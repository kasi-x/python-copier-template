"""Structural maintenance checks for copier.yml and the questionnaire docs.

test_micropython_maintenance.py guards the MicroPython pins the same way:
static, offline assertions over the template source that catch drift early.
This module guards the questionnaire's shape:

- the `use_recommended_*` gates appear in the canonical order and are
  well-formed bool questions;
- docs/reference/questionnaire.md's gate table stays in sync with copier.yml;
- every variable referenced in a question's `when`/`default`/`choices` or in a
  `template/` conditional exists (a removed question leaves a dangling
  reference — the ascii_banner removal regressed exactly this way);
- every `when: false` internal variable is actually used somewhere (no dead
  hidden variables);
- the two OJ predicate internals (`oj_bare` / `no_pkg`) keep exactly their
  documented derivations and the raw inline forms they replaced
  (`online_judge and not kaggle`, the `micropython_pkg`+`oj_code` pair in one
  condition) never reappear in the template sources;
- the questionnaire fragments under questions/ are complete (their union
  equals the resolved questionnaire, no duplicate keys across fragments) and
  every question reference is forward-only (a question must only reference
  variables defined earlier in ask order — the docs_type back-reference bug
  regressed exactly this way);
- every asked question's `when` condition is satisfiable for at least one
  combination of earlier answers (a question that can never be asked is dead)
  and no internal variable's derivation is contradictory (Z3-backed checks).
"""

import re
import sys
from contextlib import suppress
from pathlib import Path

import pytest
import yaml
import z3

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_batch.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools import when_model  # noqa: E402

COPIER_YML = TOP / "copier.yml"
QUESTIONNAIRE_DOC = TOP / "docs" / "reference" / "questionnaire.md"
TEMPLATE_DIR = TOP / "template"
QUESTIONS_DIR = TOP / "questions"

# The canonical gate order — matches the order asked in copier.yml (project
# type first, then each area, then Project Details).
CANONICAL_GATES = [
    "use_recommended_agent",
    "use_recommended_toolchain",
    "use_recommended_data_science",
    "use_recommended_polish",
    "use_recommended_docs",
    "use_recommended_quality",
    "use_recommended_license",
    "use_recommended_integrations",
    "use_recommended_web_api",
    "use_recommended_security",
]

# Copier/Jinja built-ins that may appear in `{{ }}` expressions without
# being copier.yml keys.
ALLOWED_NON_KEYS = {
    "_copier_answers",
    "_copier_conf",
    "_commit",
    "_folder_name",
    "_src_path",
    "_dst_path",
    "_copier_templates_dir",
    "_copier_subdirectory",
    "strftime",
    "now",
    "today",
    # Jinja / copier built-in filters and tests used in the questionnaire.
    "regex_search",
    "replace",
    "lower",
    "upper",
    "length",
    "to_nice_yaml",
    "tojson",
    "map",
    "join",
    "trim_start_matches",
    "date",
    "striptags",
    "split",
    "truncate",
}


_JINJA_IF_WORDS = {
    "if",
    "elif",
    "else",
    "endif",
    "for",
    "endfor",
    "set",
    "endset",
    "macro",
    "endmacro",
    "import",
    "include",
    "from",
    "as",
    "with",
    "context",
    "in",
    "not",
    "and",
    "or",
    "is",
    "defined",  # {% if x is defined %}
    "true",
    "false",
    "none",
    "None",
    "_",  # {% set _ = ... %} loop-accumulator idiom
}


def _is_known(name: str, keys: set[str]) -> bool:
    return name in keys or name in ALLOWED_NON_KEYS or name in _JINJA_IF_WORDS


def template_files() -> list[Path]:
    """Every file in template/ plus the root _tasks.jinja and _shared/
    partials (both included by template files via {% import %}/{% include %})."""
    files = [Path(p) for p in TEMPLATE_DIR.rglob("*")]
    files.append(TOP / "_tasks.jinja")
    files.extend(shared_files())
    return files


def shared_files() -> list[Path]:
    """Root-level shared partials (_shared/*.jinja) that template files include."""
    return sorted((TOP / "_shared").glob("*.jinja"))


def _template_local_vars(files: list[Path]) -> set[str]:
    """Names bound by {% set %}, {% import ... as %}, {% for %} and
    {% macro %} in templates.

    These are template-local definitions, not copier.yml keys.
    """
    local: set[str] = set()
    for f in files:
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        local |= set(re.findall(r"\{%-?\s*set\s+([A-Za-z_][A-Za-z0-9_]*)", text))
        local |= set(re.findall(r"\{%-?\s*import\s+[\"'][^\"']+[\"']\s+as\s+([A-Za-z_][A-Za-z0-9_]*)", text))
        # A macro definition binds its name and its parameters, both of which
        # are bare identifiers in the macro body: {% macro serialize(x, y=1) %}.
        for name, params in re.findall(r"\{%-?\s*macro\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)", text):
            local.add(name)
            local |= {p.split("=", 1)[0].strip() for p in params.split(",") if p.strip()}
        # A loop may bind several names: {% for a, b in ... %}.
        local |= set(
            re.findall(r"\{%-?\s*for\s+([A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)\s+in\b", text)
        )
    return local


def test_can_parse_copier_yml_and_gates_are_well_formed():
    questions, order = when_model.load_questions()
    # Every gate exists, is a bool defaulting to true, and has help text.
    for gate in CANONICAL_GATES:
        assert gate in questions, f"{gate} missing from copier.yml"
        assert questions[gate].get("type") == "bool", f"{gate} should be a bool"
        assert questions[gate].get("default") is True, f"{gate} should default to true"
        assert questions[gate].get("help"), f"{gate} should explain its recommendation"
    # The gates appear in the canonical order (project-type questions come
    # first, so filter to just the gates when comparing order).
    gate_order = [k for k in order if k in CANONICAL_GATES]
    assert gate_order == CANONICAL_GATES, f"gate order drifted: {gate_order}"


def test_questionnaire_gate_table_matches_copier_yml():
    """The gate table in the questionnaire reference stays in sync."""
    doc = QUESTIONNAIRE_DOC.read_text(encoding="utf-8")
    # Table rows look like "| `use_recommended_*` | ... |".
    doc_gates = re.findall(r"\| `(use_recommended_[a-z_]+)` \|", doc)
    assert doc_gates == CANONICAL_GATES, f"questionnaire.md gate table drifted: {doc_gates}"


def test_every_asked_question_has_a_default():
    """`--defaults` only auto-answers questions that HAVE a default; a
    question without one still prompts and breaks non-interactive generation
    (gitlab_group regressed exactly this way). Every question that can
    actually be asked (`when` not statically false) must carry a default."""
    questions, _ = when_model.load_questions()
    for name, question in questions.items():
        if name.startswith("_"):
            continue
        if question.get("when") in (False, "false"):
            continue
        assert "default" in question, (
            f"question {name!r} can be asked but has no default: `copier copy --defaults` would stop and prompt for it"
        )


def test_when_and_default_reference_defined_variables():
    questions, _ = when_model.load_questions()
    keys = set(questions)
    for key, q in questions.items():
        for field in ("when", "default", "validator"):
            value = q.get(field)
            if isinstance(value, str):
                for ident in when_model.jinja_identifiers(value):
                    assert _is_known(ident, keys), f"question {key!r} {field} references undefined {ident!r}"
        choices = q.get("choices")
        if isinstance(choices, str):
            for ident in when_model.jinja_identifiers(choices):
                assert _is_known(ident, keys), f"question {key!r} choices references undefined {ident!r}"


def test_template_conditionals_reference_defined_variables():
    """Every {% if %}/{{ }} variable in template/ paths and bodies is defined.

    Template filenames carry copier's conditional syntax
    ({% if var %}segment{% endif %}), so the tree is walked including the
    bracketed directory names. This is what catches a removed question that
    template files still gate on.
    """
    questions, _ = when_model.load_questions()
    keys = set(questions) | ALLOWED_NON_KEYS
    files = template_files()
    known = keys | _template_local_vars(files)
    references: dict[str, list[str]] = {}
    for f in files:
        if f.is_dir():
            continue
        # Path conditionals: the {%%} segments in relative path parts. Copier
        # interprets these for every file, .jinja or not.
        rel = f.relative_to(TOP)
        refs = when_model.jinja_identifiers(str(rel)) | when_model.jinja_identifiers(f.name)
        # Body conditionals / expressions: only `.jinja` files are rendered by
        # copier. A non-.jinja file (e.g. sphinx's custom-module-template.rst,
        # processed later by sphinx-autoapi) keeps its Jinja verbatim, so its
        # variables are not copier.yml keys by design.
        if f.name.endswith(".jinja"):
            with suppress(UnicodeDecodeError, OSError):
                refs |= when_model.jinja_identifiers(f.read_text(encoding="utf-8"))
        for ident in sorted(refs):
            references.setdefault(ident, []).append(str(rel))
    for ident, where in sorted(references.items()):
        if not _is_known(ident, known):
            assert False, f"template references undefined variable {ident!r} in {where[:3]}"


def test_no_dead_internal_variables():
    """Hidden (`when: false`) variables must be referenced somewhere."""
    questions, _ = when_model.load_questions()
    internal = {k for k, q in questions.items() if isinstance(q.get("when"), bool) and q["when"] is False}
    assert internal, "no internal variables found — is the when: false convention still used?"
    # Collect every identifier referenced in copier.yml, its questions/
    # fragments, in template/ file *names* (the {% if %} path conditionals)
    # and in file bodies.
    referenced: set[str] = set()
    for src in (COPIER_YML, *QUESTIONS_DIR.rglob("*.yml")):
        with suppress(UnicodeDecodeError, OSError):
            referenced |= when_model.jinja_identifiers(src.read_text(encoding="utf-8"))
    for f in TEMPLATE_DIR.rglob("*"):
        if f.is_file():
            rel = f.relative_to(TOP)
            referenced |= when_model.jinja_identifiers(str(rel)) | when_model.jinja_identifiers(f.name)
            with suppress(UnicodeDecodeError, OSError):
                referenced |= when_model.jinja_identifiers(f.read_text(encoding="utf-8"))
    for var in sorted(internal):
        assert var in referenced, (
            f"internal variable {var!r} is never referenced — remove it or its last consumer regressed"
        )


# ---------------------------------------------------------------------------
# OJ predicate rot-guard (TODO §18 item 2).
#
# The template used to re-derive two predicates inline at every consumer:
# `online_judge and not kaggle` (now the `oj_bare` internal — the four
# code-submission judges AND ctf, i.e. an OJ workspace without kaggle's real
# package) and the `micropython_pkg … oj_code` pair (now the `no_pkg`
# internal — renders no installable/importable CPython package). These tests
# keep the named internals authoritative: the raw forms must not reappear in
# template/ file names or bodies, _shared/ partials, _tasks.jinja or
# copier.yml, and the internals themselves must keep their documented
# derivations (so a "simplification" of `oj_bare` to `oj_code` — which would
# push ctf's package-less workspace through the package gates — cannot drift
# in silently).
# ---------------------------------------------------------------------------

OJ_BARE_DEFINITION = "{{ online_judge and not kaggle }}"
NO_PKG_DEFINITION = "{{ micropython_pkg or oj_code }}"

# `micropython_pkg`/`oj_code` joined by and/or inside one expression — the
# shape `no_pkg` replaced. Co-occurrences in *different* conditions are fine
# (separate {% if %} tags or distinct ternaries sharing a line, e.g. the
# basedpyright excludes), so bare co-occurrence is not the test.
_PAIR_IN_ONE_CONDITION = re.compile(
    r"\b(?:micropython_pkg|oj_code)\s+(?:and|or)\s+(?:not\s+)?(?:micropython_pkg|oj_code)\b"
)


def _rot_guard_sources() -> list[str]:
    """File names + bodies the raw predicate forms are banned from: template/
    (paths carry copier's {% if %} name conditionals), _shared/ partials,
    _tasks.jinja and copier.yml. questions/ is deliberately excluded — it
    holds the internals' documented definitions, asserted separately below.
    """
    sources = [COPIER_YML.read_text(encoding="utf-8")]
    for f in template_files():
        if f.is_dir():
            continue
        sources.append(str(f.relative_to(TOP)))
        with suppress(UnicodeDecodeError, OSError):
            sources.append(f.read_text(encoding="utf-8"))
    return sources


def test_oj_predicate_raw_forms_are_named_internals():
    """The raw predicate forms §18 item 2 eliminated never reappear.

    Nothing is allow-listed: after the unification there are zero occurrences
    outside questions/online_judge.yml, where the internals are defined.
    """
    banned = "online_judge and not kaggle"
    for src in _rot_guard_sources():
        assert banned not in src, (
            f"raw OJ predicate reappeared — write the `oj_bare` internal instead: {src[:160]!r}"
        )
        match = _PAIR_IN_ONE_CONDITION.search(src)
        if match is not None:
            raise AssertionError(
                f"micropython_pkg+oj_code pair in one condition reappeared — "
                f"write the `no_pkg` internal instead: {match.group(0)!r} in {src[:160]!r}"
            )


def test_oj_predicate_internals_keep_documented_definitions():
    """`oj_bare` / `no_pkg` keep exactly the derivation the template relies on.

    `oj_bare` is deliberately NOT `oj_code` (ctf is in, kaggle is out); both
    expressions are load-bearing for docker / vulture / setuptools_scm /
    testpaths / dependencies gates, so the exact strings are pinned.
    """
    questions, _ = when_model.load_questions()
    for name, definition in (("oj_bare", OJ_BARE_DEFINITION), ("no_pkg", NO_PKG_DEFINITION)):
        assert name in questions, f"{name} internal is missing from questions/"
        assert questions[name].get("when") is False, f"{name} must stay an internal (when: false)"
        assert questions[name].get("default") == definition, (
            f"{name} drifted from its documented derivation {definition!r}: got {questions[name].get('default')!r}"
        )


# ---------------------------------------------------------------------------
# Questionnaire completeness checks.
#
# The copier.yml questionnaire is split across questions/*.yml fragments and
# merged by copier's `!include` loader. These tests verify the split is
# *complete*: fragments hold every question exactly once, references only go
# forward in ask order, and every question's `when`/`default` derivation is
# satisfiable (Z3-backed) so no question is dead or contradictory.
# ---------------------------------------------------------------------------


def _fragment_questions() -> dict[str, dict]:
    """Merge the raw YAML of every questions/*.yml fragment.

    Unlike copier's loader this does NOT apply its reverse-document merge
    semantics (which would hide duplicate keys); a plain dict-build instead
    surfaces duplicates as overwrites we can detect.
    """
    merged: dict[str, dict] = {}
    for f in sorted(QUESTIONS_DIR.rglob("*.yml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        for key, value in doc.items():
            assert key not in merged, (
                f"question {key!r} defined more than once across questions/ fragments (second in {f.name})"
            )
            merged[key] = value
    return merged


def test_fragments_are_complete_and_duplicate_free():
    """questions/*.yml fragments hold every resolved question exactly once."""
    resolved, _ = when_model.load_questions()
    fragments = _fragment_questions()
    # The resolved config is the union of fragments + the inline project_type
    # in copier.yml.
    inline = set(resolved) - set(fragments)
    assert inline == {"project_type"}, f"unexpected inline questions: {inline}"
    assert set(fragments) == set(resolved) - {"project_type"}, (
        f"fragments diverge from resolved config: "
        f"only-in-fragments={sorted(set(fragments) - set(resolved))} "
        f"only-in-resolved={sorted(set(resolved) - set(fragments))}"
    )


def test_question_references_are_forward_only():
    """An asked question must only reference variables defined earlier.

    Copier resolves a question's `when`/`default`/`choices` when it is
    reached in ask order, so referencing a later variable leaves it Undefined
    (falsy) — the docs_type -> micropython_pkg back-reference bug. Internal
    (`when: false`) variables may reference anything: they are resolved at
    render time after every answer exists.
    """
    questions, order = when_model.load_questions()
    position = {name: i for i, name in enumerate(order)}
    for name in order:
        q = questions[name]
        if q.get("when") is False:
            continue  # internal variable: render-time resolution
        for field in ("when", "default", "choices"):
            value = q.get(field)
            if not isinstance(value, str):
                continue
            for ident in when_model.jinja_identifiers(value):
                if ident in position and position[ident] > position[name]:
                    raise AssertionError(
                        f"question {name!r} {field} references {ident!r} defined later in ask order — "
                        "move the referenced variable before this question (see docs_type backref fix)"
                    )


def test_internal_variable_references_are_forward_only():
    """A `when: false` internal variable must only reference internals defined
    earlier in the chain.

    Copier evaluates internal defaults in definition order, so an internal
    referencing a later internal renders as Undefined (falsy) — the
    mcp_effective -> web_api ordering bug, where web_api+MCP silently
    generated no server file. Asked questions are excluded here (covered by
    test_question_references_are_forward_only); only internal-to-internal
    edges are checked.
    """
    questions, order = when_model.load_questions()
    position = {name: i for i, name in enumerate(order)}
    for name in order:
        q = questions[name]
        if q.get("when") is not False:
            continue
        for field in ("default", "choices"):
            value = q.get(field)
            if not isinstance(value, str):
                continue
            for ident in when_model.jinja_identifiers(value):
                if ident not in position:
                    continue
                target = questions[ident]
                if target.get("when") is not False:
                    continue  # asked answer: always resolved before render
                if position[ident] > position[name]:
                    raise AssertionError(
                        f"internal variable {name!r} {field} references {ident!r} defined later — "
                        "move the referenced internal earlier (see mcp_effective ordering fix)"
                    )


def test_every_question_when_is_z3_satisfiable():
    """Every asked question's `when` can hold for some answer combination.

    A when-condition that Z3 proves unsatisfiable means the question can
    never be asked: a dead questionnaire entry (typo in a project_type
    comparison, a self-contradictory gate, a genre guard no project type
    satisfies). Bool gates referenced by the when are treated as free —
    each question is checked independently, which catches structural
    deadness without full ask-order simulation. That the model's verdicts
    are the same as real Jinja evaluation at a known answer set is
    tests/test_when_model.py's business, not this structural check's.
    """
    questions, _ = when_model.load_questions()
    str_domains = when_model.str_domains(questions)

    checked = 0
    for name, q in questions.items():
        w = q.get("when")
        if not isinstance(w, str):
            continue
        assert when_model.when_expr_satisfiable(w, str_domains, z3), (
            f"question {name!r} has an unsatisfiable when {w!r}: it can never be asked. "
            "Check the project_type comparison / gate logic."
        )
        checked += 1
    assert checked > 0, "no templated when conditions found to check"


def test_z3_sweep_detects_typo_project_type():
    """Error sweep: a typo'd project_type literal is unsatisfiable.

    Guards the guard — proves when_model.when_expr_satisfiable rejects the
    'librry' class of typos instead of vacuously passing.
    """
    questions, _ = when_model.load_questions()
    assert not when_model.when_expr_satisfiable("{{ project_type == 'librry' }}", when_model.str_domains(questions), z3)


def test_z3_sweep_detects_self_contradictory_gate():
    """Error sweep: `X and not X` is unsatisfiable."""
    questions, _ = when_model.load_questions()
    assert not when_model.when_expr_satisfiable(
        "{{ use_recommended_docs and not use_recommended_docs }}",
        when_model.str_domains(questions),
        z3,
    )


def test_z3_sweep_detects_impossible_genre_combo():
    """Error sweep: two distinct project_type literals conjoined."""
    questions, _ = when_model.load_questions()
    assert not when_model.when_expr_satisfiable(
        "{{ project_type == 'cli' and project_type == 'ros2' }}",
        when_model.str_domains(questions),
        z3,
    )


@pytest.mark.xfail(
    reason="free-bool modelling: unknown names are satisfiable by design; "
    "test_when_and_default_reference_defined_variables owns this"
)
def test_z3_sweep_wrong_variable_name_is_out_of_scope():
    """Error sweep (known gap): a misspelled variable is satisfiable to Z3.

    Unknown identifiers model as free bools, so Z3 cannot see the
    always-falsy Undefined. Detection belongs to the loader-level
    reference test, not Z3 — this pins the division of labour.
    """
    questions, _ = when_model.load_questions()
    assert not when_model.when_expr_satisfiable(
        "{{ project_type == 'cli' and use_recommended_doccs }}",
        when_model.str_domains(questions),
        z3,
    )
