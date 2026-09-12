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
import json
import re
import sys
import tempfile
import tomllib
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
from tools import pyproject_deps  # noqa: E402

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

    `copier copy` without `--vcs-ref` resolves the latest tag. On a fork those
    tags can be inherited and point at a different template, so the tag is used
    only when it declares the same questions as this checkout; otherwise the
    default branch is used, with the reason reported.
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


def _declared_requirements(document: dict[str, Any]) -> dict[str, str]:
    """Canonical name -> requirement string, across the tables a merge writes."""
    found: dict[str, str] = {}
    for keys in (
        ("project", "dependencies"),
        ("dependency-groups", "dev"),
        ("tool", "poetry", "dependencies"),
    ):
        node: Any = document
        for key in keys:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, list):
            items = [(str(entry), str(entry)) for entry in node if isinstance(entry, str)]
        elif isinstance(node, dict):
            items = [(str(name), str(value)) for name, value in node.items()]
        else:
            continue
        for name, raw in items:
            found.setdefault(pyproject_deps.canonical(name), raw)
    return found


def merge_template_dependencies(
    target: Path, data: dict[str, Any], ref: str, *, apply: bool
) -> pyproject_deps.MergeResult | None:
    """Merge the generated project's dependencies into the adopter's pyproject.

    The generated file is rendered into a temporary directory (the adopter's
    own pyproject is protected, so the adopt render never produced one); only
    the missing names are then added, through tools/pyproject_merge.py.
    """
    target_pyproject = target / "pyproject.toml"
    if not target_pyproject.is_file():
        return None
    with tempfile.TemporaryDirectory(prefix="adopt-deps-") as tmp:
        # A *fresh* render: in adopt mode the template does not render
        # pyproject.toml at all (it is the adopter's file), so asking for the
        # generated dependency set means asking for the fresh scaffold.
        fresh = {**data, "existing_project": False, "adopt_protect": []}
        with batch.report_stream_only():
            batch.render(str(TOP), Path(tmp), fresh, ref)
        source = Path(tmp) / "pyproject.toml"
        if not source.is_file():
            return None
        return pyproject_deps.merge_dependencies(target_pyproject, source, apply=apply)


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
    merge_deps: bool = True,
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
        adoption.ok = True
        adoption.unchanged = detection.kept
        adoption.notes.append(f"dry run: would render {len(detection.added)} new file(s)")
        if merge_deps:
            plan = merge_template_dependencies(target, data, resolved_ref, apply=False)
            if plan is not None:
                adoption.deps = plan.as_dict()
                adoption.notes.extend(plan.notes)
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
    if merge_deps:
        run = _Run(target=target, backup=backup, data=data, ref=resolved_ref, created=created, before_dirs=before_dirs)
        _apply_dependency_merge(run, adoption)
    return adoption


def _apply_dependency_merge(run: _Run, adoption: Adoption) -> None:
    """Merge the generated dependencies in, or take the whole run back.

    The merge may only add requirements; `merge_problem` proves that, and a
    violation undoes the merge *and* the render, so a failed adoption still
    means "the project is exactly as it was".
    """
    target_pyproject = run.target / "pyproject.toml"
    before_pyproject = run.backup.get("pyproject.toml") or (
        target_pyproject.read_bytes() if target_pyproject.is_file() else None
    )
    merged = merge_template_dependencies(run.target, run.data, run.ref, apply=True)
    if merged is None:
        return
    adoption.deps = merged.as_dict()
    adoption.notes.extend(merged.notes)
    problem = merge_problem(target_pyproject, before_pyproject)
    if not problem:
        return
    if before_pyproject is not None:
        target_pyproject.write_bytes(before_pyproject)
    _roll_back(run.target, run.backup, run.created, run.before_dirs)
    adoption.ok = False
    adoption.applied = False
    adoption.error = f"dependency merge failed and was rolled back: {problem}"
    adoption.restored = [*adoption.restored, "pyproject.toml"]
    adoption.removed = run.created
    adoption.notes.append("rolled back: the project is unchanged")


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
    after = _declared_requirements(after_document)
    for name, raw in _declared_requirements(before_document).items():
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
    if not adoption.applied and adoption.error is None:
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
    parser.add_argument("--no-deps", action="store_true", help="do not merge the template's dependencies")
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
            merge_deps=not args.no_deps,
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
