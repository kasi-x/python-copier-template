#!/usr/bin/env python3
"""Detect what an existing project already has, and which apply mode fits.

Adopting the template into a repository is only safe if you know two things
first: which operation is correct for the target (a fresh scaffold, an
adoption, or an update of an already-generated project), and which of the
files the template would write already exist there. This tool answers both
from the filesystem alone -- no rendering, no answers file, no network.

It is deliberately an *inventory*, not a questionnaire oracle: it reports
observable facts and the one answer that follows deterministically from them
(which mode, and which of your files the template protects). It does not
guess `project_type`, `include_*` or any other shape question from your code
-- see notes/SPEC-adoption.md section 12, which keeps that a non-goal.

What it derives from the template tree, not from a hardcoded list: which
outputs exist and under which `existing_project` / `adopt_protect` condition
each is rendered. The report therefore stays true as those protection rules
change -- including for a template revision that predates `adopt_protect`.

Usage:
    python tools/detect.py                  # inspect the current directory
    python tools/detect.py /path/to/repo
    python tools/detect.py --json           # full report as JSON
    python tools/detect.py --answers out.yml   # write a copier --data-file

Exit codes: 0 a report was produced, 2 the target cannot be inspected or is
in a mode where `--answers` cannot apply (update / foreign template).
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Literal

import yaml

TOP = Path(__file__).resolve().parent.parent
GIT = shutil.which("git") or "git"
TEMPLATE_DIR = TOP / "template"

RenderState = Literal["overwrite", "omit"]

# The adopt_protect tokens, in questionnaire order. Facts map onto these.
PROTECT_TOKENS: tuple[str, ...] = (
    "readme",
    "license",
    "pyproject",
    "gitignore",
    "python_version",
    "scaffold",
    "docs",
)

# Fallback for a condition that only says `not existing_project` (the tree
# before adopt_protect existed) -- display only: whether a file is rendered
# in adopt mode is decided by the condition's shape, not by this map.
FILENAME_TOKENS: dict[str, str] = {
    "README.md": "readme",
    "LICENSE": "license",
    "pyproject.toml": "pyproject",
    ".gitignore": "gitignore",
    ".python-version": "python_version",
}

# Answer files the template writes that only affect the files it renders
# itself; used to name them in protections rather than guess.
JINJA_TAG = re.compile(r"{%.*?%}", re.DOTALL)
JINJA_VAR = re.compile(r"{{.*?}}", re.DOTALL)
PROTECT_CONDITION = re.compile(r"'([a-z_]+)'\s+(?:not\s+)?in\s+adopt_protect")
GIT_REMOTE = re.compile(r"(?:github\.com|gitlab\.com)[:/]+([^/]+)/(.+?)(?:\.git)?$")


class DetectError(Exception):
    """The target cannot be inspected."""


@dataclass(frozen=True)
class Fact:
    """One observed property of the target project."""

    key: str
    detail: str


@dataclass(frozen=True)
class Output:
    """One file the template can render, and what adopt mode does with it."""

    path: str
    condition: str
    token: str | None


@dataclass
class Detection:
    """The full report."""

    path: str
    mode: str
    facts: list[Fact] = field(default_factory=list)
    protections: dict[str, bool] = field(default_factory=dict)
    kept: list[str] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    suggested_answers: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    answers_file: str | None = None
    foreign_src: str | None = None
    took_over: bool = False
    skip: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serializable form used by --json."""
        return {
            "path": self.path,
            "mode": self.mode,
            "facts": [{"key": f.key, "detail": f.detail} for f in self.facts],
            "protections": self.protections,
            "kept": self.kept,
            "collisions": self.collisions,
            "added_count": len(self.added),
            "added": self.added,
            "suggested_answers": self.suggested_answers,
            "notes": self.notes,
            "answers_file": self.answers_file,
            "foreign_src": self.foreign_src,
            "took_over": self.took_over,
            "skip": self.skip,
        }


def _git(where: Path, *args: str) -> str | None:
    """Run git in `where`, returning stripped stdout or None on any failure."""
    try:
        proc = subprocess.run(  # noqa: S603  WHYNOT: fixed argv, no user input.
            [GIT, "-C", str(where), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _load_pyproject(target: Path) -> dict[str, Any]:
    """Parse pyproject.toml, or return {} when it is absent or broken."""
    path = target / "pyproject.toml"
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def _license_fact(pyproject: dict[str, Any], target: Path) -> str | None:
    license_value = pyproject.get("project", {}).get("license")
    if isinstance(license_value, str):
        return f"pyproject license = {license_value!r}"
    if isinstance(license_value, dict):
        text = license_value.get("text") or license_value.get("file")
        if text:
            return f"pyproject license = {text!r}"
    found = sorted(p.name for p in target.glob("LICENSE*")) + sorted(p.name for p in target.glob("COPYING*"))
    return ", ".join(found) if found else None


def _scaffold_fact(target: Path) -> str | None:
    src_packages = sorted(p.parent.name for p in target.glob("src/*/__init__.py"))
    if src_packages:
        return "src/" + ", src/".join(src_packages)
    flat = sorted(p.parent.name for p in target.glob("*/__init__.py") if p.parent.name not in {"tests", "docs"})
    return ", ".join(flat) if flat else None


def _remote_facts(target: Path, notes: list[str]) -> dict[str, str]:
    """Derive git_platform / owner / repo from the origin remote."""
    root = _git(target, "rev-parse", "--show-toplevel")
    if root and Path(root) != target:
        notes.append(f"target is a subdirectory of the git repository at {root}")
    url = _git(target, "remote", "get-url", "origin")
    if not url:
        return {}
    match = GIT_REMOTE.search(url)
    if not match:
        notes.append(f"origin remote {url!r} is not a github.com/gitlab.com URL; git_platform not derived")
        return {}
    owner, repo = match.group(1), match.group(2)
    platform = "github.com" if "github.com" in url else "gitlab.com"
    derived = {"repo_name": repo, "distribution_name": repo, "git_platform": platform}
    derived["github_org" if platform == "github.com" else "gitlab_group"] = owner
    return derived


def collect_facts(target: Path, notes: list[str]) -> list[Fact]:
    """Inventory the target: only paths that exist, in a stable order."""
    pyproject = _load_pyproject(target)
    project = pyproject.get("project", {})
    facts: list[Fact] = []

    def add(key: str, items: list[str]) -> None:
        if items:
            facts.append(Fact(key=key, detail=", ".join(items)))

    if (target / ".git").exists():
        remote = _git(target, "remote", "get-url", "origin") or "no origin"
        add("vcs", [f".git ({remote})"])

    add(
        "packaging",
        [
            f"pyproject.toml (name={project['name']!r})"
            if project.get("name")
            else ("pyproject.toml" if pyproject else "")
        ]
        + [name for name in ("setup.py", "setup.cfg", "Pipfile") if (target / name).exists()]
        + sorted(p.name for p in target.glob("requirements*.txt"))
        + [name for name in ("poetry.lock", "uv.lock", "pixi.lock", "pixi.toml") if (target / name).exists()],
    )
    add(
        "python",
        [name for name in (".python-version", "tox.ini", "noxfile.py") if (target / name).exists()]
        + ([f"requires-python={project['requires-python']!r}"] if project.get("requires-python") else []),
    )
    add(
        "layout",
        [item for item in [("src/" if (target / "src").is_dir() else ""), _scaffold_fact(target) or ""] if item],
    )
    add("tests", ["tests/"] if (target / "tests").is_dir() else [])
    add(
        "task runner",
        [name for name in ("justfile", "Taskfile.yml", "Makefile", "tasks.py", "duties.py") if (target / name).exists()]
        + (["poe (pyproject)"] if pyproject.get("tool", {}).get("poe") else []),
    )
    add(
        "ci",
        ([".github/workflows/"] if (target / ".github" / "workflows").is_dir() else [])
        + [name for name in (".gitlab-ci.yml", ".pre-commit-config.yaml") if (target / name).exists()],
    )
    add(
        "quality",
        [tool for tool in ("ruff", "mypy", "pyright", "pytest", "black", "isort") if tool in pyproject.get("tool", {})]
        + [
            name
            for name in (".flake8", "pytest.ini", "mypy.ini", "pyrightconfig.json", ".editorconfig", "typos.toml")
            if (target / name).exists()
        ]
        + [name for name in ("gitleaks.toml", "renovate.json", "cliff.toml") if (target / name).exists()]
        + ([".gitleaks.toml"] if (target / ".gitleaks.toml").exists() else []),
    )
    add(
        "docs",
        (["docs/"] if (target / "docs").is_dir() else [])
        + [name for name in ("mkdocs.yml", "zensical.toml", "book.toml", "conf.py") if (target / name).exists()],
    )
    add(
        "containers",
        [
            name
            for name in ("Dockerfile", "Dockerfile.gpu", "compose.yml", "compose.local.yml", ".dockerignore")
            if (target / name).exists()
        ]
        + (["devcontainer/"] if (target / ".devcontainer").is_dir() else []),
    )
    add(
        "agents",
        [
            name
            for name in ("AGENTS.md", "CLAUDE.md", ".cursorrules", ".github/copilot-instructions.md")
            if (target / name).exists()
        ],
    )
    license_fact = _license_fact(pyproject, target)
    add("license", [license_fact] if license_fact else [])
    add("authors", [f"{a.get('name')} <{a.get('email')}>" for a in project.get("authors", []) if isinstance(a, dict)])

    add("copier", [_answers_summary(path) for path in sorted(target.glob(".copier-answers*.yml"))])
    if (target / "copier.yml").is_file() and (target / "template").is_dir():
        notes.append("target contains copier.yml + template/ -- this is a copier template, not a project to adopt")
    return facts


def _answers_summary(path: Path) -> str:
    """`file (_src_path=..., _commit=...)` for the facts line."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    parts = [str(data.get("_src_path", "?"))]
    if data.get("_commit"):
        parts.append(str(data["_commit"]))
    return f"{path.name} ({', '.join(parts)})"


def protection_facts(target: Path) -> dict[str, bool]:
    """Which adopt_protect tokens have a corresponding file in the target."""
    pyproject = _load_pyproject(target)
    return {
        "readme": any(target.glob("README*")),
        "license": bool(_license_fact(pyproject, target)),
        "pyproject": (target / "pyproject.toml").is_file(),
        "gitignore": (target / ".gitignore").is_file(),
        "python_version": (target / ".python-version").is_file(),
        "scaffold": (target / "tests").is_dir() or _scaffold_fact(target) is not None,
        "docs": (target / "docs").is_dir()
        or any((target / name).exists() for name in ("mkdocs.yml", "zensical.toml", "book.toml", "conf.py")),
    }


def derive_answers(target: Path, notes: list[str]) -> dict[str, Any]:
    """Project Details that have exactly one answer on disk.

    Shape questions (project_type, include_*, docs_type, ...) are *not*
    guessed: notes/SPEC-adoption.md section 12 keeps that out of scope, and a
    wrong guess here would be silently baked into a generated project.
    """
    derived: dict[str, Any] = {}
    pyproject = _load_pyproject(target)
    project = pyproject.get("project", {})

    scaffold = _scaffold_fact(target)
    if scaffold:
        candidate = scaffold.split(", ")[0].split("/")[-1]
        if candidate.isidentifier() and candidate not in {"tests", "docs"}:
            derived["package_name"] = candidate
            if "," in scaffold:
                notes.append(f"several import packages found ({scaffold}); package_name derived from {candidate!r}")
        else:
            notes.append(f"import package {candidate!r} is not a valid identifier; package_name not derived")

    description = project.get("description")
    if isinstance(description, str) and description:
        derived["description"] = description
    derived.update(_remote_facts(target, notes))
    authors = [a for a in project.get("authors", []) if isinstance(a, dict)]
    if authors:
        if authors[0].get("name"):
            derived["author_name"] = authors[0]["name"]
        if authors[0].get("email"):
            derived["author_email"] = authors[0]["email"]
    return derived


def _is_empty(target: Path) -> bool:
    """True when nothing but a .git directory (and its own files) is present."""
    return not any(entry.name != ".git" for entry in target.iterdir())


def _normalised_template_ref(value: str) -> str:
    return re.sub(r"\.git$", "", value.strip().rstrip("/"))


def _own_identities() -> set[str]:
    """Names and URLs that mean "this template" (for _src_path matching)."""
    identities = {TOP.name, str(TOP)}
    remote = _git(TOP, "remote", "get-url", "origin")
    if remote:
        identities.add(_normalised_template_ref(remote))
        identities.add(Path(_normalised_template_ref(remote)).name)
    return identities


def _src_is_ours(src: str) -> bool:
    """True when a recorded _src_path names this repository (URL, path or clone)."""
    normalised = _normalised_template_ref(src)
    if normalised in _own_identities():
        return True
    path = Path(normalised)
    if path.exists():
        if path.resolve() == TOP:
            return True
        # A clone of this repo records a local path; ask that clone where it
        # came from rather than trusting the directory name.
        origin = _git(path, "remote", "get-url", "origin")
        if origin and _normalised_template_ref(origin) in _own_identities():
            return True
    return "python-copier-template" in normalised


def answers_owner(target: Path) -> tuple[str | None, str | None]:
    """(src_path, commit) recorded by the answers file that governs `target`."""
    for answers in sorted(target.glob(".copier-answers*.yml")):
        try:
            data = yaml.safe_load(answers.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError):
            continue
        if isinstance(data, dict) and isinstance(data.get("_src_path"), str):
            commit = data.get("_commit")
            return data["_src_path"], commit if isinstance(commit, str) else None
    return None, None


def _managed_by_this_template(target: Path) -> bool:
    """True when .copier-answers*.yml points back at this repository."""
    for answers in sorted(target.glob(".copier-answers*.yml")):
        try:
            data = yaml.safe_load(answers.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError):
            continue
        if isinstance(data, dict) and isinstance(data.get("_src_path"), str) and _src_is_ours(data["_src_path"]):
            return True
    return False


def detect_mode(target: Path) -> str:
    """Pick the operation: fresh | adopt | update | foreign."""
    if not target.exists() or (target.is_dir() and _is_empty(target)):
        return "fresh"
    if not target.is_dir():
        msg = f"{target} is not a directory"
        raise DetectError(msg)
    if sorted(target.glob(".copier-answers*.yml")):
        return "update" if _managed_by_this_template(target) else "foreign"
    return "adopt"


def _plain_part(part: str) -> str:
    return JINJA_TAG.sub("", part).strip()


def template_outputs(template_dir: Path) -> list[Output]:
    """Every file the template can render, with its adopt-mode condition.

    Answer-derived path segments (`{{ package_name }}`) are dropped: they are
    the adopter's own package tree, which `scaffold` covers.
    """
    outputs: list[Output] = []
    for path in sorted(template_dir.rglob("*")):
        if path.is_dir():
            continue
        parts = [_plain_part(part) for part in path.relative_to(template_dir).parts]
        if any(JINJA_VAR.search(part) or not part for part in parts):
            continue
        rendered = "/".join(parts).removesuffix(".jinja")
        condition = " ".join(JINJA_TAG.findall(str(path.relative_to(template_dir))))
        token: str | None = None
        match = PROTECT_CONDITION.search(condition)
        if match:
            token = match.group(1)
        elif "existing_project" in condition:
            token = FILENAME_TOKENS.get(Path(rendered).name)
        if any(existing.path == rendered for existing in outputs):
            # Several branches (e.g. zensical vs sphinx docs) render the same
            # path; it is one file to the adopter, so report it once.
            continue
        outputs.append(Output(path=rendered, condition=condition, token=token))
    return outputs


def render_state(output: Output, protections: dict[str, bool]) -> RenderState:
    """What adopt mode does with this output.

    A condition that mentions `existing_project` is false in adopt mode, so
    the file is omitted -- unless it names an `adopt_protect` token the
    adopter left deselected, which re-enables it.
    """
    if "existing_project" not in output.condition:
        return "overwrite"
    if output.token is None:
        return "omit"
    return "omit" if protections.get(output.token, False) else "overwrite"


def template_questions(template_dir: Path) -> set[str]:
    """Question names the template asks (top-level keys of its config files).

    Derived rather than assumed: `--answers` must not emit an answer the
    questionnaire does not declare, or an adoption silently carries a key
    that no question consumes.
    """
    names: set[str] = set()
    config_dir = template_dir.parent
    for path in [config_dir / "copier.yml", *sorted((config_dir / "questions").glob("*.yml"))]:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^([a-z][a-z0-9_]*):\s*$", line)
            if match:
                names.add(match.group(1))
    return names


def skip_if_exists(template_dir: Path) -> set[str]:
    """Read `_skip_if_exists` from the copier.yml that owns `template_dir`."""

    class TolerantLoader(yaml.SafeLoader):
        """SafeLoader that ignores copier's custom tags instead of failing."""

    TolerantLoader.add_multi_constructor("!", lambda _loader, _suffix, _node: None)
    config_path = template_dir.parent / "copier.yml"
    try:
        # noqa: S506  WHYNOT: TolerantLoader subclasses SafeLoader; it only
        # stops copier's !include tags from raising, and constructs nothing.
        documents = list(yaml.load_all(config_path.read_text(encoding="utf-8"), Loader=TolerantLoader))  # noqa: S506
    except (yaml.YAMLError, OSError):
        return set()
    # copier.yml is one document per !include, and _skip_if_exists lives in
    # the last one; merge them all.
    merged: dict[str, Any] = {}
    for document in documents:
        if isinstance(document, dict):
            merged.update(document)
    entries = merged.get("_skip_if_exists") or []
    return {str(entry) for entry in entries if isinstance(entry, str)}


def detect(target: Path, template_dir: Path | None = None, *, takeover: bool = False) -> Detection:
    """Inspect `target` and report the mode, the inventory and the collisions.

    `takeover=True` is the explicit "discard the other template's record and
    adopt this one" decision: a `foreign` target is then treated as an
    adoption (and reported as such), instead of being refused.
    """
    template_dir = template_dir or TEMPLATE_DIR
    notes: list[str] = []
    mode = detect_mode(target)
    detection = Detection(path=str(target), mode=mode, notes=notes)
    if mode == "foreign":
        src, commit = answers_owner(target)
        detection.foreign_src = src
        if not takeover:
            notes.append(
                f"managed by another copier template ({src}"
                + (f" at {commit}" if commit else "")
                + "); refusing to touch it -- pass --takeover to adopt anyway"
            )
            return detection
        detection.took_over = True
        detection.mode = mode = "adopt"
        notes.append(f"taking over from {src}: the previous template's .copier-answers.yml is replaced")

    if mode == "fresh":
        proposed = {"existing_project": False}
        if target.is_dir():
            proposed.update(derive_answers(target, notes))
        asked = template_questions(template_dir)
        detection.suggested_answers = {key: value for key, value in proposed.items() if key in asked}
        detection.added = [
            output.path for output in template_outputs(template_dir) if render_state(output, {}) == "overwrite"
        ]
        return detection

    detection.facts = collect_facts(target, notes)
    detection.protections = protection_facts(target)
    proposed = {
        "existing_project": True,
        "adopt_protect": [token for token in PROTECT_TOKENS if detection.protections[token]],
        **derive_answers(target, notes),
    }
    asked = template_questions(template_dir)
    detection.suggested_answers = {key: value for key, value in proposed.items() if key in asked}

    always_kept = skip_if_exists(template_dir)
    for output in template_outputs(template_dir):
        exists = (target / output.path).exists()
        state = render_state(output, detection.protections)
        if state == "omit" or output.path in always_kept:
            if exists:
                detection.kept.append(output.path)
            continue
        (detection.collisions if exists else detection.added).append(output.path)

    detection.collisions.sort()
    detection.added.sort()
    detection.kept.sort()
    detection.skip = list(detection.collisions)
    if not any(detection.protections.values()):
        notes.append("no protectable files found; adopt mode would render every file it produces")
    return detection


def _bullet_section(title: str, entries: list[str], limit: int) -> list[str]:
    if not entries:
        return []
    shown = entries[:limit]
    lines = ["", title]
    lines.extend(f"  {entry}" for entry in shown)
    if len(entries) > limit:
        lines.append(f"  ... and {len(entries) - limit} more")
    return lines


def render_report(detection: Detection, limit: int = 12) -> str:
    """Human-readable report: facts, what is kept, what would be written."""
    lines = [f"path: {detection.path}", f"mode: {detection.mode}"]
    if detection.facts:
        lines.extend(["", "facts"])
        lines.extend(f"  {fact.key:<12} {fact.detail}" for fact in detection.facts)
    if detection.mode == "foreign":
        lines += [
            "",
            "STOP: this project is already managed by another copier template",
            f"  _src_path: {detection.foreign_src}",
            "  `copier copy` here would write this template's files over that project's",
            "  and replace its answers file. To adopt this template anyway (discarding",
            "  the previous template's record), re-run with --takeover.",
        ]
        return "\n".join(lines)
    if detection.mode == "adopt":
        lines += _bullet_section("kept (your files; adopt mode does not write them)", detection.kept, limit)
        lines += _bullet_section(
            "COLLISIONS (already exist and adopt mode WOULD write them)", detection.collisions, limit
        )
    if detection.mode == "fresh":
        lines += _bullet_section("would render", detection.added, limit)
    elif detection.added:
        lines += _bullet_section(
            f"added ({len(detection.added)} files the template would create)", detection.added, limit
        )
    if detection.suggested_answers:
        lines += ["", "suggested answers"]
        lines.extend(f"  {key}: {json.dumps(value)}" for key, value in detection.suggested_answers.items())
    if detection.mode == "adopt":
        skips = " ".join(f"--skip {shlex.quote(path)}" for path in detection.skip)
        lines += [
            "",
            "next (keep your files, add the rest):",
            "  python tools/detect.py <path> --answers answers.yml",
            "  copier copy --trust --defaults --vcs-ref=<ref> --data-file answers.yml "
            f"{skips} <TEMPLATE_URL> <path>".rstrip(),
            "  copier stops at the first conflict without --skip (and replaces it with --overwrite);",
            "  a --skip path that the template would not render for your answers is harmless.",
        ]
    if detection.notes:
        lines += ["", "notes"]
        lines.extend(f"  {note}" for note in detection.notes)
    return "\n".join(lines)


def write_answers(detection: Detection, destination: Path) -> None:
    """Write a copier --data-file for the detected mode."""
    body = yaml.safe_dump(detection.suggested_answers, sort_keys=False, default_flow_style=False)
    header = (
        f"# Generated by tools/detect.py from {detection.path}\n"
        f"# mode: {detection.mode}\n"
        "# Shape questions (project_type, include_*, docs_type, ...) are NOT guessed:\n"
        "# add them yourself, or accept each question's default with --defaults.\n"
    )
    destination.write_text(header + body, encoding="utf-8")
    detection.answers_file = str(destination)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect what an existing project already has.")
    parser.add_argument("path", nargs="?", type=Path, default=Path(), help="project to inspect (default: .)")
    parser.add_argument("--template", type=Path, default=TEMPLATE_DIR, help="template tree to read the outputs from")
    parser.add_argument("--answers", type=Path, default=None, help="write a copier --data-file here")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("--takeover", action="store_true", help="adopt over a foreign template's answers file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: detect, report, and optionally write an answers file."""
    args = _parse_args(argv)
    target = args.path.resolve()
    try:
        detection = detect(target, args.template, takeover=args.takeover)
    except DetectError as exc:
        print(f"cannot inspect: {exc}", file=sys.stderr)
        return 2

    refused = detection.mode == "foreign"
    if args.answers is not None and not refused:
        if detection.mode not in ("fresh", "adopt"):
            remedy = "run copier update" if detection.mode == "update" else "another template manages this project"
            print(
                f"mode is {detection.mode!r}: an answers file only applies to a fresh copy or an adoption ({remedy})",
                file=sys.stderr,
            )
            return 2
        write_answers(detection, args.answers)

    if args.json:
        print(json.dumps(detection.as_dict(), indent=2))
    else:
        print(render_report(detection))
    # A foreign target is a refusal, not a failure to inspect: the report above
    # names the other template and the --takeover escape hatch.
    return 3 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
