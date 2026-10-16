#!/usr/bin/env python3
"""Which generated files exist for which answers: questions/99-files.yml as data.

The table is copier's own input (copier.yml's `_exclude` turns every row whose
condition is false into an excluded path), so this module only reads it for
the tools that reason about the template without rendering it -- detect,
predicates, where. It never decides anything copier would decide differently.

A row is `<path>: {{ <condition> }}`, the path as it appears in the generated
project (a file or a directory; `{{ pkg_dir }}` is allowed). Rows inside a
`{% if X %} ... {% endif %}` block of the table apply only when X holds too;
the scope is kept with the row.

Usage:

    python architekton/file_gates.py              # the table, one row per line
    python architekton/file_gates.py --check      # every row names a path template/ has
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:  # architekton/ is no root package (pyproject.toml)
    sys.path.insert(0, str(TOP))

#: The table, relative to the repository root.
GATES_FILE = Path("questions") / "99-files.yml"

_ROW = re.compile(r"^\s+(?P<path>[^\s#][^:]*?):\s*\{\{\s*(?P<condition>.+?)\s*\}\}\s*$")
_SCOPE_OPEN = re.compile(r"^\s+\{%-?\s*if\s+(?P<condition>.+?)\s*-?%\}\s*$")
_SCOPE_CLOSE = re.compile(r"^\s+\{%-?\s*endif\s*-?%\}\s*$")
#: A template path segment whose condition stays in its name: `{% if C %}NAME{% endif %}`.
_NAMED_GATE = re.compile(
    r"^\{%-?\s*if\s+(?P<condition>.+?)\s*-?%\}(?P<name>.+?)\{%-?\s*endif\s*-?%\}(?P<suffix>\.jinja)?$"
)


@dataclass(frozen=True)
class Gate:
    """One row: `path` is generated only when `condition` (and `scope`, if any) holds."""

    path: str
    condition: str
    line: int
    scope: str | None = None

    @property
    def full_condition(self) -> str:
        """The row's condition with its enclosing block's, as one expression."""
        if self.scope is None:
            return self.condition
        return f"({self.scope}) and ({self.condition})"


def load(root: Path = TOP) -> list[Gate]:
    """Every row of `root`'s table, in file order; an empty list when the template has none."""
    path = root / GATES_FILE
    if not path.is_file():
        return []
    gates: list[Gate] = []
    scope: str | None = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if opened := _SCOPE_OPEN.match(line):
            scope = opened.group("condition")
        elif _SCOPE_CLOSE.match(line):
            scope = None
        elif row := _ROW.match(line):
            gates.append(Gate(path=row.group("path"), condition=row.group("condition"), line=number, scope=scope))
    return gates


def output_path(template_relpath: str) -> str:
    """A template/ path as the generated project names it, computed names kept as Jinja.

    `.jinja` is dropped from the last segment; a segment that keeps its own
    condition (`{% if pkg_scaffold %}{{ pkg_dir }}{% endif %}`) contributes
    just its name (`{{ pkg_dir }}`), which is how the table spells it.
    """
    parts = []
    for segment in Path(template_relpath).parts:
        named = _NAMED_GATE.match(segment)
        parts.append(named.group("name") + (named.group("suffix") or "") if named else segment)
    return "/".join(parts).removesuffix(".jinja")


def name_conditions(template_relpath: str) -> list[str]:
    """The conditions a template/ path still carries in its own segment names."""
    return [named.group("condition") for part in Path(template_relpath).parts if (named := _NAMED_GATE.match(part))]


def gates_for(template_relpath: str, gates: list[Gate]) -> list[Gate]:
    """The rows that decide whether this template/ path is generated: its own and its ancestors'."""
    output = output_path(template_relpath)
    return [gate for gate in gates if output == gate.path or output.startswith(gate.path + "/")]


def conditions_for(template_relpath: str, gates: list[Gate]) -> list[str]:
    """Every condition a template/ path is generated under: in its name, then in the table."""
    return [*name_conditions(template_relpath), *(gate.full_condition for gate in gates_for(template_relpath, gates))]


def stale_rows(root: Path = TOP) -> list[Gate]:
    """Rows whose path no file under template/ produces (a removed or renamed file)."""
    template = root / "template"
    sources = [path for path in template.rglob("*") if path.is_file() or path.is_symlink()]
    outputs = {output_path(path.relative_to(template).as_posix()) for path in sources}
    return [gate for gate in load(root) if not any(o == gate.path or o.startswith(gate.path + "/") for o in outputs)]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read questions/99-files.yml, the file-gate table.")
    parser.add_argument("--check", action="store_true", help="fail when a row names a path template/ does not have")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: print the table, or check it against template/."""
    args = _parse_args(argv)
    if args.check:
        stale = stale_rows()
        for gate in stale:
            print(f"{GATES_FILE}:{gate.line}: no file under template/ produces {gate.path}", file=sys.stderr)
        return 1 if stale else 0
    for gate in load():
        print(f"{gate.path:<44} {gate.full_condition}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
