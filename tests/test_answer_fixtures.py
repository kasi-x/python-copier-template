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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import answers  # noqa: E402
from tools import questionnaire  # noqa: E402

import test_batch  # noqa: E402
import test_bot_layer  # noqa: E402
import test_example_adopt  # noqa: E402
import test_example_data_science  # noqa: E402
import test_example_docs_ci  # noqa: E402
import test_generated_lint  # noqa: E402
import test_generated_typecheck  # noqa: E402
import test_generation_docs  # noqa: E402
import test_machine_gate  # noqa: E402
import test_mcp_server  # noqa: E402
import test_micropython_maintenance  # noqa: E402
import test_recommended_path  # noqa: E402
import test_task_runners  # noqa: E402

# The live questionnaire, by name: the only authority on which questions exist
# and which values each accepts.
QUESTIONS = {question.name: question for question in questionnaire.load_questions()[0]}

EXAMPLE_ANSWERS = yaml.safe_load((TOP / "example-answers.yml").read_text(encoding="utf-8"))
BATCH_BASE = yaml.safe_load((TOP / "batches" / "base.yml").read_text(encoding="utf-8"))

GATE_PREFIX = "use_recommended_"

# Answers that deliberately restate their question's default. Like
# invariants.yml's `excluded`, the registry is declared, not discovered: the
# test below refuses an undeclared repeat, and refuses a declared key that has
# stopped repeating (a stale entry is the same lie in the other direction).
DEFAULT_REPEATS_ALLOWED: dict[str, dict[str, str]] = {
    "tools/answers.py BASE": {
        "git_platform": "BASE is what the committed tests/matrix/witnesses.json(l) leaves were derived"
        " from, so dropping the key would rewrite byte-frozen fixtures; it leaves only with a"
        " deliberate witness regeneration",
    },
    "batches/base.yml": {
        "git_platform": "must equal answers.BASE (checked below), so it repeats what the witness bytes pin",
    },
    "test_mcp_server.BASE_ANSWERS": {
        "git_platform": "inherited from answers.BASE, which the witness bytes pin",
    },
    "test_batch.BASE_ANSWERS": {
        "git_platform": "inherited from answers.BASE, which the witness bytes pin",
    },
    "test_recommended_path.FAST_PATHS": {
        "project_type": "tools/invariants.facts refuses a case without a stated project_type, so the"
        " dimension is named even at its default",
        "oj_category": "oj_kind's choices are resolved from oj_category (kaggle exists only under"
        " data_science), so the case declares the pair",
    },
    "test_generated_lint.EXTRA_PATHS": {
        "micropython_port": "the case names the branch it renders; the value is the variant's subject",
        "pkg_language": "the case names the branch it renders; the value is the variant's subject",
        "ros_distro": "the case names the branch it renders; the value is the variant's subject",
        "ros2_package_manager": "the case names the branch it renders; the value is the variant's subject",
    },
    "test_generated_lint.MANAGER_PATHS": {
        "project_type": "tools/invariants.facts refuses a case without a stated project_type",
    },
    "test_generated_lint.LAYER_PATHS": {
        "project_type": "tools/invariants.facts refuses a case without a stated project_type",
    },
    "test_generated_lint.JAPANESE_VARIANTS": {
        "allow_japanese": "the off state is the variant's subject (its sibling states True), so"
        " restating it is the variant, not drift",
    },
    "test_generated_typecheck.TYPECHECK_PATHS": {
        "project_type": "tools/invariants.facts refuses a case without a stated project_type",
    },
    "test_machine_gate.RENDER_MATRIX": {
        "project_type": "tools/invariants.facts refuses a case without a stated project_type",
        "oj_category": "oj_kind's choices are resolved from oj_category (kaggle exists only under"
        " data_science), so the case declares the pair",
        "micropython_port": "the case names the branch it renders; the value is the variant's subject",
        "pkg_language": "the case names the branch it renders; the value is the variant's subject",
        "ros_distro": "the case names the branch it renders; the value is the variant's subject",
        "ros2_package_manager": "the case names the branch it renders; the value is the variant's subject",
    },
    "test_generation_docs.MINIMAL_ANSWERS": {
        "project_type": "the case names the branch it renders; the value is the variant's subject",
        "git_platform": "the module mirrors the documented minimal answers file"
        " (docs/reference/non-interactive.md), which states the platform even at its default",
        "docs_type": "copier validates a supplied value against the question's choices even while"
        " use_recommended_docs keeps `when` false, so zensical being accepted is the fork-only signal",
    },
    "test_task_runners.RENDER_ARGS": {
        "task_runner": "the case names the runner it renders; the value is the variant's subject",
        "task_runner_pixi": "the case names the runner it renders; the value is the variant's subject",
    },
    "test_example_adopt.NOGIT_ANSWERS": {
        "git_platform": "inherited from answers.BASE, which the witness bytes pin",
    },
    "test_micropython_maintenance.MICROPYTHON_ANSWERS": {
        "micropython_port": "the case names the branch it renders; the value is the variant's subject",
    },
    "test_example_docs_ci.ORCID_INVALID_ANSWERS": {
        "project_type": "the case names the branch it renders; the value is the variant's subject",
    },
}


def _fixtures() -> Mapping[str, Sequence[Mapping[str, Any]]]:
    """Every answer set this repo renders with, labelled for the failure message.

    The fixtures are declared by their own modules (`list[dict[str, object]]`,
    `dict[str, Any]`, ...), so the registry takes the covariant view of them:
    it only reads. Answer literals that live inside a test module register
    here too -- complete sets (test_example_adopt.NOGIT_ANSWERS) and the
    BASE-composed overrides of a render call site
    (test_example_docs_ci.ORCID_INVALID_ANSWERS) alike -- so a dict a grep
    would miss is still checked against the questionnaire.
    """
    return {
        "tools/answers.py BASE": [answers.BASE],
        "example-answers.yml": [EXAMPLE_ANSWERS],
        "batches/base.yml": [BATCH_BASE],
        "test_recommended_path.FAST_PATHS": test_recommended_path.FAST_PATHS,
        "test_generated_typecheck.TYPECHECK_PATHS": test_generated_typecheck.TYPECHECK_PATHS,
        "test_machine_gate.RENDER_MATRIX": test_machine_gate.RENDER_MATRIX,
        "test_generation_docs.MINIMAL_ANSWERS": [test_generation_docs.MINIMAL_ANSWERS],
        "test_task_runners.RENDER_ARGS": list(test_task_runners.RENDER_ARGS.values()),
        "test_generated_lint.EXTRA_PATHS": test_generated_lint.EXTRA_PATHS,
        "test_generated_lint.MANAGER_PATHS": test_generated_lint.MANAGER_PATHS,
        "test_generated_lint.LAYER_PATHS": test_generated_lint.LAYER_PATHS,
        "test_generated_lint.JAPANESE_VARIANTS": test_generated_lint.JAPANESE_VARIANTS,
        "test_mcp_server.BASE_ANSWERS": [test_mcp_server.BASE_ANSWERS],
        "test_batch.BASE_ANSWERS": [test_batch.BASE_ANSWERS],
        "test_bot_layer.SLACK_ANSWERS": [test_bot_layer.SLACK_ANSWERS],
        "test_bot_layer.LINE_ANSWERS": [test_bot_layer.LINE_ANSWERS],
        "test_bot_layer.GMAIL_ANSWERS": [test_bot_layer.GMAIL_ANSWERS],
        "test_example_adopt.NOGIT_ANSWERS": [test_example_adopt.NOGIT_ANSWERS],
        "test_micropython_maintenance.MICROPYTHON_ANSWERS": [test_micropython_maintenance.MICROPYTHON_ANSWERS],
        "test_example_docs_ci.ORCID_INVALID_ANSWERS": [test_example_docs_ci.ORCID_INVALID_ANSWERS],
        "test_example_data_science.DATA_GOV_ANSWERS": [test_example_data_science.DATA_GOV_ANSWERS],
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
    """A value outside the declared choices cannot be produced by answering the questionnaire.

    The same value-level reading holds against the default (TODO §23.1): each
    fixture is defaults() plus its override diff, so a value equal to its
    question's default renders identically if dropped and the next editor
    cannot tell intent from boilerplate. example-answers.yml is exactly that
    shape (every gate off plus its non-default overrides); the repeats in
    DEFAULT_REPEATS_ALLOWED are the declared, load-bearing exceptions.
    """
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

    observed = _default_repeats()
    undeclared = {
        label: sorted(set(keys) - set(DEFAULT_REPEATS_ALLOWED.get(label, {})))
        for label, keys in observed.items()
        if set(keys) - set(DEFAULT_REPEATS_ALLOWED.get(label, {}))
    }
    assert not undeclared, (
        "a fixture answers its question's current default, so the render is the same without the key "
        "and the next editor cannot tell intent from boilerplate: drop the key, or declare it in "
        f"DEFAULT_REPEATS_ALLOWED with the reason it is load-bearing: {undeclared}"
    )
    stale = {
        label: sorted(set(DEFAULT_REPEATS_ALLOWED[label]) - set(observed.get(label, [])))
        for label in DEFAULT_REPEATS_ALLOWED
        if set(DEFAULT_REPEATS_ALLOWED[label]) - set(observed.get(label, []))
    }
    assert not stale, (
        "DEFAULT_REPEATS_ALLOWED declares a repeat that no longer exists, so the registry is stale in "
        f"the other direction and must drop the entry: {stale}"
    )


def _default_repeats() -> dict[str, list[str]]:
    """Fixture label -> the answer keys whose value equals the question's default."""
    observed: dict[str, list[str]] = {}
    for label, cases in _fixtures().items():
        for case in cases:
            for key, value in case.items():
                question = QUESTIONS.get(key)
                if question is not None and question.default is not None and question.default == value:
                    observed.setdefault(label, []).append(key)
    return observed


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


def test_agent_gate_stays_absent_from_the_example_fixture():
    """example-answers.yml deliberately does NOT state `use_recommended_agent`.

    The question is asked only for library / cli (questions/_common_a.yml's
    `when`), and the example is a data_science project -- so the key would
    change nothing about the example itself. But example-answers.yml is also
    the base fixtures/support.py `copy_project` derives its library / cli
    renders from, and copier uses a data-supplied value even for a question
    whose `when` is false: a `false` here would flip `agent_scaffold` on
    (questions/_internal.yml) for every derived fixture. The non-recommended
    agent route is exercised where it belongs instead -- the cli witness leaf
    `project_type=cli/gate=off:use_recommended_agent` and
    test_example_layers.py's `use_recommended_agent=False` renders.
    """
    assert "use_recommended_agent" not in EXAMPLE_ANSWERS, (
        "use_recommended_agent in example-answers.yml leaks agent_scaffold=true into"
        " every library / cli render copy_project derives from this file; see this"
        " test's docstring before changing that on purpose"
    )


def test_batch_sample_base_is_the_shared_answer_set():
    """batches/base.yml is documented as the same starting point the tests use."""
    assert BATCH_BASE == answers.BASE, (
        "batches/base.yml and tools/answers.py BASE diverge, so `task batch` renders a different "
        f"project than the pytest fast paths:\n  batch: {BATCH_BASE}\n  tests: {answers.BASE}"
    )
