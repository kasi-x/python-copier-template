#!/usr/bin/env python3
"""Merge the template's dependencies into an adopter's pyproject.toml.

The template generates a `pyproject.toml` with the runtime and dev
dependencies a project needs; when it is adopted into an existing project
that file is protected (it is the adopter's), so those dependencies used to
end up only in the adoption report — "wire these up yourself". This module
does the additive half of that by hand instead:

- **add what is missing, never touch what is there.** A dependency the
  adopter already declares keeps its own specifier, even when the template
  would pin something different; the difference is reported, not resolved.
- **never reorder or reformat anything else.** The file is edited through
  tomlkit, which round-trips comments and layout.
- **report instead of guessing** when the file has no table to merge into
  (`[project]` for PEP 621, `[tool.poetry]` for the legacy Poetry layout),
  or when it does not parse.

That is the boundary this stays on: no reconciliation of conflicting
constraints, no section-level rewriting of the adopter's configuration --
just the missing names, appended.

Usage (normally through tools/adopt.py, which is the transactional caller):

    python tools/pyproject_merge.py --target /path/to/pyproject.toml --source generated/pyproject.toml
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

import tomlkit

NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
REQUIREMENT = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?P<extras>\[[^\]]*\])?\s*(?P<spec>[^;]*?)(?P<marker>;.*)?$"
)


def canonical(spec: str) -> str:
    """The distribution name a requirement string refers to (PEP 503 style).

    `httpx>=0.27` -> `httpx`; `Foo_Bar[x,y]>=1` -> `foo-bar`. Used only to
    decide "is this already declared", so a false match costs a missing
    dependency (reported), never a modified one.
    """
    match = NAME.match(spec)
    if not match:
        return spec.strip()
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


@dataclass
class MergeResult:
    """What the merge added, kept, and refused to decide."""

    target: str
    style: str = "none"
    added: dict[str, list[str]] = field(default_factory=dict)
    kept: dict[str, list[str]] = field(default_factory=dict)
    differing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    applied: bool = False

    @property
    def added_names(self) -> list[str]:
        """Every dependency name that was added, in section order."""
        return [name for names in self.added.values() for name in names]

    def as_dict(self) -> dict[str, Any]:
        """Serializable form used by --json and tools/adopt.py."""
        return {
            "target": self.target,
            "style": self.style,
            "added": self.added,
            "kept": self.kept,
            "differing": self.differing,
            "notes": self.notes,
            "applied": self.applied,
        }


def _requirements(document: dict[str, Any], section: str) -> list[str]:
    """The PEP 508 requirement strings of one section of a parsed pyproject."""
    project = document.get("project")
    if not isinstance(project, dict):
        return []
    if section == "dependencies":
        entries = project.get("dependencies", [])
    elif section == "optional":
        return sorted(str(name) for name in project.get("optional-dependencies", {}))
    else:
        groups = document.get("dependency-groups")
        entries = groups.get(section, []) if isinstance(groups, dict) else []
    return [entry for entry in entries if isinstance(entry, str)]


def _source_requirements(source: dict[str, Any]) -> dict[str, list[str]]:
    """The template's dependencies, keyed by where they belong."""
    sections = {"runtime": _requirements(source, "dependencies"), "dev": _requirements(source, "dev")}
    return {name: entries for name, entries in sections.items() if entries}


def _to_poetry(requirement: str) -> tuple[str, str] | None:
    """`httpx>=0.27` -> `("httpx", ">=0.27")`, or None when that is not faithful.

    Poetry writes a plain specifier as the value; extras and environment
    markers need table syntax, so those requirements are reported instead of
    being guessed at.
    """
    match = REQUIREMENT.match(requirement)
    if not match or match.group("extras") or match.group("marker"):
        return None
    return match.group("name"), (match.group("spec").strip() or "*")


def _add_missing(
    target_section: Any,
    entries: list[str] | dict[str, str],
    result: MergeResult,
    section: str,
) -> None:
    """Append requirements the target does not declare; record what was kept.

    Two container shapes: a PEP 621 array of requirement strings, or a table
    (`name = "spec"`) as Poetry writes it. Only names that are absent are
    added, and a table key is never rewritten.
    """
    kept: list[str] = []
    added: list[str] = []
    if isinstance(entries, dict):
        present = {canonical(str(name)) for name in target_section}
        for name, value in entries.items():
            key = canonical(str(name))
            if key in present:
                kept.append(str(name))
                continue
            target_section[str(name)] = value
            present.add(key)
            added.append(str(name))
    else:
        present = {canonical(str(item)) for item in target_section}
        for entry in entries:
            key = canonical(entry)
            if key in present:
                kept.append(entry)
                continue
            target_section.append(entry)
            present.add(key)
            added.append(entry)
    if added:
        result.added[section] = added
    if kept:
        result.kept[section] = kept


def _differing(target_section: Any, template: list[str]) -> list[str]:
    """Names declared by both sides with a different requirement string."""
    declared = {canonical(str(item)): str(item) for item in target_section}
    out = []
    for entry in template:
        name = canonical(entry)
        if name in declared and declared[name].strip() != entry.strip():
            out.append(f"{name}: kept {declared[name]!r}, template wanted {entry!r}")
    return out


def _merge_pep621(document: Any, source: dict[str, Any], result: MergeResult) -> None:
    """PEP 621: `[project].dependencies` plus a PEP 735 dev group."""
    result.style = "pep621"
    project = document["project"]
    template = _source_requirements(source)
    runtime = template.get("runtime", [])
    if runtime:
        if "dependencies" not in project:
            project["dependencies"] = tomlkit.array()
        _add_missing(project["dependencies"], runtime, result, "runtime")
        result.differing += _differing(project["dependencies"], runtime)
    dev = template.get("dev", [])
    if dev:
        groups = document.get("dependency-groups")
        if groups is None:
            groups = tomlkit.table()
            document["dependency-groups"] = groups
            result.notes.append("created [dependency-groups] to hold the dev dependencies")
        if "dev" not in groups:
            groups["dev"] = tomlkit.array()
        _add_missing(groups["dev"], dev, result, "dev")
        result.differing += _differing(groups["dev"], dev)
    optional = _requirements(source, "optional")
    if optional:
        result.notes.append(f"optional extras not merged (opt in per project): {', '.join(optional)}")


def _merge_poetry(document: Any, source: dict[str, Any], result: MergeResult) -> None:
    """Legacy Poetry layout: dependencies live under `[tool.poetry]`."""
    result.style = "poetry"
    poetry = document["tool"]["poetry"]
    template = _source_requirements(source)
    translated: dict[str, dict[str, str]] = {"runtime": {}, "dev": {}}
    for section, table in translated.items():
        for requirement in template.get(section, []):
            converted = _to_poetry(requirement)
            if converted is None:
                result.notes.append(f"needs manual wiring (Poetry table syntax): {requirement}")
                continue
            table[converted[0]] = converted[1]
    if translated["runtime"]:
        if "dependencies" not in poetry:
            poetry["dependencies"] = tomlkit.table()
        _add_missing(poetry["dependencies"], translated["runtime"], result, "runtime")
    if translated["dev"]:
        group = poetry.get("group", {}).get("dev", {})
        table = group.get("dependencies") if isinstance(group, dict) else None
        if table is None:
            table = poetry.get("dev-dependencies")
        if table is None:
            result.notes.append("no [tool.poetry.group.dev.dependencies]; dev dependencies not merged")
        else:
            _add_missing(table, translated["dev"], result, "dev")


def merge_dependencies(target_path: Path, source_path: Path, *, apply: bool = True) -> MergeResult:
    """Add the template's missing dependencies to `target_path`.

    `apply=False` computes exactly the same result without writing; the caller
    (tools/adopt.py) uses that for its dry run and for its report.
    """
    result = MergeResult(target=str(target_path))
    if not target_path.is_file():
        result.notes.append(f"{target_path} does not exist; nothing to merge")
        return result
    if not source_path.is_file():
        result.notes.append(f"{source_path} does not exist; nothing to merge")
        return result

    try:
        document = tomlkit.parse(target_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  WHYNOT: tomlkit raises its own parse errors; the caller reports them.
        result.notes.append(f"{target_path} does not parse ({exc}); left untouched")
        return result
    try:
        source = tomllib.loads(source_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        result.notes.append(f"{source_path} does not parse ({exc}); nothing to merge")
        return result

    if isinstance(document.get("project"), dict):
        _merge_pep621(document, source, result)
    elif isinstance(document.get("tool"), dict) and "poetry" in document["tool"]:
        _merge_poetry(document, source, result)
    else:
        result.style = "none"
        template = _source_requirements(source)
        result.notes.append(
            "no [project] or [tool.poetry] table to merge into; add these by hand: "
            + ", ".join(template.get("runtime", []) + template.get("dev", []))
        )
        return result

    if not result.added_names:
        result.notes.append("every template dependency is already declared")
    if apply and (result.added_names or result.notes):
        target_path.write_text(tomlkit.dumps(document), encoding="utf-8")
        result.applied = True
    return result


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add the template's missing dependencies to a pyproject.toml.")
    parser.add_argument("--target", type=Path, required=True, help="the adopter's pyproject.toml")
    parser.add_argument(
        "--source", type=Path, required=True, help="the generated pyproject.toml to take dependencies from"
    )
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: merge (or report) and print what happened."""
    args = _parse_args(argv)
    result = merge_dependencies(args.target, args.source, apply=not args.dry_run)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
        return 0
    print(f"{args.target}: {result.style}")
    for section, names in result.added.items():
        print(f"  added {section}: {', '.join(names)}")
    for section, names in result.kept.items():
        print(f"  kept  {section}: {', '.join(names)}")
    for line in result.differing:
        print(f"  differs: {line}")
    for note in result.notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
