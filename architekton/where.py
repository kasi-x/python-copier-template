#!/usr/bin/env python3
"""Where to edit: every file a question (or derived value) touches, in one report.

The template is large -- dozens of areas, hundreds of payload files -- but a
change usually starts from one setting: "I want to change what the task
runner question does". This tool answers "which files is that?" so nobody
has to know the layout first:

- **defined**: the questions/ file and line that declares the name, with the
  first line of its help text.
- **feeds**: the derived values (`when: false` internals) that read it,
  transitively -- a template file gated on `runner_just` is still a
  `task_runner` file.
- **which files exist**: the rows of `questions/99-files.yml` whose
  condition reads the name or anything it feeds (with their line numbers:
  that is where to edit), plus the few template/ paths that keep their
  condition in their computed name.
- **template / partials**: payload files whose *Jinja code* reads the name
  or anything it feeds. Only Jinja
  code is scanned (`{{ ... }}` / `{% ... %}`), never prose, so a short name
  like `docs` matches where the template branches on it, not every sentence
  that mentions documentation.
- **presets / tests / docs**: where the name itself is spelled out.

It reuses the question graph (`architekton/question_graph.py`) for the
definitions and their when/default edges -- no second questionnaire parser.

Usage:

    python architekton/where.py task_runner     # the human report
    python architekton/where.py sentry          # a fragment: picks include_sentry, or lists candidates
    python architekton/where.py docs_type --json
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:  # architekton/ is no root package (pyproject.toml)
    sys.path.insert(0, str(TOP))

from architekton import file_gates  # noqa: E402
from architekton import question_graph  # noqa: E402
from architekton import questionnaire  # noqa: E402
from architekton import when_model  # noqa: E402

#: The internal that holds questions/99-files.yml's table.
TABLE_NAME = "file_gates"

#: The payload trees: the generated project and the partials it includes.
PAYLOAD_ROOT = "template"
PARTIAL_ROOT = "partials"

#: Where a name is spelled out rather than branched on.
PRESET_GLOB = "presets/*.yml"
TEST_GLOBS = ("tests/**/*.py", "tests/matrix/*.yml")
DOC_GLOBS = ("README.md", "CONTRIBUTING.md", "docs/**/*.md")

#: What to run after editing each kind of file (the blast-radius table in CONTRIBUTING.md).
NEXT_STEPS = {
    "questions": "edited the question (questions/)?    task regen && task test-fast",
    "payload": "edited a generated file or partial?  task test-fast && task verify-delta",
}


class WhereError(Exception):
    """The name does not identify one question or derived value."""


@dataclass
class Touchpoints:
    """Everything one name touches, grouped by what kind of edit it is."""

    name: str
    kind: str  # question_graph.QUESTION or question_graph.INTERNAL
    defined: str  # questions/NN-area.yml:LINE
    summary: str  # first line of the help text ("" for internals)
    feeds: list[str] = field(default_factory=list)  # derived values that read it, transitively
    read_by: list[str] = field(default_factory=list)  # asked questions whose when/default read it
    file_gated: list[str] = field(default_factory=list)  # payload paths that exist only conditionally on it
    content: list[str] = field(default_factory=list)  # payload files whose Jinja code reads it
    partials: list[str] = field(default_factory=list)
    presets: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)


def resolve(name: str, graph: question_graph.Graph) -> str:
    """Map user input to one definition name: exact, else a unique substring match."""
    names = [node.name for node in graph.nodes]
    if name in names:
        return name
    partial = [candidate for candidate in names if name.lower() in candidate.lower()]
    if len(partial) == 1:
        return partial[0]
    if partial:
        msg = f"{name!r} matches several settings: {', '.join(partial)}"
        raise WhereError(msg)
    close = difflib.get_close_matches(name, names, n=5, cutoff=0.6)
    hint = f" Did you mean: {', '.join(close)}?" if close else " `python architekton/questionnaire.py` lists them all."
    msg = f"no question or derived value named {name!r}.{hint}"
    raise WhereError(msg)


def _closure(name: str, graph: question_graph.Graph) -> tuple[list[str], list[str]]:
    """(derived values that read `name` transitively, asked questions that read any of them)."""
    dependents = graph.dependents()
    kinds = {node.name: node.kind for node in graph.nodes}
    order = {node.name: node.order for node in graph.nodes}
    feeds: set[str] = set()
    read_by: set[str] = set()
    frontier = [name]
    while frontier:
        current = frontier.pop()
        for reader in dependents.get(current, []):
            if kinds[reader] == question_graph.INTERNAL:
                if reader not in feeds and reader != name:
                    feeds.add(reader)
                    frontier.append(reader)
            elif reader != name:
                read_by.add(reader)
    feeds.discard(TABLE_NAME)  # the file table reads everything; its rows are reported on their own
    return sorted(feeds, key=order.__getitem__), sorted(read_by, key=order.__getitem__)


def jinja_reads(text: str) -> set[str]:
    """The identifiers the Jinja code in `text` reads (when_model skips `${{ }}` and raw blocks)."""
    return when_model.jinja_identifiers(text)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""  # a binary asset or a dangling symlink: no Jinja to read


def _payload_files(root: Path) -> list[Path]:
    """Every file under the payload tree (symlinked files included, in a stable order)."""
    return sorted(path for path in root.rglob("*") if path.is_file())


def _scan_payload(top: Path, watched: set[str], hits: Touchpoints) -> None:
    # Which files exist: the .gate markers that generate questions/99-files.yml,
    # plus the few template/ paths that keep their condition in their (computed)
    # name. Row line numbers point at the generated table; the marker is what
    # you actually edit, so report its path instead.
    template = top / PAYLOAD_ROOT
    hits.file_gated = []
    for gate in file_gates.load(top):
        if not (jinja_reads("{{ " + gate.full_condition + " }}") & watched):
            continue
        rel = gate.path.replace("{{ pkg_dir }}", "{% if pkg_scaffold %}{{ pkg_dir }}{% endif %}")
        markers = [template / f"{rel}.gate", template / rel / ".gate"]
        marker = next((m for m in markers if m.exists()), None)
        hits.file_gated.append(
            f"{marker.relative_to(top).as_posix()}:1  {gate.path}"
            if marker
            else f"{file_gates.GATES_FILE.as_posix()}:{gate.line}  {gate.path}"
        )
    for path in _payload_files(template):
        relative = path.relative_to(top).as_posix()
        if jinja_reads(path.relative_to(template).as_posix()) & watched:
            hits.file_gated.append(relative)
        if jinja_reads(_read_text(path)) & watched:
            hits.content.append(relative)
    hits.partials = [
        path.relative_to(top).as_posix()
        for path in _payload_files(top / PARTIAL_ROOT)
        if jinja_reads(_read_text(path)) & watched
    ]


def _spelled_out(top: Path, globs: tuple[str, ...], pattern: re.Pattern[str]) -> list[str]:
    found = {path for glob in globs for path in top.glob(glob) if path.is_file() and pattern.search(_read_text(path))}
    return sorted(path.relative_to(top).as_posix() for path in found)


def touchpoints(name: str, top: Path = TOP) -> Touchpoints:
    """Every file `name` touches. `name` may be a fragment of the real name (see `resolve`)."""
    graph = question_graph.build_graph()
    resolved = resolve(name, graph)
    node = graph.by_name[resolved]
    by_name = questionnaire.questions_by_name()
    help_text = by_name[resolved].help.strip()
    feeds, read_by = _closure(resolved, graph)
    hits = Touchpoints(
        name=resolved,
        kind=node.kind,
        defined=f"{node.fragment}:{node.line}",
        summary=help_text.splitlines()[0] if help_text else "",
        feeds=feeds,
        read_by=read_by,
    )
    _scan_payload(top, {resolved, *feeds}, hits)

    escaped = re.escape(resolved)
    hits.presets = _spelled_out(top, (PRESET_GLOB,), re.compile(rf"(?m)^{escaped}\s*:"))
    # Quoted, assigned or keyed spellings only: a bare word match would make
    # every test that says "docs" a docs_type test.
    named = re.compile(rf"""["'`]{escaped}["'`=]|\b{escaped}\s*[:=]|--{escaped}\b""")
    hits.tests = _spelled_out(top, TEST_GLOBS, named)
    hits.docs = _spelled_out(top, DOC_GLOBS, re.compile(rf"`{escaped}(?:[ =`]|\b)"))
    return hits


def _section(title: str, entries: list[str], *, limit: int) -> list[str]:
    if not entries:
        return []
    lines = [f"{title} ({len(entries)})"]
    lines += [f"  {entry}" for entry in entries[:limit]]
    if len(entries) > limit:
        lines.append(f"  ... and {len(entries) - limit} more (--all shows every file)")
    return [*lines, ""]


def report(hits: Touchpoints, *, limit: int = 12) -> str:
    """The human report: one screen, most specific places first."""
    kind = "question" if hits.kind == question_graph.QUESTION else "derived value (never asked)"
    lines = [f"{hits.name} — {kind}", f"  defined in  {hits.defined}"]
    if hits.summary:
        lines.append(f"  asks        {hits.summary}")
    if hits.feeds:
        lines.append(f"  feeds       {', '.join(hits.feeds)}")
    if hits.read_by:
        lines.append(f"  read by     {', '.join(hits.read_by)} (asked questions whose `when` or `default` reads it)")
    lines.append("")
    lines += _section("Which files exist (edit the condition here)", hits.file_gated, limit=limit)
    lines += _section("Generated files whose content depends on it", hits.content, limit=limit)
    lines += _section("Snippets the generated files include (partials/)", hits.partials, limit=limit)
    lines += _section("Presets that set it", hits.presets, limit=limit)
    lines += _section("Tests that name it", hits.tests, limit=limit)
    lines += _section("Docs that name it", hits.docs, limit=limit)
    lines.append("Then run:")
    lines.append(f"  {NEXT_STEPS['questions']}")
    if hits.file_gated or hits.content or hits.partials:
        lines.append(f"  {NEXT_STEPS['payload']}")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show every file a question or derived value touches.")
    parser.add_argument("name", help="question or derived-value name, or a fragment of one (e.g. sentry)")
    parser.add_argument("--json", action="store_true", help="print the machine report")
    parser.add_argument("--all", action="store_true", help="list every file instead of the first few per group")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: print where NAME is defined, what it feeds and which files read it."""
    args = _parse_args(argv)
    try:
        hits = touchpoints(args.name)
    except WhereError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(asdict(hits), indent=2))
    else:
        print(report(hits, limit=sys.maxsize if args.all else 12))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
