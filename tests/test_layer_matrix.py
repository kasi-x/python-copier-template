"""D1: the declared layer availability matrix against the live `when` gates.

tests/matrix/layers.yml declares, for each opt-in layer, the base project
types that see its include question, the non-base clauses its `when` reads,
and the reason the availability set is what it is (TODO §28.6 D1 — the
machine-readable completion of §10's "a request to add something must first
answer what existing thing it layers on top of", and the standing remedy for
§28.4's 1c unexplained asymmetries and 1b include_bot hole). The declaration
is held against the questionnaire in both directions, registry-test style
(tests/test_support_matrix.py, tests/test_answer_fixtures.py): declared, not
discovered, and stale-proof both ways.

Direction (a) — matrix -> when: for every declared row, copier's own
questionnaire pass (Worker._ask + Question.get_when — the same oracle
tests/test_when_model.py established) evaluates the question's real `when`
over every project_type choice, with the row's declared clauses at their off
polarity (rides not opted into, the extra trait off, the revealing gate off)
and every other answer at its default. The admitted set must equal the
declared bases exactly; this is an actual evaluation, never a string
compare, so a `when` that changed meaning without changing shape still
fails.

Direction (b) — when -> matrix: the identifiers each `when` reads
(tools/when_model.jinja_identifiers, Jinja operators subtracted) must be
exactly {project_type} plus the row's declared clauses. A future clause
added to a `when` without updating the declaration fails here, and so does a
declaration row naming a clause the `when` no longer has.

What this does not cover (a narrower claim beats an overstated one): the
ride semantics themselves — that a bot/MCP question REALLY appears once
include_web_api is answered Yes — are pinned by
tests/test_bot_layer.py::test_include_bot_and_include_mcp_gates_stay_in_sync
plus the bot/MCP scaffold tests; this file pins who gets ASKED with every
layer off. The render-time effective guards (scraping_effective, bot_effective,
mcp_effective, ctf_effective) re-check the same bases render-side; their sync
with these ask-time gates is owned by those guards' own comments and pins,
not re-declared here.
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:  # tests/test_batch.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from copier._main import Worker  # noqa: E402
from copier._user_data import Question  # noqa: E402
from tools import answers  # noqa: E402
from tools import when_model  # noqa: E402

MATRIX = TOP / "tests" / "matrix" / "layers.yml"

# The non-base clause kinds a row may declare; see layers.yml's header for
# what each means.
CLAUSE_KINDS = ("extras", "rides", "revealed_by")


def matrix() -> dict[str, Any]:
    """The committed declaration, as yaml reads it."""
    return yaml.safe_load(MATRIX.read_text(encoding="utf-8"))


def rows() -> dict[str, dict[str, Any]]:
    """The layer rows, keyed by their include question's name."""
    return {str(row["include"]): row for row in matrix()["layers"]}


def exclusions() -> dict[str, dict[str, Any]]:
    """The include questions deliberately kept out of the matrix, keyed by name."""
    return {str(row["include"]): row for row in matrix().get("excluded", [])}


def clause_names(row: dict[str, Any]) -> set[str]:
    """Every non-base clause name the row declares, across all kinds."""
    names: set[str] = set()
    for kind in CLAUSE_KINDS:
        names.update(str(clause) for clause in row.get(kind, []))
    return names


@pytest.fixture(scope="module")
def worker() -> Iterator[Worker]:
    """One copier Worker for the module: the oracle is the checkout's own
    questionnaire (vcs_ref=HEAD), the setup tests/test_when_model.py uses."""
    with tempfile.TemporaryDirectory() as dst:
        yield Worker(src_path=str(TOP), dst_path=Path(dst), defaults=True, quiet=True, vcs_ref="HEAD")


def _admitted_by_type(
    worker: Worker, names: Sequence[str], off: dict[str, bool], choices: Sequence[str]
) -> dict[str, set[str]]:
    """The project types each named question's real `when` admits, declared clauses off.

    One questionnaire pass per project_type, shared by every row: direction
    (b) (`test_when_identifiers_are_exactly_the_declared_clauses`) guarantees
    a row's `when` reads nothing but `project_type` and its own clauses, so
    evaluating all rows with the UNION of declared clauses off is the same
    evaluation as per-row offs — at one pass per type instead of one per
    (row, type), which is what keeps this check inside the edit-loop budget.
    `worker.data` seeds the pass with the shared Project Details, the
    project_type under trial, and the clauses at their off polarity — so what
    the evaluation isolates is exactly the declared base set, not a layer the
    environment leaked in. `Worker._ask` is the questionnaire pass copier
    itself runs and `Question.get_when` is the method that decides whether a
    question is asked; both are private, because copier exposes no other way
    to run that pass.
    """
    admitted: dict[str, set[str]] = {name: set() for name in names}
    for project_type in choices:
        worker.data = {**answers.BASE, "project_type": project_type, **off}
        worker._ask()  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001  WHYNOT: the oracle is copier's own questionnaire pass, the tests/test_when_model.py precedent.
        context = worker._render_context()  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001  WHYNOT: same oracle as above.
        for name in names:
            question = Question(
                answers=worker.answers,
                context=context,
                jinja_env=worker.jinja_env,
                settings=worker.settings,
                var_name=name,
                **worker.template.questions_data[name],
            )
            if question.get_when():
                admitted[name].add(project_type)
    return admitted


def _table(headers: Sequence[str], data: Sequence[Sequence[str]]) -> str:
    """A fixed-width table for the failure message: every mismatched row, named."""
    widths = [len(header) for header in headers]
    for row in data:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    lines = ["  " + "  ".join(header.ljust(width) for header, width in zip(headers, widths, strict=True))]
    lines.extend("  " + "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)) for row in data)
    return "\n".join(lines)


def test_declared_bases_are_exactly_what_the_when_admits(worker: Worker) -> None:
    """Direction (a): declared bases == what each question's real `when` admits.

    The evaluation is copier's own Jinja over every project_type choice with
    the row's declared non-base clauses off — a base added to (or dropped
    from) a `when` without a matching declaration change fails here, naming
    every drifted row.
    """
    questions, _order = when_model.load_questions()
    choices = when_model.static_str_choices(questions["project_type"])
    assert choices, "project_type lost its static choices: there is no base space to iterate"
    problems: list[list[str]] = []

    # Rows whose `when` is gone are registry problems, not evaluation inputs:
    # only live rows go into the shared copier passes below.
    rows_all = rows()
    live = {
        name: row
        for name, row in rows_all.items()
        if name in questions and isinstance(questions[name].get("when"), str)
    }
    problems.extend(
        [name, str(rows_all[name].get("bases")), "-", "the question is gone or its `when` is no longer templated"]
        for name in sorted(set(rows_all) - set(live))
    )

    off = dict.fromkeys(sorted({clause for row in rows_all.values() for clause in clause_names(row)}), False)
    admitted = _admitted_by_type(worker, list(live), off, choices)
    for name, row in live.items():
        declared = {str(base) for base in row["bases"]}
        if admitted[name] != declared:
            when_only = ", ".join(sorted(admitted[name] - declared)) or "(none)"
            declared_only = ", ".join(sorted(declared - admitted[name])) or "(none)"
            problems.append(
                [
                    name,
                    ", ".join(str(base) for base in row["bases"]),
                    ", ".join(sorted(admitted[name])),
                    f"when-only: {when_only}; declared-only: {declared_only}",
                ]
            )
    assert not problems, (
        f"{len(problems)} layer row(s) drift from the live `when` gates (declared bases vs the project types "
        "the question's real `when` admits, evaluated by copier's own questionnaire pass with every declared "
        "non-base clause off) — update tests/matrix/layers.yml or the `when`, whichever is wrong:\n"
        + _table(["layer", "declared bases", "when admits", "difference"], problems)
    )


def test_when_identifiers_are_exactly_the_declared_clauses() -> None:
    """Direction (b): each `when` reads exactly {project_type} + declared clauses.

    The identifier set is the shape-level guard: a clause ADDED to a `when`
    without a declaration (the 1c failure mode — availability that grew a
    disjunct silently) fails, and so does a declared clause the `when` no
    longer reads (the declaration lying about a gate that is gone).
    """
    questions, _order = when_model.load_questions()

    problems: list[list[str]] = []
    for name, row in rows().items():
        when = questions[name].get("when") if name in questions else None
        if not isinstance(when, str):
            problems.append([name, str(dict.fromkeys(clause_names(row))), "-", "no templated `when` left"])
            continue
        reads = when_model.jinja_identifiers(when) - when_model.JINJA_OPERATORS
        declared = {"project_type"} | clause_names(row)
        if reads != declared:
            when_only = ", ".join(sorted(reads - declared)) or "(none)"
            declared_only = ", ".join(sorted(declared - reads)) or "(none)"
            problems.append(
                [
                    name,
                    ", ".join(sorted(declared)),
                    ", ".join(sorted(reads)),
                    f"when-only: {when_only}; declared-only: {declared_only}",
                ]
            )
    assert not problems, (
        f"{len(problems)} layer row(s) disagree with their `when` about which clauses exist "
        "(the `when`'s identifier set vs {project_type} + the row's extras/rides/revealed_by) — "
        "declare the clause in tests/matrix/layers.yml or drop it from the `when`:\n"
        + _table(["layer", "declared clauses", "when reads", "difference"], problems)
    )


def test_every_row_and_exclusion_has_a_why():
    """§28.6 D1 settles every availability set by written reason or removal."""
    payload = matrix()
    unreasoned = [
        str(row.get("include"))
        for section in ("layers", "excluded")
        for row in payload.get(section, [])
        if not (isinstance(row.get("why"), str) and row["why"].strip())
    ]
    assert unreasoned == [], (
        f"layer matrix row(s) {unreasoned} carry no `why`: a row whose reason cannot be written must be "
        "reworked into a shape that can, or withdrawn — that is the decision §28.6 D1 asks for"
    )


def _row_problems(
    name: str,
    row: dict[str, Any],
    questions: Mapping[str, dict],
    choices: set[str],
    declared: dict[str, dict[str, Any]],
) -> list[str]:
    """The registry problems of one declared row: dead names, unknown bases, dangling clauses.

    Clause names are checked against every questionnaire key, asked or
    internal (kaggle, the web_api layer's extra, is a derived internal), so a
    clause that lost its definition fails even though it was never asked.
    """
    if name not in questions:
        return [f"{name}: declared as a layer, but the question is gone"]
    problems: list[str] = []
    bases = [str(base) for base in row["bases"]]
    if not bases:
        problems.append(f"{name}: declares empty bases — a layer nothing can reach is a row to remove, not to declare")
    unknown_bases = sorted(set(bases) - choices)
    if unknown_bases:
        problems.append(f"{name}: bases {unknown_bases} are not project_type choices")
    for kind in CLAUSE_KINDS:
        for clause in (str(item) for item in row.get(kind, [])):
            if clause not in questions:
                problems.append(f"{name}: {kind} names {clause!r}, which the questionnaire no longer defines")
            if clause in (name, "project_type"):
                problems.append(f"{name}: {kind} names {clause!r}, which cannot be a clause")
    undeclared_rides = sorted({str(item) for item in row.get("rides", [])} - set(declared))
    if undeclared_rides:
        problems.append(f"{name}: rides {undeclared_rides}, which is not itself a declared layer row")
    return problems


def test_matrix_rows_are_live_and_complete():
    """The registry accounts for every include question, in both directions.

    A layer row naming a question that is gone (or whose `when` stopped being
    templated) is as stale as an include question that appeared without a
    declaration: the same declared-not-discovered rule
    tools/z3_witnesses.py enforces for the leaf space, applied to the matrix.
    """
    questions, _order = when_model.load_questions()
    choices = set(when_model.static_str_choices(questions["project_type"]))
    declared = rows()
    excluded_rows = exclusions()
    live = {
        name
        for name, question in questions.items()
        if name.startswith("include_") and isinstance(question.get("when"), str)
    }

    problems = [
        *(
            problem
            for name, row in declared.items()
            for problem in _row_problems(name, row, questions, choices, declared)
        ),
        *(
            f"{name}: declared excluded, but the question is gone or its `when` is no longer templated"
            for name in excluded_rows
            if name not in live
        ),
    ]
    unaccounted = sorted(live - set(declared) - set(excluded_rows))
    if unaccounted:
        problems.append(
            f"include question(s) {unaccounted} are neither a declared layer nor declared excluded — "
            f"declare them in {MATRIX.relative_to(TOP)} with the reason they exist"
        )
    assert not problems, "the layer availability registry is stale or incomplete:\n  " + "\n  ".join(problems)
