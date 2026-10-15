"""The invariants file is the one source for what a leaf must satisfy.

tests/matrix/invariants.yml declares, per leaf class, the artifacts a render
must ship and must not ship, the content predicates that hold, the witness tier
the class runs at and why a question type is left out. architekton/invariants.py is
its only reader; these tests hold the
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
- a stale exclusion fails at load: an excluded ``project_type`` the
  questionnaire offers again, and an excluded ``question`` the questionnaire
  no longer declares, are both refused;
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
if str(TOP) not in sys.path:  # tests/test_batch.py, tests/test_witness_matrix.py do the same to reach architekton/
    sys.path.insert(0, str(TOP))

from architekton import batch  # noqa: E402
from architekton import invariants  # noqa: E402
from architekton.answers import BASE  # noqa: E402

from test_recommended_path import FAST_PATHS  # noqa: E402

INVARIANTS = invariants.load()
WITNESSES = TOP / "tests" / "matrix" / "witnesses.jsonl"
LEDGER = TOP / "tests" / "matrix" / "witnesses.json"

# The declared witness leaves, read through architekton/batch.py's own validator, so
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


def _excluded_live_project_type(payload: dict[str, Any]) -> None:
    """Exclude a project type the questionnaire still offers.

    The row that selects it is re-pointed first, so the error raised is the
    exclusion rot check (an exclusion must not be offered) and not the
    row-selector refusal a live exclusion would trip on the way there.
    """
    payload["excluded"].append({"project_type": "library", "why": "not a non-goal"})
    _row(payload, "project_type=library")["select"]["project_type"] = ["cli"]


def _excluded_unknown_question(payload: dict[str, Any]) -> None:
    payload["excluded"].append({"question": "include_nope", "why": "the questionnaire declares no such question"})


def _excluded_entry_of_both_kinds(payload: dict[str, Any]) -> None:
    payload["excluded"].append({"project_type": "ros2", "question": "include_ctf", "why": "two kinds, one entry"})


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


_M1_EXPECTED: dict[str, dict[str, object]] = {
    "include=include_data_science": {"ships": [], "absent": [], "content": []},
    "include=include_web_api": {"ships": [], "absent": [], "content": []},
    "include=include_bot/bot_platform=slack": {
        "ships": ["src/smoke_example/bot_slack.py", "tests/test_bot_slack.py"],
        "absent": [
            "src/smoke_example/bot_discord.py",
            "src/smoke_example/bot_line.py",
            "src/smoke_example/bot_gmail.py",
            "tests/test_bot_discord.py",
            "tests/test_bot_line.py",
            "tests/test_bot_gmail.py",
        ],
        "content": [["pyproject.toml", "slack-bolt"]],
    },
    "include=include_bot/bot_platform=line": {
        "ships": ["src/smoke_example/bot_line.py", "tests/test_bot_line.py"],
        "absent": [
            "src/smoke_example/bot_discord.py",
            "src/smoke_example/bot_slack.py",
            "src/smoke_example/bot_gmail.py",
            "tests/test_bot_discord.py",
            "tests/test_bot_slack.py",
            "tests/test_bot_gmail.py",
        ],
        "content": [["pyproject.toml", "line-bot-sdk"]],
    },
    "include=include_bot/bot_platform=gmail": {
        "ships": ["src/smoke_example/bot_gmail.py", "tests/test_bot_gmail.py"],
        "absent": [
            "src/smoke_example/bot_discord.py",
            "src/smoke_example/bot_slack.py",
            "src/smoke_example/bot_line.py",
            "tests/test_bot_discord.py",
            "tests/test_bot_slack.py",
            "tests/test_bot_line.py",
        ],
        "content": [["pyproject.toml", "google-api-python-client"]],
    },
    "include=include_bot_web_api/bot_platform=slack": {
        "ships": ["app/bot_slack.py", "tests/test_bot_slack.py"],
        "absent": [
            "app/bot_discord.py",
            "app/bot_line.py",
            "app/bot_gmail.py",
            "tests/test_bot_discord.py",
            "tests/test_bot_line.py",
            "tests/test_bot_gmail.py",
        ],
        "content": [["pyproject.toml", "slack-bolt"]],
    },
    "include=include_bot_web_api/bot_platform=line": {
        "ships": ["app/bot_line.py", "tests/test_bot_line.py"],
        "absent": [
            "app/bot_discord.py",
            "app/bot_slack.py",
            "app/bot_gmail.py",
            "tests/test_bot_discord.py",
            "tests/test_bot_slack.py",
            "tests/test_bot_gmail.py",
        ],
        "content": [["pyproject.toml", "line-bot-sdk"]],
    },
    "include=include_bot_web_api/bot_platform=gmail": {
        "ships": ["app/bot_gmail.py", "tests/test_bot_gmail.py"],
        "absent": [
            "app/bot_discord.py",
            "app/bot_slack.py",
            "app/bot_line.py",
            "tests/test_bot_discord.py",
            "tests/test_bot_slack.py",
            "tests/test_bot_line.py",
        ],
        "content": [["pyproject.toml", "google-api-python-client"]],
    },
}


def test_m1_generated_file_sets_are_byte_identical_to_former_hand_values() -> None:
    """M1 temporary byte-identical assertion (plan §2.3, removed at M3).

    The 8 derived rows' file-sets now come from the generated sidecar joined
    by architekton/invariants.py. This pinned assertion proves the generated
    file-set (ships/absent/content) equals the former hand-written file-set
    byte-for-byte, so the union/``expect`` outputs are unchanged. The expected
    dict is the committed hand value copied literally from invariants.yml at
    M0; the loader already guarantees the sidecar supplies an explicit entry
    for every derived row (R2).
    """
    by_id = {row.id: row for row in INVARIANTS.rows}
    problems: list[str] = []
    for row_id, expected in _M1_EXPECTED.items():
        row = by_id.get(row_id)
        if row is None:
            problems.append(f"{row_id}: missing row")
            continue
        got = {"ships": list(row.ships), "absent": list(row.absent), "content": [list(pair) for pair in row.content]}
        if got != expected:
            problems.append(f"{row_id}: got {got} want {expected}")
    assert problems == [], "M1 generated file-sets diverged from former hand file-sets:\n  " + "\n  ".join(problems)


def _double_truth_ships(payload: dict[str, Any]) -> None:
    _row(payload, "include=include_bot/bot_platform=slack")["ships"] = ["src/smoke_example/bot_slack.py"]


def _double_truth_alias_ships(payload: dict[str, Any]) -> None:
    _row(payload, "include=include_data_science")["ships"] = []


CASES: tuple[tuple[str, Callable[[dict[str, Any]], None], str], ...] = (
    ("unknown row key", _unknown_row_key, "unknown key"),
    ("unknown select key", _unknown_select_key, "unknown select key"),
    ("unknown select value", _unknown_select_value, "unknown project_type"),
    ("unknown gate", _unknown_gate, "unknown gate_off"),
    ("excluded project type", _excluded_project_type, "excluded project_type"),
    ("excluded live project type", _excluded_live_project_type, "still offers it"),
    ("excluded unknown question", _excluded_unknown_question, "no longer declares it"),
    ("excluded entry of both kinds", _excluded_entry_of_both_kinds, "not both"),
    ("unknown predicate", _unknown_predicate, "unknown predicate"),
    ("unknown tier", _unknown_tier, "unknown tier"),
    ("duplicate id", _duplicate_id, "duplicate leaf class id"),
    ("contradictory markers", _contradictory_markers, "both shipped and absent"),
    ("missing why", _missing_why, "`why`"),
    ("missing row", _missing_row, "no row selects project_type"),
    ("derived row double truth (origin + ships)", _double_truth_ships, "only the generated sidecar"),
    ("derived row double truth (alias + ships)", _double_truth_alias_ships, "only the generated sidecar"),
)


def _stage_with_sidecar(tmp_path: Path, payload: dict[str, Any]) -> Path:
    """Write *payload* as a tmp invariants.yml plus its sibling sidecar.

    The loader joins the policy file with ``invariants.files.yml`` next to it,
    so the tmp file must carry its own sidecar copy; otherwise every
    tmp-path test would fail with “missing sidecar” instead of the intended
    schema error.
    """
    broken = tmp_path / invariants.PATH.name
    broken.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    sidecar_src = invariants.FILES
    if sidecar_src.exists():
        (tmp_path / sidecar_src.name).write_text(sidecar_src.read_text(encoding="utf-8"), encoding="utf-8")
    return broken


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
    broken = _stage_with_sidecar(tmp_path, payload)
    with pytest.raises(invariants.InvariantError, match=match):
        invariants.load(broken)


def test_missing_sidecar_for_derived_row_is_refused(tmp_path: Path) -> None:
    payload = yaml.safe_load(invariants.PATH.read_text(encoding="utf-8"))
    broken = tmp_path / invariants.PATH.name
    broken.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    # No sidecar copied -- load must refuse the missing generated row.
    with pytest.raises(invariants.InvariantError, match=r"need invariants\.files\.yml"):
        invariants.load(broken)


def test_orphan_generated_row_is_refused(tmp_path: Path) -> None:
    payload = yaml.safe_load(invariants.PATH.read_text(encoding="utf-8"))
    broken = _stage_with_sidecar(tmp_path, payload)
    sidecar = tmp_path / invariants.FILES.name
    data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    data["orphan=row"] = {"ships": [], "absent": [], "content": []}
    sidecar.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(invariants.InvariantError, match="orphan generated rows"):
        invariants.load(broken)
