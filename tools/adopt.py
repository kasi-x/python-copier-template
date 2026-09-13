#!/usr/bin/env python3
"""Adopt this template into an existing project, transactionally.

Adoption has three failure modes that `copier copy` alone does not protect
against, all measured against copier 9.18.1:

1. **A half-written destination.** A file the template also ships
   (`.github/workflows/ci.yml`, `renovate.json`, ...) that already exists is a
   *conflict*: copier stops with `Interactive session required` and exits 1 --
   after writing every file it had already rendered. The project is left in a
   state that is neither before nor after.
2. **Silent replacement.** Passing `--overwrite` avoids the stop by replacing
   those files, including collisions nobody listed.
3. **Expanding the wrong revision.** `copier copy <url>` resolves the latest
   *tag*, and a fork's inherited tags can point at a long-abandoned ancestor
   with a different questionnaire.

This driver closes all three:

- it reads the collisions from `tools/detect.py` and passes them to copier as
  `skip_if_exists`, so the adopter's files are left alone and everything else
  is still added;
- it renders with `overwrite=False` and *verifies* afterwards that no existing
  file changed (by content) and that nothing disappeared -- restoring the
  originals and deleting what the run created if anything did;
- it resolves the revision by asking whether the latest tag actually carries
  this questionnaire, falling back to the default branch when it does not.

What it deliberately does not do: merge the adopter's configuration *into*
the template's. Splitting a `pyproject.toml` into sections and reconciling
them with a generated one is not something a renderer can do correctly (see
notes/SPEC-adoption.md section 12); the run ends by telling you what to wire
by hand instead.

Usage:
    python tools/adopt.py /path/to/project --dry-run     # plan only
    python tools/adopt.py /path/to/project               # plan, then apply
    python tools/adopt.py /path/to/project --data project_type=library

Exit codes: 0 adopted (or a dry run that found no problem), 1 the run failed
and the project was rolled back, 2 the request is invalid (already generated
by this template, not a directory, bad options), 3 refused (another copier
template owns the project and --takeover was not given).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import shutil
import sys
import tempfile
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import batch  # noqa: E402
from tools import detect  # noqa: E402
from tools import file_merge  # noqa: E402
from tools import pyproject_merge  # noqa: E402

QUESTION_LINE = re.compile(r"^([a-z][a-z0-9_]*):\s*$", re.MULTILINE)
CONFIG_FILES = ("copier.yml", "copier.yaml")


class AdoptError(Exception):
    """The request cannot be carried out as asked."""


class OwnershipError(AdoptError):
    """Another copier template owns the target (a refusal, not a failure)."""


@dataclass
class _Run:
    """What the render produced, for the steps that verify or amend it."""

    target: Path
    backup: dict[str, bytes]
    data: dict[str, Any]
    ref: str
    created: list[str]
    before_dirs: set[str]


@dataclass
class Adoption:
    """The plan, what the run did, and -- when it failed -- what was undone."""

    target: str
    mode: str
    ref: str
    ref_reason: str
    skip: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    ok: bool = False
    applied: bool = False
    error: str | None = None
    notes: list[str] = field(default_factory=list)
    deps: dict[str, Any] | None = None
    tool_config: dict[str, Any] | None = None
    files_merged: list[dict[str, Any]] = field(default_factory=list)
    cancelled: bool = False
    declined: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serializable form used by --json and the MCP tool."""
        return {
            "target": self.target,
            "mode": self.mode,
            "ref": self.ref,
            "ref_reason": self.ref_reason,
            "skip": self.skip,
            "created_count": len(self.created),
            "created": self.created,
            "unchanged": self.unchanged,
            "restored": self.restored,
            "removed": self.removed,
            "ok": self.ok,
            "applied": self.applied,
            "error": self.error,
            "notes": self.notes,
            "deps": self.deps,
            "tool_config": self.tool_config,
            "files_merged": self.files_merged,
            "cancelled": self.cancelled,
            "declined": self.declined,
        }


def _ref_questions(ref: str) -> set[str]:
    """Question names declared at `ref`, read out of git without a checkout."""
    names: set[str] = set()
    paths = [*CONFIG_FILES, *(p for p in _ref_question_files(ref))]
    for path in paths:
        shown = batch.git(TOP, "show", f"{ref}:{path}")
        if shown.returncode != 0:
            continue
        names.update(QUESTION_LINE.findall(shown.stdout))
    return names


def _ref_question_files(ref: str) -> list[str]:
    listing = batch.git(TOP, "ls-tree", "-r", "--name-only", ref, "--", "questions")
    if listing.returncode != 0:
        return []
    return [line for line in listing.stdout.splitlines() if line.endswith((".yml", ".yaml"))]


def resolve_ref(requested: str | None = None) -> tuple[str, str]:
    """Choose the revision to expand: the latest tag only if it is this questionnaire.

    `copier copy` without `--vcs-ref` resolves the repository's newest tag.
    This fork tags its own releases, so that tag normally is the right
    questionnaire. It is still used only when it declares the same questions
    as this checkout -- a tag left over from before the fork detach points at
    a different template -- and otherwise the default branch is used, with the
    reason reported. `--ref` names a revision explicitly; `--ref HEAD` expands
    the working tree for local iteration.
    """
    if requested:
        return requested, "requested explicitly"
    latest = batch.git(TOP, "describe", "--tags", "--abbrev=0")
    branch = batch.git(TOP, "rev-parse", "--abbrev-ref", "HEAD")
    branch_name = branch.stdout.strip() if branch.returncode == 0 else ""
    tag = latest.stdout.strip() if latest.returncode == 0 else ""
    if not tag or not branch_name or branch_name == "HEAD":
        return "HEAD", "no usable tag or branch; rendering the working tree"
    worktree = _ref_questions("HEAD")
    tagged = _ref_questions(tag)
    missing = sorted(worktree - tagged)
    if missing:
        reason = (
            f"latest tag {tag} does not carry this questionnaire "
            f"(missing {len(missing)} question(s), e.g. {', '.join(missing[:3])}); using {branch_name}"
        )
        return branch_name, reason
    return tag, f"latest tag {tag} carries this questionnaire"


def _plan_data(detection: detect.Detection, answers: dict[str, Any]) -> dict[str, Any]:
    """The answers for this target: what detect derived, overridden by the caller."""
    data = dict(detection.suggested_answers)
    if detection.mode == "fresh":
        data["existing_project"] = False
    data.update(answers)
    return data


# The template files an adopter commonly already has, and how to merge each.
MERGE_KINDS = {
    ".gitignore": "gitignore",
    "justfile": "justfile",
    "Makefile": "makefile",
    "Taskfile.yml": "taskfile",
    "tasks.py": "python_tasks",
    "duties.py": "python_tasks",
}


def plan_merges(target: Path, data: dict[str, Any], ref: str) -> dict[str, Any]:
    """Compute every merge without writing, for a dry run and the prompts."""
    source = render_fresh_source(data, ref)
    try:
        dependencies = pyproject_merge.merge_dependencies(
            target / "pyproject.toml", source / "pyproject.toml", apply=False
        )
        config = pyproject_merge.merge_tool_config(
            target / "pyproject.toml",
            source / "pyproject.toml",
            identity=_merge_identity(data, source),
            apply=False,
        )
        files = [
            file_merge.merge_text_file(target / name, source / name, kind, apply=False).as_dict()
            for name, kind in MERGE_KINDS.items()
            if (target / name).is_file() and (source / name).is_file()
        ]
        ci_plan = _plan_ci_jobs(target, source)
        if ci_plan is not None:
            files.append(ci_plan)
        return {"dependencies": dependencies.as_dict(), "tool_config": config.as_dict(), "files": files}
    finally:
        shutil.rmtree(source, ignore_errors=True)


def render_fresh_source(data: dict[str, Any], ref: str) -> Path:
    """Render a *fresh* project into a temp dir and return where it landed.

    In adopt mode the template does not render the protected files at all, so
    asking what the template would have generated means asking for the fresh
    scaffold. The caller owns the returned directory's lifetime.
    """
    directory = Path(tempfile.mkdtemp(prefix="adopt-merge-"))
    fresh = {**data, "existing_project": False, "adopt_protect": []}
    with batch.report_stream_only():
        batch.render(str(TOP), directory, fresh, ref)
    return directory


def _merge_identity(data: dict[str, Any], source: Path) -> tuple[str, ...]:
    """Tokens that mark a value as *this project's*, not a tool preference."""
    tokens = {
        str(data.get(key, ""))
        for key in ("package_name", "repo_name", "distribution_name", "github_org", "gitlab_group")
    }
    if (source / "pyproject.toml").is_file():
        with contextlib.suppress(tomllib.TOMLDecodeError, KeyError, OSError):
            tokens.add(str(tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]["name"]))
    return tuple(sorted(token for token in tokens if token))


def merge_generated_files(
    run: _Run,
    adoption: Adoption,
    *,
    approved: frozenset[str] = frozenset(),
    approved_files: frozenset[str] = frozenset(),
) -> None:
    """Merge what the template generated into the files the adopter already had."""
    target_pyproject = run.target / "pyproject.toml"
    before_pyproject = run.backup.get("pyproject.toml") or (
        target_pyproject.read_bytes() if target_pyproject.is_file() else None
    )
    source = render_fresh_source(run.data, run.ref)
    try:
        merged = pyproject_merge.merge_dependencies(target_pyproject, source / "pyproject.toml")
        adoption.deps = merged.as_dict()
        adoption.notes.extend(merged.notes)
        config = pyproject_merge.merge_tool_config(
            target_pyproject,
            source / "pyproject.toml",
            identity=_merge_identity(run.data, source),
            approved=approved,
        )
        adoption.tool_config = config.as_dict()
        adoption.notes.extend(config.notes)
        problem = merge_problem(target_pyproject, before_pyproject)
        if problem:
            raise _MergeError(problem)
        _merge_text_files(run, adoption, source, approved_files=approved_files)
        _merge_ci_caller(run, adoption, source, approved_files=approved_files)
    finally:
        shutil.rmtree(source, ignore_errors=True)


class _MergeError(Exception):
    """A merge broke the add-only contract; the caller rolls the run back."""


def _merge_text_files(
    run: _Run, adoption: Adoption, source: Path, *, approved_files: frozenset[str] = frozenset()
) -> None:
    """Append the missing entries of the line-oriented files, keeping backups."""
    for name, kind in MERGE_KINDS.items():
        target_file = run.target / name
        if not target_file.is_file() or not (source / name).is_file():
            continue
        before = run.backup.setdefault(name, target_file.read_bytes())
        result = file_merge.merge_text_file(target_file, source / name, kind, append=name in approved_files)
        adoption.files_merged.append(result.as_dict())
        adoption.notes.extend(result.notes)
        if result.applied and not file_merge.original_is_preserved(before, target_file.read_bytes()):
            msg = f"merging {name} rewrote existing content"
            raise _MergeError(msg)
    _note_runner_mismatch(run, adoption, source)


def _note_runner_mismatch(run: _Run, adoption: Adoption, source: Path) -> None:
    """Tell the adopter when their runner file is not the one the answers picked."""
    for name, kind in MERGE_KINDS.items():
        if kind == "gitignore" or not (run.target / name).is_file():
            continue
        if not (source / name).is_file():
            runners = [candidate for candidate, candidate_kind in MERGE_KINDS.items() if candidate_kind != "gitignore"]
            rendered = ", ".join(sorted(candidate for candidate in runners if (source / candidate).is_file()))
            adoption.notes.append(
                f"your {name} was kept, but these answers render {rendered or 'no task runner'}; "
                f"re-run with --data task_runner=<runner> for that runner's entries"
            )


def _merge_ci_caller(
    run: _Run, adoption: Adoption, source: Path, *, approved_files: frozenset[str] = frozenset()
) -> None:
    """Add the template's checks beside their workflow — or into it, when approved.

    The default is the non-destructive placement (`copier-ci.yml`). Appending
    to their ci.yml happens only for a plan entry the human approved; when the
    append turns out to be unsafe (or there was nothing to append), the run
    falls back to the placement, so the checks are offered either way.
    """
    target_ci = run.target / ".github/workflows/ci.yml"
    if not target_ci.is_file():
        return
    source_ci = source / ".github/workflows/ci.yml"
    if "ci.yml" in approved_files and source_ci.is_file():
        before = run.backup.setdefault(".github/workflows/ci.yml", target_ci.read_bytes())
        result = file_merge.merge_ci_jobs(target_ci, source_ci, append=True)
        adoption.files_merged.append(result.as_dict())
        adoption.notes.extend(result.notes)
        if result.applied:
            if not file_merge.original_is_preserved(before, target_ci.read_bytes()):
                msg = "merging .github/workflows/ci.yml rewrote existing content"
                raise _MergeError(msg)
            return
        if not result.reported:
            return  # nothing was missing: their workflow already carries the checks
        adoption.notes.append("your ci.yml could not take the jobs; copier-ci.yml was added alongside instead")
    result = file_merge.merge_ci_caller(run.target, source_ci)
    adoption.files_merged.append(result.as_dict())
    adoption.notes.extend(result.notes)


def _plan_ci_jobs(target: Path, source: Path) -> dict[str, Any] | None:
    """The plan for their ci.yml: the read-only jobs that could be appended to it."""
    target_ci = target / ".github/workflows/ci.yml"
    source_ci = source / ".github/workflows/ci.yml"
    if not target_ci.is_file() or not source_ci.is_file():
        return None
    return file_merge.merge_ci_jobs(target_ci, source_ci, append=False).as_dict()


def _snapshot(target: Path, risky: list[str]) -> dict[str, bytes]:
    """Content of every existing file the template could write over."""
    backup: dict[str, bytes] = {}
    for relative in risky:
        path = target / relative
        if path.is_file():
            backup[relative] = path.read_bytes()
    return backup


def _verify(target: Path, backup: dict[str, bytes], before: set[str]) -> tuple[list[str], list[str], list[str]]:
    """(changed, removed, created) -- what the render did that it should not have."""
    changed = [
        relative
        for relative, content in backup.items()
        if (target / relative).is_file() and (target / relative).read_bytes() != content
    ]
    removed = [relative for relative in backup if not (target / relative).exists()]
    after = {str(path.relative_to(target)) for path in target.rglob("*") if path.is_file()}
    return sorted(changed), sorted(removed), sorted(after - before)


def _roll_back(target: Path, backup: dict[str, bytes], created: list[str], before_dirs: set[str]) -> None:
    """Restore the backed-up files and remove every path this run created.

    Directories too: a render can leave an empty one behind (a `docs/how-to/`
    whose files were all conditional), and leaving it would make "the project
    is unchanged" a lie.
    """
    for relative, content in backup.items():
        path = target / relative
        if not path.exists() or path.read_bytes() != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    for relative in created:
        path = target / relative
        if path.is_file():
            path.unlink()
    now_dirs = {str(path.relative_to(target)) for path in target.rglob("*") if path.is_dir()}
    for relative in sorted(now_dirs - before_dirs, key=lambda name: len(Path(name).parts), reverse=True):
        directory = target / relative
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def adopt(  # noqa: PLR0913  WHYNOT: the keyword-only options are the operation's whole contract; a bag would hide them from the MCP tool schema.
    target: Path,
    *,
    ref: str | None = None,
    answers: dict[str, Any] | None = None,
    skip: list[str] | None = None,
    takeover: bool = False,
    dry_run: bool = False,
    merge_generated: bool = True,
    ask: Callable[[str], str] | None = None,
) -> Adoption:
    """Plan (and unless `dry_run`, apply) an adoption of `target`."""
    detection = detect.detect(target, takeover=takeover)
    if detection.mode == "update":
        msg = "this project was already generated from this template: run `copier update` (or tools/batch.py)"
        raise AdoptError(msg)
    if detection.mode == "foreign":
        msg = (
            f"another copier template owns this project ({detection.foreign_src}); "
            "pass takeover=True to replace its record"
        )
        raise OwnershipError(msg)

    resolved_ref, reason = resolve_ref(ref)
    adoption = Adoption(
        target=str(target),
        mode=detection.mode,
        ref=resolved_ref,
        ref_reason=reason,
        skip=list(detection.skip if skip is None else skip),
        notes=list(detection.notes),
    )
    if skip is None and detection.mode == "adopt" and not adoption.skip:
        adoption.notes.append("no collisions: nothing existing would be replaced")

    data = _plan_data(detection, answers or {})
    if dry_run:
        _plan_only(target, data, resolved_ref, adoption, detection)
        if not merge_generated:
            adoption.deps = None
            adoption.tool_config = None
            adoption.files_merged = []
        return adoption

    backup = _snapshot(target, [*detection.kept, *detection.collisions])
    before = {str(path.relative_to(target)) for path in target.rglob("*") if path.is_file()}
    before_dirs = {str(path.relative_to(target)) for path in target.rglob("*") if path.is_dir()}
    failed: str | None = None
    try:
        with batch.report_stream_only():
            batch.render(
                str(TOP),
                target,
                data,
                resolved_ref,
                skip_if_exists=tuple(adoption.skip),
                overwrite=False,
            )
    except Exception as exc:  # noqa: BLE001  WHYNOT: the failure is reported and rolled back, not raised.
        failed = f"{type(exc).__name__}: {exc}"

    changed, removed, created = _verify(target, backup, before)
    if failed or changed or removed:
        _roll_back(target, backup, created, before_dirs)
        adoption.error = failed or f"the render modified existing files ({', '.join([*changed, *removed][:5])})"
        adoption.restored = [*changed, *removed]
        adoption.removed = created
        adoption.notes.append("rolled back: the project is unchanged")
        return adoption

    adoption.ok = True
    adoption.applied = True
    adoption.created = created
    adoption.unchanged = sorted(backup)
    if merge_generated:
        run = _Run(target=target, backup=backup, data=data, ref=resolved_ref, created=created, before_dirs=before_dirs)
        _finish_with_merges(run, adoption, ask)
    return adoption


def _finish_with_merges(run: _Run, adoption: Adoption, ask: Callable[[str], str] | None) -> None:
    """Confirm the merge plan (when asked), apply it, or take the run back."""
    confirmation = _confirm_merges(run, ask)
    if confirmation.cancel:
        _undo_merges(run, adoption, "cancelled at the confirmation prompt")
        adoption.cancelled = True
        adoption.error = None
        adoption.notes.append("cancelled: the render was rolled back too")
        return
    if not confirmation.merge:
        adoption.notes.append("merges skipped: your files were left as they were")
        return
    try:
        merge_generated_files(run, adoption, approved=confirmation.approved, approved_files=confirmation.files)
    except _MergeError as exc:
        _undo_merges(run, adoption, str(exc))


@dataclass(frozen=True)
class Confirmation:
    """The human's answer to the merge plan."""

    cancel: bool = False
    merge: bool = True
    approved: frozenset[str] = frozenset()
    files: frozenset[str] = frozenset()


def _confirm_merges(run: _Run, ask: Callable[[str], str] | None) -> Confirmation:
    """Show what would be merged and ask; returns the answer.

    Without an `ask` callback this is a no-op: the automatic plan is applied,
    which is what a non-interactive caller (CI, an MCP tool) wants. With one,
    the questions are the plan itself and then, one by one, the values that
    were *not* copied because they name the generated project -- those are the
    decisions a human should make.
    """
    if ask is None:
        return Confirmation()
    plan = plan_merges(run.target, run.data, run.ref)
    lines = _merge_summary_from(plan)
    if not lines:
        return Confirmation()
    answer = ask(_MERGE_QUESTION.format(plan="\n".join(lines)))
    if answer == "cancel":
        return Confirmation(cancel=True)
    if answer == "no":
        return Confirmation(merge=False)
    approved_files = _ask_about_task_files(plan, ask)
    approved_files |= _ask_about_ci_jobs(plan, ask)
    approved_values = _ask_about_values(plan, ask)
    return Confirmation(approved=frozenset(approved_values), files=frozenset(approved_files))


# The file kinds where appending means a real edit of the adopter's task list.
TASK_APPEND_KINDS = ("taskfile", "python_tasks")


def _ask_about_task_files(plan: dict[str, Any], ask: Callable[[str], str]) -> set[str]:
    """Ask about the task files (Taskfile.yml, tasks.py, duties.py): appending tasks is a real edit."""
    approved: set[str] = set()
    for entry in plan["files"]:
        if entry.get("kind") not in TASK_APPEND_KINDS or not entry.get("reported"):
            continue
        name = Path(entry["path"]).name
        if ask(f"append these tasks to your {name}: {', '.join(entry['reported'][:8])}? [Y]es / [n]o") == "yes":
            approved.add(name)
    return approved


def _ask_about_ci_jobs(plan: dict[str, Any], ask: Callable[[str], str]) -> set[str]:
    """Ask where the template's read-only jobs go: into their ci.yml, or beside it."""
    approved: set[str] = set()
    for entry in plan["files"]:
        if entry.get("kind") != "ci_jobs" or not entry.get("reported"):
            continue
        name = Path(entry["path"]).name
        answer = ask(
            f"append these jobs to your {name}: {', '.join(entry['reported'][:8])}? "
            "[Y]es / [n]o (copier-ci.yml alongside instead)"
        )
        if answer == "yes":
            approved.add(name)
    return approved


def _ask_about_values(plan: dict[str, Any], ask: Callable[[str], str]) -> set[str]:
    """Ask, one by one, about the values that name this project."""
    approved: set[str] = set()
    approve_rest = False
    for line in plan["tool_config"]["needs_your_value"]:
        key_path = line.split(" (template:")[0]
        if approve_rest:
            approved.add(key_path)
            continue
        answer = ask(f"add {line}? [Y]es / [n]o / [a]ll:")
        if answer == "all":
            approve_rest = True
            approved.add(key_path)
        elif answer == "yes":
            approved.add(key_path)
    return approved


_MERGE_QUESTION = """\
these files the template also generates already exist, and this is what would
be added to them (nothing of yours is rewritten):

{plan}

Apply? [Y]es / [n]o (render only) / [c]ancel:"""


def _undo_merges(run: _Run, adoption: Adoption, problem: str) -> None:
    """Restore every merged file, then take the whole run back.

    The merges may only add; when one of them breaks that (a dropped key, a
    rewritten line), the render goes too: a failed adoption still means "the
    project is exactly as it was".
    """
    for relative, content in run.backup.items():
        path = run.target / relative
        if path.is_file() and path.read_bytes() != content:
            path.write_bytes(content)
    _roll_back(run.target, run.backup, run.created, run.before_dirs)
    adoption.ok = False
    adoption.applied = False
    adoption.error = f"merge failed and was rolled back: {problem}"
    adoption.restored = sorted(run.backup)
    adoption.removed = run.created
    adoption.notes.append("rolled back: the project is unchanged")


def _plan_only(target: Path, data: dict[str, Any], ref: str, adoption: Adoption, detection: detect.Detection) -> None:
    """Fill in a dry-run result: what would be rendered, and what merged."""
    adoption.ok = True
    adoption.unchanged = detection.kept
    adoption.notes.append(f"dry run: would render {len(detection.added)} new file(s)")
    plan = plan_merges(target, data, ref)
    adoption.deps = plan["dependencies"]
    adoption.tool_config = plan["tool_config"]
    adoption.files_merged = plan["files"]
    for section in (plan["dependencies"], plan["tool_config"]):
        adoption.notes.extend(section["notes"])


def merge_problem(target_pyproject: Path, before: bytes | None) -> str | None:
    """Why the merged pyproject is not acceptable, or None when it is.

    The merge may only add: every requirement that was declared before must
    still be declared, unchanged, and the file must still parse.
    """
    if before is None:
        return None
    try:
        after_document = tomllib.loads(target_pyproject.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return f"the merged file does not parse: {exc}"
    try:
        before_document = tomllib.loads(before.decode("utf-8"))
    except tomllib.TOMLDecodeError:
        return None
    after = pyproject_merge.declared_values(after_document)
    for name, raw in pyproject_merge.declared_values(before_document).items():
        if name not in after:
            return f"{name} was dropped"
        if after[name] != raw:
            return f"{name} was changed from {raw!r} to {after[name]!r}"
    return None


def _parse_data(pairs: list[str] | None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            msg = f"--data expects key=value, got {pair!r}"
            raise AdoptError(msg)
        key, value = pair.split("=", 1)
        data[key.strip()] = yaml.safe_load(value)
    return data


def _load_answers(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.is_file():
        msg = f"answers file not found: {path}"
        raise AdoptError(msg)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is not None and not isinstance(loaded, dict):
        msg = f"{path}: expected a mapping of answers"
        raise AdoptError(msg)
    return dict(loaded or {})


def _prompter(args: argparse.Namespace) -> Callable[[str], str] | None:
    """The confirmation prompt, or None when nobody is there to answer it.

    `--yes` (and any non-interactive run) applies the automatic plan: a tool
    that blocks on stdin in CI or inside an MCP session is worse than one that
    does the safe thing and says so. `--ask` forces the prompt.
    """
    if args.yes or args.dry_run:
        return None
    if not args.ask and not sys.stdin.isatty():
        return None

    def confirm(question: str) -> str:
        print(question)
        while True:
            try:
                answer = input().strip().lower()
            except EOFError:
                print("(no input; taking that as cancel)")
                return "cancel"
            if answer in ("", "y", "yes"):
                return "yes"
            if answer in ("n", "no"):
                return "no"
            if answer in ("c", "cancel"):
                return "cancel"
            if answer in ("a", "all"):
                return "all"

    return confirm


def render_report(adoption: Adoption) -> str:
    """Human-readable plan and outcome."""
    lines = [
        f"target: {adoption.target}",
        f"mode:   {adoption.mode}",
        f"ref:    {adoption.ref}  ({adoption.ref_reason})",
    ]
    if adoption.skip:
        lines.append(f"skip:   {' '.join(adoption.skip)}")
    lines.append("")
    if adoption.cancelled:
        lines.append("cancelled -- nothing was applied")
    elif not adoption.applied and adoption.error is None:
        lines.append("dry run -- nothing written")
    elif adoption.error is not None:
        lines.append(f"FAILED: {adoption.error}")
        if adoption.restored:
            lines.append(f"  restored: {', '.join(adoption.restored)}")
        if adoption.removed:
            lines.append(f"  removed what the run created: {len(adoption.removed)} file(s)")
    else:
        lines.append(
            f"adopted: {len(adoption.created)} file(s) added, {len(adoption.unchanged)} existing file(s) untouched"
        )
    merged = _merge_summary(adoption)
    if merged:
        heading = "merged into your files" if adoption.applied else "would merge into your files"
        lines += ["", heading]
        lines.extend(f"  {line}" for line in merged)
    if adoption.notes:
        lines.append("")
        lines.extend(f"  {note}" for note in adoption.notes)
    if adoption.applied:
        lines += [
            "",
            "next",
            "  git diff     # review; the adoption only added files",
            "  git status   # untracked additions: CI, hygiene, AGENTS.md, ...",
        ]
    return "\n".join(lines)


def _merge_summary_from(plan: dict[str, Any]) -> list[str]:
    """The same summary, computed from a plan (used by the prompt and dry runs)."""
    lines: list[str] = []
    dependencies = plan.get("dependencies") or {}
    if dependencies.get("added"):
        added = [f"{section}: {', '.join(names)}" for section, names in dependencies["added"].items()]
        lines.append(f"pyproject.toml dependencies -> {'; '.join(added)}")
    config = plan.get("tool_config") or {}
    if config.get("added"):
        tables = sorted(config["added"])
        shown = ", ".join(f"[{table}]" for table in tables[:3])
        more = f" and {len(tables) - 3} more" if len(tables) > 3 else ""
        lines.append(f"pyproject.toml tool config -> {len(tables)} table(s): {shown}{more}")
    for entry in plan.get("files", []):
        detail = ", ".join(entry.get("added", [])[:6]) + ("..." if len(entry.get("added", [])) > 6 else "")
        if detail:
            lines.append(f"{Path(entry['path']).name} -> {detail}")
        elif entry.get("reported"):
            lines.append(f"{Path(entry['path']).name} -> not written: {', '.join(entry['reported'][:6])}")
    return lines


def _merge_summary(adoption: Adoption) -> list[str]:
    """One line per file the merge step touched, for the review step."""
    lines: list[str] = []
    if adoption.deps:
        added = [f"{section}: {', '.join(names)}" for section, names in adoption.deps["added"].items()]
        if added:
            lines.append(f"pyproject.toml dependencies -> {'; '.join(added)}")
    if adoption.tool_config and adoption.tool_config["added"]:
        tables = sorted(adoption.tool_config["added"])
        shown = ", ".join(f"[{table}]" for table in tables[:3])
        more = f" and {len(tables) - 3} more" if len(tables) > 3 else ""
        lines.append(f"pyproject.toml tool config -> {len(tables)} table(s): {shown}{more}")
    for entry in adoption.files_merged:
        detail = ", ".join(entry["added"][:6]) + ("..." if len(entry["added"]) > 6 else "")
        if detail:
            lines.append(f"{Path(entry['path']).name} -> {detail}")
        elif entry["reported"]:
            lines.append(f"{Path(entry['path']).name} -> not written: {', '.join(entry['reported'][:6])}")
    return lines


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Adopt this template into an existing project, transactionally.")
    parser.add_argument("path", type=Path, help="project to adopt into (a directory)")
    parser.add_argument("--ref", default=None, help="template revision to expand (default: judged from the tags)")
    parser.add_argument(
        "--answers", type=Path, default=None, help="copier answers file (see tools/detect.py --answers)"
    )
    parser.add_argument("--data", action="append", default=None, help="extra answer, key=value (repeatable)")
    parser.add_argument(
        "--skip", action="append", default=None, help="path to never write over (default: the detected collisions)"
    )
    parser.add_argument("--takeover", action="store_true", help="replace a foreign template's answers file")
    parser.add_argument("--dry-run", action="store_true", help="plan only; write nothing")
    parser.add_argument("--yes", action="store_true", help="apply without the confirmation prompt")
    parser.add_argument("--ask", action="store_true", help="confirm even when stdin is not a terminal")
    parser.add_argument("--no-merge", action="store_true", help="do not merge anything into the files you already have")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: plan, apply, and roll back on any failed expectation."""
    args = _parse_args(argv)
    if not args.path.is_dir():
        print(f"not a directory: {args.path}", file=sys.stderr)
        return 2
    try:
        adoption = adopt(
            args.path.resolve(),
            ref=args.ref,
            answers={**_load_answers(args.answers), **_parse_data(args.data)},
            skip=args.skip,
            takeover=args.takeover,
            dry_run=args.dry_run,
            merge_generated=not args.no_merge,
            ask=_prompter(args),
        )
    except OwnershipError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (AdoptError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(adoption.as_dict(), indent=2))
    else:
        print(render_report(adoption))
    return 0 if adoption.ok or adoption.error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
