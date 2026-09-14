"""Tests for tools/answers_for.py -- the inverse template.

The unit tests run on crafted render contexts (plain dicts), so the
constraint language, the exact filtering, the diagnostics and the cache are
verified in milliseconds. The two render-proof tests each pay one real
witness render (~1s, unmarked like tests/test_mcp_server.py's render tests --
nothing leaves the machine, no venv, no network); they prove the feature's
point end to end: the answers a match reports really render into a tree that
satisfies the constraints it was asked for.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import answers_for  # noqa: E402
from tools import predicates  # noqa: E402

KNOWN = frozenset({"docker", "mcp_effective", "docs_type", "sphinx", "project_type", "license", "license_effective"})

# Three crafted render contexts (the shapes the real pass produces; ids are
# real witness leaves so recommend() can resolve the ships and the requests).
LEAF_A = "project_type=cli/gate=off:use_recommended_agent"
LEAF_B = "project_type=cli/gate=off:use_recommended_agent/include=include_bot"
LEAF_K = "project_type=online_judge/gate=off:use_recommended_docs/oj=data_science/kaggle"
CONTEXTS: dict[str, dict[str, Any]] = {
    LEAF_A: {"docker": False, "mcp_effective": False, "docs_type": "zensical", "project_type": "cli"},
    LEAF_B: {
        "docker": False,
        "mcp_effective": False,
        "docs_type": "zensical",
        "project_type": "cli",
        "bot_effective": True,
    },
    LEAF_K: {
        "docker": False,
        "mcp_effective": False,
        "docs_type": "zensical",
        "kaggle": True,
        "use_gpu_effective": True,
    },
}


def patched_contexts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve the crafted contexts from load_contexts (no copier pass)."""
    monkeypatch.setattr(answers_for, "load_contexts", lambda root=TOP: CONTEXTS)


# --------------------------------------------------------------------------- #
# the constraint language
# --------------------------------------------------------------------------- #


def test_every_constraint_form_parses():
    forms = answers_for.parse_constraints(
        ["docker", "docker=true", "-docker", "docs_type=sphinx", "docs_type!=sphinx", "license=MIT"],
        KNOWN,
    )
    assert [(c.name, c.negated, c.value) for c in forms] == [
        ("docker", False, None),
        ("docker", False, "true"),
        ("docker", True, None),
        ("docs_type", False, "sphinx"),
        ("docs_type", True, "sphinx"),
        ("license", False, "MIT"),
    ]
    assert forms[0].raw == "docker" and forms[3].raw == "docs_type=sphinx"


def test_malformed_constraints_are_refused():
    for token in ("", "   ", "=cli", "docker=", "-docker=true", "-docker!=true"):
        with pytest.raises(ValueError, match=r"constraint|--|no (name|value)"):
            answers_for.parse_constraints([token], KNOWN)


def test_unknown_name_suggests_the_closest_real_names():
    with pytest.raises(ValueError) as excinfo:
        answers_for.parse_constraints(["spinx=true"], KNOWN)
    assert "sphinx" in str(excinfo.value)
    with pytest.raises(ValueError) as excinfo:
        answers_for.parse_constraints(["zzzzzzzz=true"], KNOWN)
    assert "any question or internal" in str(excinfo.value)


def test_known_names_exclude_copier_plumbing_and_the_clock():
    contexts = {"leaf": {"_commit": "abc", "now": "whenever", "docker": False}}
    assert answers_for.known_names(contexts) == frozenset({"docker"})


def test_satisfied_covers_truthiness_equality_and_negation():
    context: dict[str, Any] = {"docker": False, "sphinx": True, "docs_type": "zensical", "license": None}
    (truthy, eq_true, falsy, eq_str, ne_str, ne_str_other) = answers_for.parse_constraints(
        ["sphinx", "sphinx=true", "-sphinx", "docs_type=zensical", "docs_type!=sphinx", "docs_type!=zensical"], KNOWN
    )
    assert answers_for.satisfied(truthy, context) is True
    assert answers_for.satisfied(eq_true, context) is True
    assert answers_for.satisfied(falsy, context) is False
    assert answers_for.satisfied(eq_str, context) is True
    assert answers_for.satisfied(ne_str, context) is True
    # the negated equality fails on the value the leaf actually has
    assert answers_for.satisfied(ne_str_other, context) is False
    # a boolean never matches a word but true/false, and None never matches
    (eq_bad_word, eq_missing) = answers_for.parse_constraints(["sphinx=1", "license=MIT"], KNOWN)
    assert answers_for.satisfied(eq_bad_word, context) is False
    assert answers_for.satisfied(eq_missing, context) is False


# --------------------------------------------------------------------------- #
# exact filtering and the no-match diagnostic
# --------------------------------------------------------------------------- #


def test_match_filters_exactly_and_in_id_order():
    constraints = answers_for.parse_constraints(["docker=false", "project_type=cli"], KNOWN)
    matching, diagnostic = answers_for.match(constraints, CONTEXTS)
    assert matching == [LEAF_A, LEAF_B]
    assert diagnostic is None


def test_match_all_returns_every_leaf():
    matching, _ = answers_for.match(answers_for.parse_constraints(["docs_type=zensical"], KNOWN), CONTEXTS)
    assert matching == sorted(CONTEXTS)


def test_diagnose_names_the_biggest_eliminator_and_the_nearest_leaf():
    constraints = answers_for.parse_constraints(["docker=true", "mcp_effective=true", "docs_type=zensical"], KNOWN)
    matching, diagnostic = answers_for.match(constraints, CONTEXTS)
    assert matching == [] and diagnostic is not None
    assert diagnostic["eliminated"] == [
        {"constraint": "docker=true", "failed": 3},
        {"constraint": "mcp_effective=true", "failed": 3},
        {"constraint": "docs_type=zensical", "failed": 0},
    ]
    nearest = diagnostic["nearest"]
    assert nearest["leaf"] == LEAF_A  # first id among the 1/3 ties
    assert (nearest["satisfied"], nearest["of"]) == (1, 3)
    assert nearest["misses"] == [
        {"constraint": "docker=true", "observed": "false"},
        {"constraint": "mcp_effective=true", "observed": "false"},
    ]


# --------------------------------------------------------------------------- #
# the context cache
# --------------------------------------------------------------------------- #


def test_context_key_hashes_the_questionnaire_not_the_bodies(tmp_path: Path):
    (tmp_path / "tests" / "matrix").mkdir(parents=True)
    (tmp_path / "questions").mkdir()
    (tmp_path / "copier.yml").write_text("project_type:\n  type: str\n")
    (tmp_path / "questions" / "a.yml").write_text("x:\n")
    (tmp_path / "tests" / "matrix" / "witnesses.jsonl").write_text("{}\n")
    (tmp_path / "template").mkdir()
    (tmp_path / "template" / "README.md.jinja").write_text("body v1")
    first = answers_for.context_key(tmp_path)
    (tmp_path / "template" / "README.md.jinja").write_text("body v2")  # a body edit
    assert answers_for.context_key(tmp_path) == first
    (tmp_path / "questions" / "a.yml").write_text("x: changed\n")  # a questionnaire edit
    assert answers_for.context_key(tmp_path) != first


def test_load_contexts_runs_the_pass_once_and_validates_the_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls: list[int] = []

    def fake_pass(requests: list[Any]):
        calls.append(len(calls))
        for request in requests:
            yield request, {"project_type": "cli"}, None

    monkeypatch.setattr(answers_for, "CACHE", tmp_path)
    monkeypatch.setattr(predicates, "leaf_contexts", fake_pass)

    contexts = answers_for.load_contexts()
    requests = answers_for.load_witnesses()
    assert set(contexts) == {request.id for request in requests}
    assert contexts[requests[0].id] == {"project_type": "cli"}
    assert calls == [0]
    # a second call is served from the cache: the pass never re-runs
    assert answers_for.load_contexts() == contexts
    assert calls == [0]
    # a cache missing leaves (a stale or truncated file) is regenerated
    stale = json.loads((tmp_path / "contexts" / f"{answers_for.context_key(TOP)}.json").read_text())
    del stale[requests[0].id]
    (tmp_path / "contexts" / f"{answers_for.context_key(TOP)}.json").write_text(json.dumps(stale))
    assert set(answers_for.load_contexts()) == {request.id for request in requests}
    assert calls == [0, 1]


# --------------------------------------------------------------------------- #
# the payload
# --------------------------------------------------------------------------- #


def test_recommend_reports_matches_with_their_ships_and_yaml(monkeypatch: pytest.MonkeyPatch):
    patched_contexts(monkeypatch)
    payload = answers_for.recommend(["bot_effective=true"])
    assert payload["constraints"] == ["bot_effective=true"]
    assert (payload["matched"], payload["shown"]) == (1, 1)
    (leaf,) = payload["leaves"]
    assert leaf["id"] == LEAF_B
    assert yaml.safe_load(leaf["answers_yaml"]) == leaf["answers"]
    matrix = answers_for.invariants_load()
    assert leaf["ships"] == list(matrix.expect_for(leaf["answers"])["files"])
    assert leaf["absent"] == list(matrix.expect_for(leaf["answers"])["absent"])
    assert payload["diagnostic"] is None and payload["render"] is None


def test_recommend_caps_the_reported_leaves_not_the_count(monkeypatch: pytest.MonkeyPatch):
    patched_contexts(monkeypatch)
    payload = answers_for.recommend(["docs_type=zensical"], limit=1)
    assert payload["matched"] == len(CONTEXTS)
    assert payload["shown"] == 1 and len(payload["leaves"]) == 1


def test_recommend_without_a_match_carries_the_diagnostic(monkeypatch: pytest.MonkeyPatch):
    patched_contexts(monkeypatch)
    payload = answers_for.recommend(["docker=true", "mcp_effective=true"])
    assert payload["matched"] == 0 and payload["leaves"] == []
    assert payload["diagnostic"]["eliminated"][0]["failed"] == len(CONTEXTS)
    assert payload["render"] is None  # nothing to render


def test_recommend_refuses_unknown_names(monkeypatch: pytest.MonkeyPatch):
    patched_contexts(monkeypatch)
    with pytest.raises(answers_for.ConstraintError) as excinfo:
        answers_for.recommend(["kagl=true"])
    assert "kaggle" in str(excinfo.value)


def test_answers_yaml_is_data_file_ready():
    answers = {"project_type": "cli", "docker": False, "list": ["a", "b"]}
    text = answers_for.answers_yaml(answers)
    assert yaml.safe_load(text) == answers
    assert text == yaml.safe_dump(dict(sorted(answers.items())), sort_keys=False)


# --------------------------------------------------------------------------- #
# the artifact half of the render proof
# --------------------------------------------------------------------------- #


def test_artifact_proof_of_a_name_gated_file(tmp_path: Path):
    (tmp_path / ".dockerignore").write_text("*.log\n")
    (present, negated, absent) = answers_for.parse_constraints(["docker=true", "-docker", "docker=false"], KNOWN)
    assert answers_for.artifact_proof(present, tmp_path)[1] is True
    assert answers_for.artifact_proof(negated, tmp_path)[1] is False
    assert answers_for.artifact_proof(absent, tmp_path)[1] is False
    assert answers_for.artifact_proof(absent, tmp_path)[0] == "artifact"
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    assert answers_for.artifact_proof(present, empty)[1] is False


def test_artifact_proof_reads_the_license_from_pyproject(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('name = "x"\nlicense = "MIT"\n')
    (mit, agpl, not_mit) = answers_for.parse_constraints(
        ["license=MIT", "license_effective=AGPL-3.0", "license!=MIT"], KNOWN
    )
    assert answers_for.artifact_proof(mit, tmp_path)[1] is True
    assert answers_for.artifact_proof(agpl, tmp_path)[1] is False
    assert answers_for.artifact_proof(not_mit, tmp_path)[1] is False
    assert "MIT" in answers_for.artifact_proof(mit, tmp_path)[2]


def test_artifact_proof_of_an_unregistered_name_is_none(tmp_path: Path):
    (constraint,) = answers_for.parse_constraints(["project_type=cli"], KNOWN)
    kind, ok, _ = answers_for.artifact_proof(constraint, tmp_path)
    assert (kind, ok) == (None, True)


def _kaggle_request() -> Any:
    return next(
        request for request in answers_for.load_witnesses() if "kaggle" in request.id and "include" not in request.id
    )


# --------------------------------------------------------------------------- #
# the render proof (one real witness render each, ~1s: no venv, no network)
# --------------------------------------------------------------------------- #


def test_render_proof_holds_on_a_real_leaf():
    constraints = answers_for.parse_constraints(
        ["use_gpu_effective=true", "kaggle=true", "license_effective=MIT"],
        frozenset({"use_gpu_effective", "kaggle", "license_effective"}),
    )
    proof = answers_for.prove_render(_kaggle_request(), constraints)
    assert proof["ok"] is True and proof["error"] is None
    assert proof["batch"]["ok"] is True  # the ordinary witness verdicts passed too
    checks = {check["constraint"]: check for check in proof["constraints"]}
    assert checks["use_gpu_effective=true"]["context_ok"] is True
    assert checks["use_gpu_effective=true"]["artifact"] == "artifact"
    assert checks["use_gpu_effective=true"]["artifact_ok"] is True  # Dockerfile.gpu really rendered
    assert checks["kaggle=true"]["artifact"] is None  # context proof only
    assert checks["license_effective=MIT"]["artifact_ok"] is True


def test_render_proof_catches_a_contradiction():
    (constraint,) = answers_for.parse_constraints(["use_gpu_effective=false"], frozenset({"use_gpu_effective"}))
    proof = answers_for.prove_render(_kaggle_request(), [constraint])
    assert proof["ok"] is False
    (check,) = proof["constraints"]
    assert check["context_ok"] is False  # the fresh pass over the recorded answers disagrees
    assert check["artifact_ok"] is False  # and the tree carries the artifact the answer denies


def test_main_exit_codes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    patched_contexts(monkeypatch)
    assert answers_for.main(["--require", "bot_effective=true"]) == 0
    assert answers_for.main(["--require", "docker=true"]) == 1  # no match: loud, not silent
    assert answers_for.main(["--require", "spinx=true"]) == 2  # unknown name
    assert "nothing matches" in capsys.readouterr().err
