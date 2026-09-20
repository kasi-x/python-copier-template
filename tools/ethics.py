"""Loader for the ethics/regional/operational sections (_shared/ethics/).

_shared/ethics/REGISTRY.yml is the single source for the accumulated rule
sections; tests/test_ethics_registry.py pins the file format (row shape,
header agreement, draft isolation). This module is the *presentation* reader
for tooling -- currently the MCP server -- so a caller can ask which rules a
piece of text trips without re-parsing the registry's conventions (the
`設定側トリガー` presence-trigger span, the h1 marker, the active/kind
lifecycle).

Every row's file documents its presence trigger (the backticked `(?i)` regex
after `設定側トリガー` in 運用チェック), which is what `match()` scans with;
tests/test_ethics_registry.py holds that contract, so a row without the span
fails there instead of silently vanishing from `match()` results here.
"""

from __future__ import annotations

import re
from datetime import date
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

TOP = Path(__file__).resolve().parent.parent
ETHICS = TOP / "_shared" / "ethics"
REGISTRY = ETHICS / "REGISTRY.yml"

# The presence trigger each section's 運用チェック documents: the first
# backticked `(?i)` regex after the 設定側トリガー label (every section puts
# the span on the line following the label; the bounded window keeps the
# search inside that block). kyushu's label carries a stray space inside the
# parenthesis; tolerate it.
_PRESENCE_RE = re.compile(r"設定側トリガー[^:\n]*:[\s\S]{0,80}?`(\(\?i\)[^`]+)`")
_TITLE_RE = re.compile(r"^# (.+)$", re.MULTILINE)


def load_registry() -> list[dict[str, Any]]:
    """The registry rows (version 1), in declaration order."""
    payload = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    assert payload.get("version") == 1, "registry version must be 1"
    return list(payload["sections"])


def section_path(row: dict[str, Any]) -> Path:
    """The section file's path, resolved from its registry row."""
    return TOP / str(row["file"])


def section_body(row: dict[str, Any]) -> str:
    """The section's markdown, jinja comment header stripped."""
    text = section_path(row).read_text(encoding="utf-8")
    return text.split("#}", 1)[-1].lstrip("\n") if "{#" in text else text


def section_title(row: dict[str, Any]) -> str:
    """The section's h1 title line (the marker the AGENTS.md appendix renders)."""
    match = _TITLE_RE.search(section_body(row))
    return match.group(1) if match else ""


def presence_trigger(row: dict[str, Any]) -> str:
    """The row's documented presence-trigger regex (`設定側トリガー` span).

    Raises KeyError when missing: the registry test pins every row to carry
    one, so a miss here means the contract broke elsewhere.
    """
    match = _PRESENCE_RE.search(section_path(row).read_text(encoding="utf-8"))
    if match is None:
        missing = f"{row['id']}: no 設定側トリガー span documented"
        raise KeyError(missing)
    return match.group(1)


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    """The row with YAML-parsed dates (effective / review_by) as ISO strings."""
    return {key: value.isoformat() if isinstance(value, (date, datetime)) else value for key, value in row.items()}


def inventory() -> dict[str, Any]:
    """The whole registry as a deterministic JSON-ready dict.

    Rows carry their summary fields and their presence trigger, so a caller
    can see the enforcement ladder (L0 doc / L1 presence assert / L2 gate)
    without reading the section files.
    """
    rows = [dict(_jsonable(row), trigger=presence_trigger(row)) for row in load_registry()]
    return {"registry": str(REGISTRY.relative_to(TOP)), "count": len(rows), "sections": rows}


def match(text: str) -> list[dict[str, Any]]:
    """The sections whose presence trigger hits `text`, strongest first.

    Every row participates -- a draft hit is worth surfacing (the kyushu
    denylist identifiers must warn even while the section is undistributed) --
    with `status`/`enforcement` in the entry so the caller can weigh it.
    Ordered L2 before L1 before L0, then declaration order.
    """
    matched = [
        {
            "id": row["id"],
            "title": section_title(row),
            "status": row["status"],
            "enforcement": row["enforcement"],
            "scale": row["scale"],
            "audience": row["audience"],
            "version": str(row["version"]),
            "review_by": str(row["review_by"]),
            "body": section_body(row),
        }
        for row in load_registry()
        if re.search(presence_trigger(row), text)
    ]
    rank = {"L2": 0, "L1": 1, "L0": 2}
    matched.sort(key=lambda entry: rank[str(entry["enforcement"])])
    return matched
