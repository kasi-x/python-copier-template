"""Differential test: the `when` model against copier's own Jinja evaluation.

tools/when_model.py decides with Z3 whether a question's `when` can hold. That
is a re-implementation of Jinja semantics for a small grammar, so it is only
as good as its agreement with Jinja itself — real Jinja is the oracle here.
For every leaf of the declared witness space (tools/z3_witnesses.py: the same
answers tools/batch.py renders), copier's own questionnaire machinery
(`Worker._ask` + `Question.get_when`) answers every templated `when`, and the
model is asked the same question at the same answers (its `pinned` mode).
Every disagreement is a model bug — a projection hole that would otherwise
leave the structural checks green while they prove nothing.

What this covers
- every templated `when` in the questionnaire (discovered from the
  questionnaire itself, so a newly added one is compared too), against every
  declared leaf and probe: 11781 (question, answer set) verdicts.
- the probes in `_PROBES`: six answer sets outside the leaf space, each one
  there to vary a value the leaves hold at its copier default (git_platform,
  cloud_provider, fair, package_manager, existing_project, and ros2 + pixi).
  Without them some expressions would only ever be seen in one
  polarity, which cannot distinguish "the model agrees" from "the model
  always says False".
- every identifier of each expression, pinned to the answer copier produced:
  str answers (including questions whose `choices` are templated, which the
  model otherwise leaves as a free boolean) and bool answers.
- that `when_model.str_domains` — the domain the production callers pass —
  contains every answer copier actually gives those questions: a domain that
  silently dropped a choice would make the model's comparisons wrong for
  real answers.
- both polarities of *every* expression, asserted per expression below: a
  `when` whose inputs no answer set varies fails the sweep instead of
  quietly proving half of it.

What this does not cover (a narrower claim beats an overstated one)
- Only concrete assignments are compared, not the *abstract* satisfiability
  the production callers ask for (tools/z3_witnesses.py checks whether a
  branch is reachable at all). The two agree as long as pinning is sound,
  which is what the comparison below establishes; the abstract side is
  exercised by tests/test_copier_structure.py's sweeps (a typo'd
  project_type, a self-contradictory gate, an impossible genre combo).
- The questionnaire's current expressions only: every `when` here is a
  comparison against a literal, a membership test, or a boolean combination
  of those. Model paths that exist for other Jinja (a comparison between two
  question references, an identifier that is not a question, a filter) are
  not reachable from this questionnaire and so are not compared here — the
  two-reference shape has its own pinned test below instead of copier
  verdicts.
- The answer sets above only: the leaves' dimensions, plus one probe per
  value the leaves keep at its default. An answer combination outside both
  (some cross-product of gitlab + pixi + aws, say) is not compared.
"""

import sys
import tempfile
from collections.abc import Iterator
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

# z3-solver is a declared dev dependency (pyproject.toml): a missing z3 is a
# broken environment, not an unsupported platform, so this imports it loudly
# instead of skipping. The silent `pytest.importorskip("z3")` this replaces was
# the open half of TODO §19's "network 系テストの扱いを見直す".
import z3

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_batch.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from copier._main import Worker  # noqa: E402
from copier._user_data import Question  # noqa: E402
from tools import when_model  # noqa: E402
from tools import z3_witnesses  # noqa: E402

# Jinja keywords `when_model.jinja_identifiers` reports as identifiers; they
# are operators in the grammar the encoder parses, not variables to pin.
_OPERATORS = {"and", "or", "not", "in", "true", "false", "True", "False", "is", "defined", "none", "None"}

MAX_REPORTED = 10

# Answer sets outside the declared leaves, each closing a `when` that the leaf
# space holds constant: the leaves vary project_type, one gate and one include,
# and leave every other question at the default the witnesses render with.
# Every probe is a real branch (copier validates these answers) built on the
# same BASE the witnesses pin, and each one is named for the value it varies.
_PROBES: tuple[tuple[str, dict[str, Any]], ...] = (
    # BASE pins git_platform to github.com, so github_org/gitlab_group only
    # ever hold one way there.
    ("probe:gitlab", {"project_type": "library", "git_platform": "gitlab.com"}),
    # cloud_provider stays 'none' on every leaf.
    ("probe:aws", {"project_type": "library", "use_recommended_integrations": False, "cloud_provider": "aws"}),
    # `fair` stays False (author_orcid) and `existing_project` False
    # (adopt_protect).
    ("probe:fair", {"project_type": "library", "use_recommended_license": False, "fair": True}),
    ("probe:existing", {"project_type": "library", "existing_project": True}),
    # package_manager stays at its default, so task_runner_pixi never holds.
    ("probe:pixi", {"project_type": "library", "use_recommended_toolchain": False, "package_manager": "pixi"}),
    # use_recommended_toolchain's own `when` is only false for ros2 + pixi.
    ("probe:ros2-pixi", {"project_type": "ros2", "ros2_package_manager": "pixi"}),
)


def _memoize_compilation(env: Any) -> None:
    """Compile each distinct template source in ``env`` at most once.

    `Question.render_value` compiles its template on every call, and this
    sweep asks the same ~300 sources once per answer set (109 questions x 211
    answer sets), which dwarfs the comparison itself. `from_string` is pure for a
    fixed environment — a compiled Template keeps no per-render state, it
    builds a new context each time — so memoizing it changes the cost, not a
    single verdict: every answer below is still copier's own. A non-str
    source is passed straight through, because copier relies on
    `from_string` rejecting a value that is not a template.
    """
    original = env.from_string
    compiled: dict[str, Any] = {}

    def from_string(source: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(source, str) and not args and not kwargs:
            if source not in compiled:
                compiled[source] = original(source)
            return compiled[source]
        return original(source, *args, **kwargs)

    env.from_string = from_string


def _copier_answers(worker: Worker, answers: dict[str, Any]) -> tuple[dict[str, bool], Mapping[str, Any]]:
    """Copier's verdict for every templated `when` of one answer set, and its context.

    `Worker._ask` is the questionnaire pass copier itself runs (it resolves
    the internal `when: false` variables in definition order); `get_when` is
    the method that decides whether a question is asked, so the verdicts here
    are the questionnaire's own answers, not a second implementation. Both
    are private, because copier exposes no other way to run that pass.
    """
    worker.data = dict(answers)
    worker._ask()  # pyright: ignore[reportPrivateUsage]
    context = worker._render_context()  # pyright: ignore[reportPrivateUsage]
    verdicts: dict[str, bool] = {}
    for name, details in worker.template.questions_data.items():
        if not isinstance(details.get("when"), str):
            continue
        question = Question(
            answers=worker.answers,
            context=context,
            jinja_env=worker.jinja_env,
            settings=worker.settings,
            var_name=name,
            **details,
        )
        verdicts[name] = question.get_when()
    return verdicts, context


def _pins(when: str, context: Mapping[str, Any]) -> dict[str, str | bool] | None:
    """The model's `pinned` answers for one expression, or None if it cannot be pinned.

    None means the expression reads something this sweep cannot hand the
    model as a concrete answer (a list, a missing variable), i.e. that
    expression is not covered.
    """
    pinned: dict[str, str | bool] = {}
    for ident in when_model.jinja_identifiers(when):
        if ident in _OPERATORS:
            continue
        value = context.get(ident)
        if isinstance(value, (str, bool)):
            pinned[ident] = value
        else:
            return None
    return pinned


def _answer_sets(leaves: list[Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every answer set the sweep compares: each declared leaf, then each probe."""
    for leaf in leaves:
        yield leaf.id, leaf.answers
    for name, overrides in _PROBES:
        yield name, {**z3_witnesses.BASE, **overrides}


def test_model_agrees_with_copier_on_every_leaf_and_probe():
    """The model's verdict is copier's verdict, at every answer set compared."""
    _leaf_space, leaves = z3_witnesses.build()
    questions, _order = when_model.load_questions()
    whens = {name: q["when"] for name, q in questions.items() if isinstance(q.get("when"), str)}
    domains = when_model.str_domains(questions)

    polarities: dict[str, set[bool]] = {name: set() for name in whens}
    uncovered: set[str] = set()
    divergences: list[str] = []
    domain_gaps: list[str] = []
    compared = 0
    verdicts_by_pin: dict[tuple[str, tuple[tuple[str, str | bool], ...]], bool] = {}

    with tempfile.TemporaryDirectory() as dst:
        # vcs_ref=HEAD: the oracle is the checkout's own questionnaire (the
        # same source tools/z3_witnesses.py enumerates), not the newest tag's
        # -- a question added after the tag would otherwise never be seen by
        # copier here and the sweep would call it one-sided.
        worker = Worker(src_path=str(TOP), dst_path=Path(dst), defaults=True, quiet=True, vcs_ref="HEAD")
        _memoize_compilation(worker.jinja_env)
        for label, answers in _answer_sets(leaves):
            verdicts, context = _copier_answers(worker, answers)
            for name, domain in domains.items():
                answer = context.get(name)
                if isinstance(answer, str) and answer not in domain:
                    domain_gaps.append(f"{label}: {name} = {answer!r}, which is not in the model's domain {domain}")
            for name, oracle in verdicts.items():
                when = whens[name]
                polarities[name].add(oracle)
                pins = _pins(when, context)
                if pins is None:
                    uncovered.add(name)
                    continue
                key = (when, tuple(sorted(pins.items())))
                if key not in verdicts_by_pin:  # the same answers ask the same question once
                    verdicts_by_pin[key] = when_model.when_expr_satisfiable(when, domains, z3, pinned=pins)
                model = verdicts_by_pin[key]
                compared += 1
                if model != oracle:
                    divergences.append(
                        f"{label}: question {name!r} when {when!r} -> copier says {oracle}, "
                        f"the model says {model}; answers {dict(sorted(pins.items()))}"
                    )

    assert compared, "no when expression was compared: `when` is no longer templated anywhere?"
    one_sided = sorted(name for name, seen in polarities.items() if len(seen) < 2)
    assert not one_sided, (
        f"{len(one_sided)} when expression(s) were only ever seen in one polarity, so the other side of "
        f"them is unproven: {one_sided}\n  vary their inputs with another entry in _PROBES, or say why "
        "the other polarity is unreachable"
    )
    assert not uncovered, (
        f"{len(uncovered)} when expression(s) read a value this sweep cannot pin to the model, "
        f"so they are not covered: {sorted(uncovered)}"
    )
    assert not domain_gaps, "the model's str domains are missing answers copier gives:\n  " + "\n  ".join(
        domain_gaps[:MAX_REPORTED]
    )
    assert not divergences, (
        f"{len(divergences)} of {compared} (question, answer set) verdicts diverge from copier's own "
        "Jinja evaluation:\n  " + "\n  ".join(divergences[:MAX_REPORTED])
    )


@pytest.mark.parametrize(("left", "right", "expected"), [("ros2", "ros2", True), ("ros2", "ctf", False)])
def test_a_comparison_between_two_references_compares_answers_not_indices(left: str, right: str, expected: bool):
    """`x == y` compares the two answers, not each question's choice index.

    No questionnaire `when` uses this shape today, so the leaf sweep above
    cannot reach it and its docstring lists it as uncovered. It is still
    reachable — a `when` may compare two questions — and the encoder used to
    fall back to a free boolean there, which under `pinned` made `x == y`
    satisfiable whatever the answers were. Since both questions index their own
    choice lists, encoding it as `Int(x) == Int(y)` is just as wrong in the
    other direction ("ros2" == "ctf" would hold at index 0). Jinja's own
    verdict is the answer equality the expectations here spell out.
    """
    expr = "{{ project_type == oj_kind }}"
    questions, _order = when_model.load_questions()
    domains = when_model.str_domains(questions)

    verdict = when_model.when_expr_satisfiable(expr, domains, z3, pinned={"project_type": left, "oj_kind": right})

    assert verdict is expected, (
        f"the model says {verdict} for {left!r} == {right!r}; copier's Jinja says {left == right} "
        "(a two-reference comparison is the equality of the answers)"
    )
