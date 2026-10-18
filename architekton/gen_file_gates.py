#!/usr/bin/env python3
"""Regenerate questions/99-files.yml's `file_gates` table from template/.gate files.

A `.gate` file declares the existence condition for the path it sits beside:

- `template/x.gate`           -> `x` exists only when its condition holds
- `template/dir/.gate`        -> the whole `dir` subtree exists under it

The file contains the condition on its own line; `#`-lines above it are
carried into the table as provenance comments (conventionally
`# from: questions/NN-<area>.yml`). A path with no `.gate` is unconditional --
"no marker, no condition" is the rule that makes adding a file never require
touching a second file.

Paths computed from answers keep their condition in the file *name* instead
(`{{ pkg_dir }}`, the uv.lock / pixi.lock switch, the `src/` sub-trees): those
carry no `.gate`, and copier drops the name when its `{% if %}` renders empty.

This script is the only writer of questions/99-files.yml's `default:` block.
Run it after adding/moving/renaming a `.gate` file (or use `task regen`);
`architekton/file_gates.py --check` then verifies every row still names a
path template/ actually has.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:  # architekton/ is no root package (pyproject.toml)
    sys.path.insert(0, str(TOP))
from architekton.file_gates import output_path  # noqa: E402

TEMPLATE = TOP / "template"
TABLE = TOP / "questions" / "99-files.yml"

HEADER = """\
# Which generated files exist for which answers -- GENERATED from the .gate
# files under template/ by `architekton/gen_file_gates.py` (`task regen`).
# Do not edit the rows below by hand; change the `.gate` file that sits beside
# the path instead.
#
# One row per gated path in the generated project: `<path>: {{ <condition> }}`.
# The path -- a file, or a whole directory -- is generated only when the
# condition is true; anything not listed is always generated (if its source
# exists under template/). A condition can use any question or derived value
# (questions/90-derived.yml). To add a file that only some projects get, put
# it under template/ with its plain name and add `<name>.gate` beside it (or
# `.gate` inside it, for a whole directory) holding its condition.
#
# Two kinds of paths keep their condition in the file name instead: names
# that are computed from answers (`{{ pkg_dir }}`, the uv.lock / pixi.lock
# switch), and the src/ sub-trees, which several project types fill.
#
# Next: copier.yml's `_exclude` turns every row whose condition is false into
# an excluded path; what the remaining files contain is template/ (and the
# snippets in partials/). `task where -- <setting>` shows a row in context;
# after editing, `task test-fast` (tests/test_file_gates.py checks the rows).
"""

GATE_SUFFIX = ".gate"
JINJA_SUFFIX = ".jinja"


def gate_rows() -> list[tuple[str, list[str], str]]:
    """Every gated path as (table path, comment lines, condition)."""
    rows: list[tuple[str, list[str], str]] = []
    for gate in sorted(TEMPLATE.rglob("*" + GATE_SUFFIX)):
        rel = gate.relative_to(TEMPLATE)
        if gate.name == GATE_SUFFIX:  # dir/.gate gates the directory itself
            table_path = output_path(rel.parent.as_posix())
        else:
            stripped = rel.as_posix()[: -len(GATE_SUFFIX)]
            stripped = stripped.removesuffix(JINJA_SUFFIX)
            table_path = output_path(stripped)
        comments: list[str] = []
        condition = ""
        for line in gate.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                comments.append(line)
            elif line.strip():
                if condition:
                    sys.exit(f"{gate}: a .gate file holds exactly one condition line")
                condition = line.strip()
        if not condition:
            sys.exit(f"{gate}: empty .gate file -- write the condition, or delete it for unconditional")
        rows.append((table_path, comments, condition))
    return rows


def render_table() -> str:
    """The complete questions/99-files.yml contents.

    Rows under `{{ pkg_dir }}` sit in `{% if pkg_scaffold %}` blocks so the
    computed package name is only interpolated where it can render (the same
    scoping the handwritten table used).
    """
    lines = [HEADER, "file_gates:", "    type: yaml", "    when: false", "    default: |"]
    scoped = False
    for path, comments, condition in gate_rows():
        want_scope = path.startswith("{{ pkg_dir }}")
        if want_scope and not scoped:
            lines.append("        {% if pkg_scaffold %}")
            scoped = True
        elif not want_scope and scoped:
            lines.append("        {% endif %}")
            scoped = False
        lines.extend(f"        {comment}" for comment in comments)
        lines.append(f"        {path}: {{{{ {condition} }}}}")
    if scoped:
        lines.append("        {% endif %}")
    return "\n".join(lines) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail when the committed table differs from a regeneration"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    want = render_table()
    if args.check:
        have = TABLE.read_text(encoding="utf-8") if TABLE.exists() else ""
        if have != want:
            print(f"{TABLE}: stale -- regenerate with `python architekton/gen_file_gates.py`", file=sys.stderr)
            return 1
        print(f"{TABLE}: up to date with template/.gate files")
        return 0
    TABLE.write_text(want, encoding="utf-8")
    print(f"wrote {TABLE} from {len(gate_rows())} .gate files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
