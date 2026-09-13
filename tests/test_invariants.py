"""The invariants file is the one source for what a leaf must satisfy.

tests/matrix/invariants.yml declares, per leaf class, the artifacts a render
must ship and must not ship, the content predicates that hold, the witness tier
the class runs at and why a question type is left out (TODO.md §26.4 item 4,
§23.4 item 2). tools/invariants.py is its only reader; these tests hold the
loader's contract and the migration it exists for:

- the union of the rows a witness leaf's answers select reproduces that leaf's
  committed ``expect`` exactly, and every leaf's dimensions (its project type,
  judge, opt-in layer, gate turned off) are selected by some row -- so the
  generator, the batch runner and the per-class tables in the test suite cannot
  drift apart again;
- a malformed row fails loudly instead of silently shrinking a class: an
  unknown key, an unknown select value, an unknown predicate or tier, a
  duplicate id, a contradiction, a missing reason, or a project type with no
  row all raise ``InvariantError`` naming the row;
- a leaf whose class no row declares is refused, not resolved to the common
  layout.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_batch.py, tests/test_witness_matrix.py do the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools import batch  # noqa: E402
from tools import invariants  # noqa: E402

from test_recommended_path import BASE  # noqa: E402
from test_recommended_path import FAST_PATHS  # noqa: E402

INVARIANTS = invariants.load()
WITNESSES = TOP / "tests" / "matrix" / "witnesses.jsonl"
LEDGER = TOP / "tests" / "matrix" / "witnesses.json"

# The declared witness leaves, read through tools/batch.py's own validator, so
# this module checks exactly what the batch runner will render.
LEAVES: dict[str, dict[str, Any]] = {
    request.id: {"answers": dict(request.answers), "expect": dict(request.expect)}
    for request in batch.load_requests([WITNESSES])
}

# The fast paths of tests/test_recommended_path.py: leaves the witness space
# does not contain (they answer a detail question, e.g. include_mcp), but which
# this file still has to classify.
FAST: tuple[dict[str, Any], ...] = tuple({**BASE, **answers} for answers in FAST_PATHS)


def _declared_tiers() -> dict[str, str]:
    """The tier each witness leaf was actually run at (the §C4 ledger)."""
    payload: dict[str, Any] = json.loads(LEDGER.read_text(encoding="utf-8"))
    return {str(entry["id"]): str(entry["tier"]) for entry in payload["leaves"]}


def test_every_witness_leaf_resolves_to_a_row() -> None:
    """No leaf is unclassified: rows select it, and so does every dimension.

    The unit here is one of the leaf's dimensions, not the leaf: a leaf whose
    project type is covered but whose judge or layer is not would still resolve
    to a row, only to lose that branch's artifacts silently.
    """
    problems: list[str] = []
    for leaf_id, leaf in LEAVES.items():
        rows = INVARIANTS.rows_for(leaf["answers"])
        unclaimed = INVARIANTS.unclaimed(leaf["answers"])
        if not rows:
            problems.append(f"{leaf_id}: no row selects it")
        if unclaimed:
            problems.append(f"{leaf_id}: no row selects {list(unclaimed)}")
    assert problems == [], "leaf classes with no declaration in tests/matrix/invariants.yml:\n  " + "\n  ".join(
        problems
    )


def test_the_rows_reproduce_every_witness_expect() -> None:
    """The file, not the generator, is where a leaf's artifacts are declared.

    Every committed §C6 request is rebuilt from the rows its answers select, so
    a value that lives in only one of the two places shows up here.
    """
    drifted = [
        f"{leaf_id}: rows say {INVARIANTS.expect_for(leaf['answers'])} declared {leaf['expect']}"
        for leaf_id, leaf in LEAVES.items()
        if INVARIANTS.expect_for(leaf["answers"]) != {key: list(value) for key, value in leaf["expect"].items()}
    ]
    assert drifted == [], f"{WITNESSES.name} and the invariants rows disagree:\n  " + "\n  ".join(drifted)


def test_every_witness_leaf_has_a_declared_tier() -> None:
    """The tier a leaf was run at is a tier its class declares.

    A leaf whose recorded tier no row declares is a class the file does not
    describe -- the drift `support.yml`'s tier_policy and the ledger would hide
    from each other.
    """
    recorded = _declared_tiers()
    problems: list[str] = []
    for leaf_id, leaf in LEAVES.items():
        declared = INVARIANTS.tiers_for(leaf["answers"])
        if not declared:
            problems.append(f"{leaf_id}: no row declares a tier")
        elif recorded.get(leaf_id) not in declared:
            problems.append(f"{leaf_id}: ran at {recorded.get(leaf_id)!r}, the rows declare {list(declared)}")
    assert problems == [], "witness tiers with no matching row:\n  " + "\n  ".join(problems)


def test_every_row_is_reached_by_a_declared_leaf() -> None:
    """No dead row: each one is selected by a witness leaf or a fast path."""
    reached = {row.id for leaf in LEAVES.values() for row in INVARIANTS.rows_for(leaf["answers"])}
    reached |= {row.id for answers in FAST for row in INVARIANTS.rows_for(answers)}
    unreached = sorted({row.id for row in INVARIANTS.rows} - reached)
    assert unreached == [], f"rows no declared leaf selects: {unreached}"


def test_an_unclassified_leaf_is_refused() -> None:
    """A leaf carrying an undeclared question is an error, not a common layout.

    ``include_sentry`` is a real question (questions/_common_b.yml) no row
    selects: answering it must not quietly resolve to the common row alone.
    """
    with pytest.raises(invariants.InvariantError, match="include_sentry"):
        INVARIANTS.expect_for({**BASE, "project_type": "cli", "include_sentry": True})


def _row(payload: dict[str, Any], row_id: str) -> dict[str, Any]:
    """One row of a loaded copy of the file, by id."""
    return next(row for row in payload["leaf_classes"] if row["id"] == row_id)


def _unknown_row_key(payload: dict[str, Any]) -> None:
    _row(payload, "common")["ships_extra"] = []


def _unknown_select_key(payload: dict[str, Any]) -> None:
    _row(payload, "common")["select"]["project_typ"] = ["library"]


def _unknown_select_value(payload: dict[str, Any]) -> None:
    _row(payload, "project_type=library")["select"]["project_type"] = ["no-such-type"]


def _unknown_gate(payload: dict[str, Any]) -> None:
    _row(payload, "gate_off=other")["select"]["gate_off"] = ["use_recommended_bogus"]


def _excluded_project_type(payload: dict[str, Any]) -> None:
    _row(payload, "project_type=library")["select"]["project_type"] = ["web_django"]


def _unknown_predicate(payload: dict[str, Any]) -> None:
    _row(payload, "common")["predicates"] = ["pyprojectt"]


def _unknown_tier(payload: dict[str, Any]) -> None:
    _row(payload, "project_type=library")["tier"] = {"name": "medium", "why": "not a tier"}


def _duplicate_id(payload: dict[str, Any]) -> None:
    payload["leaf_classes"].append(dict(_row(payload, "common")))


def _contradictory_markers(payload: dict[str, Any]) -> None:
    _row(payload, "common")["markers"] = {"ships": ["README.md"], "absent": ["README.md"]}


def _missing_why(payload: dict[str, Any]) -> None:
    del _row(payload, "common")["why"]


def _missing_row(payload: dict[str, Any]) -> None:
    payload["leaf_classes"] = [row for row in payload["leaf_classes"] if row["id"] != "project_type=script"]


CASES: tuple[tuple[str, Callable[[dict[str, Any]], None], str], ...] = (
    ("unknown row key", _unknown_row_key, "unknown key"),
    ("unknown select key", _unknown_select_key, "unknown select key"),
    ("unknown select value", _unknown_select_value, "unknown project_type"),
    ("unknown gate", _unknown_gate, "unknown gate_off"),
    ("excluded project type", _excluded_project_type, "excluded project_type"),
    ("unknown predicate", _unknown_predicate, "unknown predicate"),
    ("unknown tier", _unknown_tier, "unknown tier"),
    ("duplicate id", _duplicate_id, "duplicate leaf class id"),
    ("contradictory markers", _contradictory_markers, "both shipped and absent"),
    ("missing why", _missing_why, "`why`"),
    ("missing row", _missing_row, "no row selects project_type"),
)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [pytest.param(mutate, match, id=case) for case, mutate, match in CASES],
)
def test_a_malformed_file_fails_loudly(tmp_path: Path, mutate: Callable[[dict[str, Any]], None], match: str) -> None:
    """One broken row at a time: the loader names it instead of ignoring it.

    This is the "one file to edit" property from the other side -- a row that
    says something the questionnaire, the predicate registry or the tier
    vocabulary does not know cannot load, so an unknown leaf class can never be
    silently unchecked.
    """
    payload = yaml.safe_load(invariants.PATH.read_text(encoding="utf-8"))
    mutate(payload)
    broken = tmp_path / invariants.PATH.name
    broken.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(invariants.InvariantError, match=match):
        invariants.load(broken)
