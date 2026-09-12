#!/usr/bin/env python3
"""Append-only merge for the template's text files.

`.gitignore`, `justfile` and `Makefile` are the files an adopter almost always
already has, and they are line-oriented: appending the entries the template
has and they do not is safe, and their own lines are never rewritten. The
`pyproject.toml` merge (tools/pyproject_merge.py) is a different problem —
structured, and edited with a round-trip parser — so it lives in its own
module.

The rule for every kind is the same: **read what the target already declares,
append only what is missing, and report anything that cannot be appended
safely** (a `Taskfile.yml` is YAML, where appending text is not a thing;
Python task files need imports). Verification is the same for all of them:
the original content must still be a prefix of the new content.

Usage:
    python tools/file_merge.py --target .gitignore --source generated/.gitignore --kind gitignore
    python tools/file_merge.py --target Makefile --source generated/Makefile --kind makefile --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

import yaml

TOP = Path(__file__).resolve().parent.parent

GITIGNORE_HEADER = "# Added by python-copier-template (tools/adopt.py)"
MAKEFILE_TARGET = re.compile(r"^(?P<name>[A-Za-z0-9_.][A-Za-z0-9_.-]*)\s*:(?!=)")
JUST_RECIPE = re.compile(r"^(?P<name>[a-zA-Z_][a-zA-Z0-9_-]*)(?P<rest>\s+[^:]*)?:")
IGNORED_JUST_NAMES = frozenset({"alias", "export", "import", "mod", "set", "unexport"})


class FileMergeError(Exception):
    """The merge cannot be carried out for this kind."""


@dataclass
class TextMerge:
    """What was appended, and what was left for the adopter."""

    path: str
    kind: str
    added: list[str] = field(default_factory=list)
    reported: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    applied: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Serializable form used by --json and tools/adopt.py."""
        return {
            "path": self.path,
            "kind": self.kind,
            "added": self.added,
            "reported": self.reported,
            "notes": self.notes,
            "applied": self.applied,
        }


def _prefix(existing_text: str) -> str:
    """The original content, newline-terminated, plus a blank line if non-empty."""
    if not existing_text:
        return ""
    return existing_text if existing_text.endswith("\n") else existing_text + "\n"


def _lines(entries: list[str]) -> str:
    return "\n".join(entries) + "\n"


def _non_comment_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def _declared_gitignore(text: str) -> set[str]:
    return {line.strip() for line in _non_comment_lines(text)}


def _recipe_blocks(text: str, pattern: re.Pattern[str], *, skip: frozenset[str] = frozenset()) -> dict[str, str]:
    """Named block of a line-oriented build file: name -> the block's text.

    A block runs from its name line to the line before the next name line, so
    appending it keeps its body (commands, dependencies) intact.
    """
    lines = text.splitlines()
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match and match.group("name") not in skip:
            starts.append((index, match.group("name")))
    blocks: dict[str, str] = {}
    for position, (index, name) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        blocks.setdefault(name, "\n".join(lines[index:end]).rstrip("\n"))
    return blocks


def merge_gitignore(target_path: Path, source_path: Path, *, apply: bool = True) -> TextMerge:
    """Append the ignore patterns the target does not already have."""
    result = TextMerge(path=str(target_path), kind="gitignore")
    if not source_path.is_file():
        result.notes.append(f"{source_path} does not exist; nothing to merge")
        return result
    existing_text = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
    declared = _declared_gitignore(existing_text)
    missing = [line.strip() for line in _non_comment_lines(source_path.read_text(encoding="utf-8"))]
    result.added = [line for line in missing if line not in declared]
    if not result.added:
        result.notes.append("every template ignore pattern is already present")
        return result
    if apply:
        target_path.write_text(f"{_prefix(existing_text)}{GITIGNORE_HEADER}\n{_lines(result.added)}", encoding="utf-8")
        result.applied = True
    return result


def merge_recipes(target_path: Path, source_path: Path, kind: str, *, apply: bool = True) -> TextMerge:
    """Append the build-file recipes (make target / just recipe) that are missing."""
    result = TextMerge(path=str(target_path), kind=kind)
    if not source_path.is_file():
        result.notes.append(f"{source_path} does not exist; nothing to merge")
        return result
    pattern = MAKEFILE_TARGET if kind == "makefile" else JUST_RECIPE
    skip = frozenset() if kind == "makefile" else IGNORED_JUST_NAMES
    existing_text = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
    declared = set(_recipe_blocks(existing_text, pattern, skip=skip))
    blocks = _recipe_blocks(source_path.read_text(encoding="utf-8"), pattern, skip=skip)
    missing = {name: block for name, block in blocks.items() if name not in declared}
    if not missing:
        result.notes.append(f"every template {kind} entry is already present")
        return result
    result.added = sorted(missing)
    if apply:
        header = "# Added by python-copier-template (tools/adopt.py)"
        body = "\n\n".join(missing[name] for name in sorted(missing))
        target_path.write_text(f"{_prefix(existing_text)}{header}\n\n{body}\n", encoding="utf-8")
        result.applied = True
    return result


def _tasks_are_the_last_block(target_text: str) -> bool:
    """True when `tasks:` is the final top-level key, so blocks can be appended."""
    top_level = [line for line in target_text.splitlines() if line and not line[0].isspace() and ":" in line]
    return bool(top_level) and top_level[-1].split(":")[0].strip() == "tasks"


def _taskfile_tasks(text: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return {}
    tasks = document.get("tasks") if isinstance(document, dict) else None
    return tasks if isinstance(tasks, dict) else {}


def merge_taskfile(target_path: Path, source_path: Path, *, append: bool = False) -> TextMerge:
    """Report the tasks a YAML task file is missing — and append them when asked.

    YAML is not append-friendly in general, so this is report-only unless the
    caller approves: `tasks:` must be the target's last top-level key, and the
    edit is verified by re-parsing (every task that was there must still be
    there, unchanged, and the new ones must parse). Anything else stays a
    report.
    """
    result = TextMerge(path=str(target_path), kind="taskfile")
    if not source_path.is_file():
        result.notes.append(f"{source_path} does not exist; nothing to merge")
        return result
    pattern = re.compile(r"^  (?P<name>[A-Za-z0-9_.-]+):")
    target_text = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
    declared = set(_recipe_blocks(target_text, pattern))
    blocks = _recipe_blocks(source_path.read_text(encoding="utf-8"), pattern)
    missing = {name: block for name, block in blocks.items() if name not in declared}
    if not missing:
        result.notes.append("every template task is already present")
        return result
    if not append or not _tasks_are_the_last_block(target_text):
        result.reported = sorted(missing)
        if not append:
            reason = "reported rather than appended"
        elif not _tasks_are_the_last_block(target_text):
            reason = "not appended: tasks: is not the last block in the file"
        else:
            reason = "not appended"
        result.notes.append(f"these are YAML tasks, {reason}; copy the ones you want from the generated Taskfile.yml")
        return result

    before = _taskfile_tasks(target_text)
    appended = target_text if target_text.endswith("\n") else target_text + "\n"
    appended += "\n".join(blocks[name] for name in sorted(missing)) + "\n"
    target_path.write_text(appended, encoding="utf-8")
    after = _taskfile_tasks(appended)
    if not all(name in after and after[name] == value for name, value in before.items()):
        target_path.write_text(target_text, encoding="utf-8")
        result.notes.append("appending the tasks changed an existing one; undone")
        result.reported = sorted(missing)
        return result
    result.added = sorted(missing)
    result.applied = True
    return result


CI_JOB = re.compile(r"^  (?P<name>[A-Za-z0-9_.-]+):")
CI_CALLER_NAME = "copier-ci.yml"
CI_SAFE_REUSABLES = ("_tasks.yml", "_test.yml", "_hygiene.yml")
CI_EXCLUDED_NOTE = (
    "the dist/release/pypi and docs jobs are not copied: they publish artifacts, releases or "
    "GitHub Pages, and a second publisher is the one thing worse than none"
)


def ci_caller(source_text: str) -> tuple[str, list[str], list[str]]:
    """(caller workflow, kept jobs, dropped jobs) for an adopter who has their own ci.yml.

    Built by textual surgery on the generated workflow rather than a YAML
    round-trip: PyYAML (YAML 1.1) reads the `on:` key as the boolean true, so
    re-dumping it produces `true:` and an invalid workflow. Cutting job blocks
    out of the original text also keeps the generated formatting intact.
    """
    head, separator, rest = source_text.partition("\njobs:\n")
    if not separator:
        msg = "the generated ci.yml has no jobs: block"
        raise FileMergeError(msg)
    blocks = _recipe_blocks(rest, CI_JOB, skip=frozenset({"required-checks-passed"}))
    kept = [
        name
        for name, block in blocks.items()
        if any(f"uses: ./.github/workflows/{reusable}" in block for reusable in CI_SAFE_REUSABLES)
    ]
    dropped = sorted(name for name in blocks if name not in kept)
    caller = "\n".join([head.replace("name: CI", "name: Copier CI", 1), "jobs:", ""])
    caller += "\n\n".join(blocks[name] for name in sorted(kept)) + "\n"
    return caller, sorted(kept), dropped


def merge_ci_caller(target: Path, source_ci: Path, *, apply: bool = True) -> TextMerge:
    """Add the template's checks as a second workflow, leaving theirs alone.

    A separate file rather than an edit of theirs: workflow files are YAML
    with comments, and the template's jobs cannot be merged into a workflow
    that already exists without either reformatting it or guessing which
    triggers should run them.
    """
    result = TextMerge(path=str(target / ".github" / "workflows" / CI_CALLER_NAME), kind="ci")
    if not source_ci.is_file():
        result.notes.append(f"{source_ci} does not exist; no CI caller added")
        return result
    try:
        caller, kept, dropped = ci_caller(source_ci.read_text(encoding="utf-8"))
    except FileMergeError as exc:
        result.notes.append(str(exc))
        return result
    destination = target / ".github" / "workflows" / CI_CALLER_NAME
    if destination.exists():
        result.notes.append(f"{destination.name} already exists; left alone")
        return result
    result.added = kept
    result.reported = dropped
    result.notes.append(CI_EXCLUDED_NOTE)
    result.notes.append(f"runs alongside your own ci.yml; delete whichever you do not want ({destination.name})")
    if apply:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(caller, encoding="utf-8")
        result.applied = True
    return result


def merge_text_file(
    target_path: Path,
    source_path: Path,
    kind: str,
    *,
    apply: bool = True,
    append_yaml: bool = False,
) -> TextMerge:
    """Dispatch to the merge for `kind` (`gitignore`, `makefile`, `justfile`, `taskfile`)."""
    if kind == "gitignore":
        return merge_gitignore(target_path, source_path, apply=apply)
    if kind in ("makefile", "justfile"):
        return merge_recipes(target_path, source_path, kind, apply=apply)
    if kind == "taskfile":
        return merge_taskfile(target_path, source_path, append=append_yaml and apply)
    msg = f"unknown kind: {kind!r}"
    raise FileMergeError(msg)


def original_is_preserved(before: bytes, after: bytes) -> bool:
    """The invariant of every kind here: the old content is still a prefix."""
    return after.startswith(before)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append the missing entries of a template text file.")
    parser.add_argument("--target", type=Path, required=True, help="the adopter's file")
    parser.add_argument("--source", type=Path, required=True, help="the generated file to take entries from")
    parser.add_argument("--kind", required=True, choices=["gitignore", "makefile", "justfile", "taskfile"])
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: merge (or report) and print what happened."""
    args = _parse_args(argv)
    result = merge_text_file(args.target, args.source, args.kind, apply=not args.dry_run)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
        return 0
    print(f"{args.target}: {result.kind}")
    if result.added:
        print(f"  added: {', '.join(result.added)}")
    if result.reported:
        print(f"  reported: {', '.join(result.reported)}")
    for note in result.notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
