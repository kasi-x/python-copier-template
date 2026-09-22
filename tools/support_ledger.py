"""The declared support contract (`support.yml`): the reader and its doc renderer.

`support.yml` is the human-approved declaration of which witness-leaf
combinations this template keeps working, at which verification tier, and
with what measured evidence (`why`). Two consumers read it, so the reading
and the table rendering live in one place (TODO.md §28.5 R5): the docs
generator (tools/gen_docs.py renders the catalogue's compact summary and the
full `docs/reference/support.md` from it) and the MCP server (the
`template://support` resource). tests/test_support_matrix.py keeps the
declaration honest against the witness ledger.

This is a foundations-layer module by the tests/test_tool_layers.py table:
one file in, markdown text out -- no template tree, no subprocess.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

SUPPORT_YML = TOP / "support.yml"
"""The declared support contract (W4 owns the file; no file, no blocks)."""

SUPPORT_DOC = TOP / "docs" / "reference" / "support.md"
"""The generated full-matrix reference page."""

SECTIONS = ("supported", "best_effort", "tier_policy")
"""The sections a full rendering needs, in page order."""


class SupportLedgerError(Exception):
    """`support.yml` is missing, malformed, or has a hole a renderer needs."""


def load_support(path: Path = SUPPORT_YML) -> dict[str, Any]:
    """Read `support.yml`."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"{path.name} must hold a mapping"
        raise SupportLedgerError(msg)
    return data


def support_section(support: dict[str, Any], key: str) -> list[Any]:
    """One `support.yml` section, validated as a non-empty list of mappings."""
    rows = support.get(key)
    if not isinstance(rows, list) or not rows:
        msg = f"support.yml has no non-empty `{key}:` list"
        raise SupportLedgerError(msg)
    return rows


def cell(text: str) -> str:
    """A markdown table cell: one line, no unescaped pipes."""
    return " ".join(text.split()).replace("|", "\\|")


def _support_cell(value: Any) -> str:
    """One support-matrix cell."""
    if isinstance(value, list):
        return ", ".join(f"`{item}`" for item in value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "—"
    return f"`{value}`"


def matrix_rows(rows: list[Any], *, drop: tuple[str, ...] = (), plain: tuple[str, ...] = ()) -> str:
    """One markdown table over `rows`, deriving its columns from their keys.

    `drop` removes keys that belong in the full reference but not in a
    summary: the catalogue keeps one row per combination, while the `why`
    column (the measured evidence) lives in `docs/reference/support.md`.

    `plain` columns are prose cells, rendered without the code-span wrapping
    `_support_cell` gives identifiers (`why` quotes commands and paths). The
    questionnaire tables (tools/gen_docs.py) reuse this renderer so the whole
    docs surface has one table vocabulary.
    """
    columns: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            msg = "every support entry must be a mapping"
            raise SupportLedgerError(msg)
        columns += [str(key) for key in row if str(key) not in columns and str(key) not in drop]
    if not columns:
        msg = "a support section has no columns to render"
        raise SupportLedgerError(msg)
    lines = [f"| {' | '.join(columns)} |", f"|{'---|' * len(columns)}"]
    for row in rows:
        cells = [
            cell(str(row.get(column))) if column in plain else cell(_support_cell(row.get(column)))
            for column in columns
        ]
        lines.append(f"| {' | '.join(cells)} |")
    return "\n".join(lines)


def render_support_table(support: dict[str, Any], *, full_link: str) -> str:
    """The catalogue's compact support summary, from `support.yml`.

    One row per combination and no `why` column: the full matrix and its
    evidence live in `docs/reference/support.md`, which the summary links to
    (`full_link`, already relative to the page the summary is generated into).
    The columns are the entry keys, in the order the file writes them, so the
    table follows whatever shape W4 settles on instead of pinning one here.
    """
    blocks = [
        "**Supported** — executed end to end by CI:",
        "",
        matrix_rows(support_section(support, "supported"), drop=("why",)),
    ]
    best_effort = support.get("best_effort")
    if best_effort is not None:
        blocks += [
            "",
            "**Best effort** — rendered by CI, but never executed:",
            "",
            matrix_rows(support_section(support, "best_effort"), drop=("why",)),
        ]
    blocks += ["", f"Full matrix and the evidence behind each tier: [{full_link}]({full_link})."]
    return "\n".join(blocks)


def render_support_doc(support: dict[str, Any]) -> str:
    """`docs/reference/support.md`: the full support matrix, prose included."""
    sections = {key: support_section(support, key) for key in SECTIONS}
    lines = [
        "Every combination this template keeps working, the tier that guarantees",
        "it, and the measured evidence behind that tier.",
        "",
        "## Supported",
        "",
        "Executed end to end in CI by the witness full tier: `uv sync`, the",
        "generated project's own pytest, basedpyright and its docs build.",
        f"Measured at ~3 minutes per leaf, so only these {len(sections['supported'])} run it.",
        "",
        matrix_rows(sections["supported"], plain=("why",)),
        "",
        "## Best effort",
        "",
        "Declared so the questionnaire's existing answers keep rendering, but",
        "never executed by CI. The witness fast tier renders and ruff-checks",
        "these leaves (272 renders at ~1.3 s each, 10-20 s in parallel); a",
        "regression that only breaks install or run is not caught there.",
        "",
        matrix_rows(sections["best_effort"], plain=("why",)),
        "",
        "## Tier policy",
        "",
        "Which tier each class of witness leaf is declared for. `none` is",
        "reserved for a future W4 exclusion: it is declared as `tier: none`",
        "plus a `reason` in `tests/matrix/witnesses.json`, and no leaf uses it",
        "today because every declared leaf has a recorded fast-tier run.",
        "",
        matrix_rows(sections["tier_policy"], plain=("why",)),
    ]
    return "\n".join(lines)
