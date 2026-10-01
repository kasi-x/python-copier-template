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

import ast
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


# --------------------------------------------------------------------- #
# Gate evaluation: the one spelling of "which leaf carries this section"  #
# --------------------------------------------------------------------- #
#
# A registry row's `gate` is a Jinja expression evaluated by copier at
# render time (inside the generated _shared/ethics-appendix.jinja). The
# render-invariants predicate must evaluate the SAME string on the test
# side, so the expression is kept in Python-compatible shape and evaluated
# here through a restricted eval -- no builtins, no attribute access, no
# calls. The context is the leaf's answer-derived flag set: the names the
# questionnaire's internal defaults would produce for this leaf
# (`*_effective`, the layouts, the domain/distribution multiselects as
# lists). A gate that names a flag not in this mapping is a vocabulary bug,
# caught by the registry test before it ever renders.


def _combinable(answers: dict[str, Any]) -> bool:
    """questions/_combo.yml's `combinable`: the bases a layer may ride on.

    A forced `--data-file` answer can set `include_web_api` on a
    non-combinable base (ros2, script, ...); the questionnaire's `has_*`
    internals re-check `combinable`, so this context must too -- otherwise a
    gate would report a leaf carrying a section the render never wrote.
    """
    project_type = answers.get("project_type")
    is_kaggle = project_type == "online_judge" and answers.get("oj_kind") == "kaggle"
    return project_type in ("library", "cli", "web_api", "data_science") or is_kaggle


# questions/online_judge.yml's `oj_code` choice list, spelled once here: the
# code-submission judges, with the kaggle workspace and the ctf challenges
# deliberately outside it (they are judges too, but neither is a contest
# whose AI rules the guide is about).
OJ_CODE_KINDS = frozenset({"atcoder", "leetcode", "yukicoder", "aoj", "codeforces", "kattis", "other"})

# Node types a gate expression may use. Anything outside this list (calls,
# attribute access, subscripts, comprehensions, names outside the context)
# fails the safety check -- the point is a lint, not a sandbox: gates are
# trusted content but this catches a typo'd expression that would crash or
# silently evaluate wrong at render time.
_GATE_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.UnaryOp,
    ast.BinOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Mod,
    ast.USub,
)


def _choices(answers: dict[str, Any], key: str) -> list[str]:
    """A multiselect answer as a list, accepting the bare-string spelling."""
    recorded = answers.get(key, [])
    if isinstance(recorded, str):
        return [recorded]
    if isinstance(recorded, (list, tuple, set)):
        return [str(entry) for entry in recorded]
    return []


def leaf_context(answers: dict[str, Any]) -> dict[str, Any]:
    """The flag set a leaf's answers imply: what the generated appendix sees.

    Mirrors questions/_internal.yml's derived defaults -- the same names, the
    same conditions -- so a gate string means one thing in both places. The
    include/gate answer shape is assumed non-recommended only when the leaf
    actually carries it (witness leaves set gates explicitly; a leaf that
    never answers `include_scraping` resolves its `scraping_effective` to
    false, matching copier's treatment of an unanswered question's default).
    """
    project_type = str(answers.get("project_type") or "")
    combinable = _combinable(answers)
    web_api = project_type == "web_api" or (bool(answers.get("include_web_api")) and combinable)
    data_science = project_type == "data_science" or (bool(answers.get("include_data_science")) and combinable)
    kaggle = project_type == "online_judge" and answers.get("oj_kind") == "kaggle"
    oj_ctf = project_type == "online_judge" and answers.get("oj_kind") == "ctf"
    return {
        "true": True,
        "false": False,
        "project_type": project_type,
        "oj_kind": str(answers.get("oj_kind") or ""),
        "domain_traits": _choices(answers, "domain_traits"),
        "distribution": _choices(answers, "distribution"),
        "web_api": web_api,
        "data_science_layout": data_science,
        "ds_stack": data_science or kaggle,
        "mcp_effective": bool(answers.get("include_mcp")) and (project_type == "cli" or web_api),
        "scraping_effective": bool(answers.get("include_scraping")) and project_type == "cli",
        "oj_code": project_type == "online_judge" and answers.get("oj_kind") in OJ_CODE_KINDS,
        "oj_ctf": oj_ctf,
        "agents_md_effective": True,
        # No leaf exercises these today, but they are documented gate
        # vocabulary: keep them bound so a gate that names them evaluates
        # (to the leaf's truth) instead of raising NameError.
        "license": str(answers.get("license") or ""),
        "scraping_memorious_effective": bool(answers.get("include_scraping"))
        and project_type == "cli"
        and answers.get("scraping_engine") in ("memorious", "all"),
    }


def gate_safe(gate: str) -> str | None:
    """None when the expression is evaluable in the restricted context.

    Returns a description of the first offending construct on failure.
    """
    try:
        tree = ast.parse(gate, mode="eval")
    except SyntaxError as exc:
        return f"syntax error: {exc}"
    for node in ast.walk(tree):
        if not isinstance(node, _GATE_NODES):
            return f"{type(node).__name__} is not allowed in a gate expression"
    return None


def gate_holds(row: dict[str, Any], answers: dict[str, Any]) -> bool:
    """Whether the registry row's gate selects this leaf.

    `gate: "true"` (or a missing/empty gate -- the unconditional spelling) is
    always on; anything else is the restricted eval of the row's expression.
    """
    gate = str(row.get("gate") or "").strip()
    if not gate or gate == "true":
        return True
    problem = gate_safe(gate)
    if problem is not None:
        msg = f"{row['id']}: unsafe gate {gate!r}: {problem}"
        raise ValueError(msg)
    return bool(eval(gate, {"__builtins__": {}}, leaf_context(answers)))  # noqa: S307 -- allowlisted AST
