"""The answer fixtures the suite renders with cannot drift from the questionnaire.

TODO §23.1. copier silently ignores an answer whose question does not exist --
it renders that question's default instead -- so a renamed question or a typo
in a fixture turns a render test into a test of nothing, while it keeps
passing. Nothing compared the fixtures with the questionnaire; the shared
values themselves live in tools/answers.py, and these checks are the guard
that keeps the two apart.
"""

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import answers  # noqa: E402
from tools import questionnaire  # noqa: E402

import test_batch  # noqa: E402
import test_generated_lint  # noqa: E402
import test_mcp_server  # noqa: E402
import test_recommended_path  # noqa: E402

# The live questionnaire, by name: the only authority on which questions exist
# and which values each accepts.
QUESTIONS = {question.name: question for question in questionnaire.load_questions()[0]}

EXAMPLE_ANSWERS = yaml.safe_load((TOP / "example-answers.yml").read_text(encoding="utf-8"))
BATCH_BASE = yaml.safe_load((TOP / "batches" / "base.yml").read_text(encoding="utf-8"))

GATE_PREFIX = "use_recommended_"


def _fixtures() -> dict[str, list[Mapping[str, Any]]]:
    """Every answer set this repo renders with, labelled for the failure message."""
    return {
        "tools/answers.py BASE": [answers.BASE],
        "example-answers.yml": [EXAMPLE_ANSWERS],
        "batches/base.yml": [BATCH_BASE],
        "test_recommended_path.FAST_PATHS": test_recommended_path.FAST_PATHS,
        "test_generated_lint.EXTRA_PATHS": test_generated_lint.EXTRA_PATHS,
        "test_generated_lint.MANAGER_PATHS": test_generated_lint.MANAGER_PATHS,
        "test_generated_lint.LAYER_PATHS": test_generated_lint.LAYER_PATHS,
        "test_generated_lint.JAPANESE_VARIANTS": test_generated_lint.JAPANESE_VARIANTS,
        "test_mcp_server.BASE_ANSWERS": [test_mcp_server.BASE_ANSWERS],
        "test_batch.BASE_ANSWERS": [test_batch.BASE_ANSWERS],
    }


def test_every_fixture_answer_names_a_real_question():
    unknown = {
        label: sorted({key for case in cases for key in case} - QUESTIONS.keys())
        for label, cases in _fixtures().items()
    }
    offenders = {label: keys for label, keys in unknown.items() if keys}
    assert not offenders, (
        "a fixture answers questions the questionnaire does not ask, so copier would render their "
        f"defaults and the case would cover nothing: {offenders}"
    )


def test_every_fixture_choice_is_offered_by_its_question():
    """A value outside the declared choices cannot be produced by answering the questionnaire."""
    offenders: dict[str, list[tuple[str, object, object]]] = {}
    for label, cases in _fixtures().items():
        for case in cases:
            for key, value in case.items():
                question = QUESTIONS.get(key)
                if question is None or not question.choices:
                    continue  # a block-scalar `choices` is a template: not resolvable here
                if value not in question.choices:
                    offenders.setdefault(label, []).append((key, value, question.choices))
    assert not offenders, f"a fixture answers a value its question does not offer: {offenders}"


def test_example_answers_keeps_every_gate_off():
    """example-answers.yml exists to take the long path: all gates off, every detail asked."""
    gates = {name: value for name, value in EXAMPLE_ANSWERS.items() if name.startswith(GATE_PREFIX)}
    assert gates, "the fixture no longer turns any gate off"
    assert set(gates.values()) == {False}, f"a gate is no longer false: {gates}"
    # The gates that are asked unconditionally must all be here, or the fixture
    # stopped exercising the questionnaire's longest path.
    unconditional = {
        question.name
        for question in QUESTIONS.values()
        if question.name.startswith(GATE_PREFIX) and question.when is not False and not isinstance(question.when, str)
    }
    assert unconditional, "no unconditional gate found: GATE_PREFIX no longer matches the questionnaire"
    assert unconditional <= set(gates), f"the fixture stopped turning off {sorted(unconditional - set(gates))}"


def test_batch_sample_base_is_the_shared_answer_set():
    """batches/base.yml is documented as the same starting point the tests use."""
    assert BATCH_BASE == answers.BASE, (
        "batches/base.yml and tools/answers.py BASE diverge, so `task batch` renders a different "
        f"project than the pytest fast paths:\n  batch: {BATCH_BASE}\n  tests: {answers.BASE}"
    )
