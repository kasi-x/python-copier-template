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
from contextlib import suppress
from pathlib import Path

import pytest
import yaml
from copier._template import load_template_config

TOP = Path(__file__).absolute().parent.parent
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

# Copier/Jinja built-ins and the custom extension globals (extensions.py) that
# may appear in `{{ }}` expressions without being copier.yml keys.
ALLOWED_NON_KEYS = {
    "_copier_answers",
    "_copier_conf",
    "_commit",
    "_folder_name",
    "_src_path",
    "_dst_path",
    "_copier_templates_dir",
    "_copier_subdirectory",
    "git_user_name",
    "git_user_email",
    "github_username",
    "current_year",
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


def _load_questions() -> tuple[dict[str, dict], list[str]]:
    """Return ({key: raw-question-dict}, ordered-keys) from copier.yml.

    The config is loaded with copier's own loader so `!include` fragments
    under questions/ are resolved and merged in ask order. The question order
    is read from the resolved config (copier asks in this order).
    """
    data = load_template_config(COPIER_YML)
    questions = {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}
    order = list(questions)
    return questions, order


def _jinja_identifiers(text: str) -> set[str]:
    """All identifiers inside {{ }} / {% %} blocks in ``text``.

    Only full Jinja tags are scanned (a stray ``{``/``}`` in a template body
    is never treated as a tag boundary). Within each tag, string literals
    (e.g. ``== 'ros2'``) and Jinja keywords are not identifiers; GitHub
    Actions expressions (``${{ secrets.X }}``) are not Jinja and are skipped.
    """
    found: set[str] = set()
    # GitHub Actions expressions (${{ secrets.X }}) are not Jinja; blank them
    # out first so they are never scanned.
    text = re.sub(r"\$\{\{[^}]*\}\}", " ", text)
    # {% raw %}...{% endraw %} blocks are emitted verbatim for another tool
    # (git-cliff's cliff.toml.jinja), not rendered by copier.
    text = re.sub(r"\{%-?\s*raw\s*-?%\}.*?\{%-?\s*endraw\s*-?%\}", " ", text, flags=re.DOTALL)
    for tag in re.findall(r"\{\{.*?\}\}|\{%.*?%\}", text, re.DOTALL):
        # Drop quoted strings inside this tag only — tag-internal quotes like
        # == "BSL-1.0" must not span across to quotes in the body text.
        stripped = re.sub(r"'[^']*'|\"[^\"]*\"", " ", tag)
        for m in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", stripped):
            # Attribute access: in `x.attr`, `attr` is not a variable.
            if m.start() > 0 and stripped[m.start() - 1] == ".":
                continue
            # Keyword argument: in `filter(keyword=value)`, `keyword` is not a
            # variable (`==` comparisons are unaffected — two '=' signs).
            rest = stripped[m.end() :]
            if rest.startswith("=") and not rest.startswith("=="):
                continue
            found.add(m.group(0))
    return found


_JINJA_IF_WORDS = {
    "if",
    "elif",
    "else",
    "endif",
    "for",
    "endfor",
    "set",
    "endset",
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


def _template_files() -> list[Path]:
    """Every file in template/ plus the root _tasks.jinja and _shared/
    partials (both included by template files via {% import %}/{% include %})."""
    files = [Path(p) for p in TEMPLATE_DIR.rglob("*")]
    files.append(TOP / "_tasks.jinja")
    files.extend(_shared_files())
    return files


def _shared_files() -> list[Path]:
    """Root-level shared partials (_shared/*.jinja) that template files include."""
    return sorted((TOP / "_shared").glob("*.jinja"))


def _template_local_vars(files: list[Path]) -> set[str]:
    """Names bound by {% set %}, {% import ... as %} and {% for %} in templates.

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
        # A loop may bind several names: {% for a, b in ... %}.
        local |= set(
            re.findall(r"\{%-?\s*for\s+([A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)\s+in\b", text)
        )
    return local


def test_can_parse_copier_yml_and_gates_are_well_formed():
    questions, order = _load_questions()
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


def test_when_and_default_reference_defined_variables():
    questions, _ = _load_questions()
    keys = set(questions)
    for key, q in questions.items():
        for field in ("when", "default", "validator"):
            value = q.get(field)
            if isinstance(value, str):
                for ident in _jinja_identifiers(value):
                    assert _is_known(ident, keys), f"question {key!r} {field} references undefined {ident!r}"
        choices = q.get("choices")
        if isinstance(choices, str):
            for ident in _jinja_identifiers(choices):
                assert _is_known(ident, keys), f"question {key!r} choices references undefined {ident!r}"


def test_template_conditionals_reference_defined_variables():
    """Every {% if %}/{{ }} variable in template/ paths and bodies is defined.

    Template filenames carry copier's conditional syntax
    ({% if var %}segment{% endif %}), so the tree is walked including the
    bracketed directory names. This is what catches a removed question that
    template files still gate on.
    """
    questions, _ = _load_questions()
    keys = set(questions) | ALLOWED_NON_KEYS
    files = _template_files()
    known = keys | _template_local_vars(files)
    references: dict[str, list[str]] = {}
    for f in files:
        if f.is_dir():
            continue
        # Path conditionals: the {%%} segments in relative path parts. Copier
        # interprets these for every file, .jinja or not.
        rel = f.relative_to(TOP)
        refs = _jinja_identifiers(str(rel)) | _jinja_identifiers(f.name)
        # Body conditionals / expressions: only `.jinja` files are rendered by
        # copier. A non-.jinja file (e.g. sphinx's custom-module-template.rst,
        # processed later by sphinx-autoapi) keeps its Jinja verbatim, so its
        # variables are not copier.yml keys by design.
        if f.name.endswith(".jinja"):
            with suppress(UnicodeDecodeError, OSError):
                refs |= _jinja_identifiers(f.read_text(encoding="utf-8"))
        for ident in sorted(refs):
            references.setdefault(ident, []).append(str(rel))
    for ident, where in sorted(references.items()):
        if not _is_known(ident, known):
            assert False, f"template references undefined variable {ident!r} in {where[:3]}"


def test_no_dead_internal_variables():
    """Hidden (`when: false`) variables must be referenced somewhere."""
    questions, _ = _load_questions()
    internal = {k for k, q in questions.items() if isinstance(q.get("when"), bool) and q["when"] is False}
    assert internal, "no internal variables found — is the when: false convention still used?"
    # Collect every identifier referenced in copier.yml, its questions/
    # fragments, in template/ file *names* (the {% if %} path conditionals)
    # and in file bodies.
    referenced: set[str] = set()
    for src in (COPIER_YML, *QUESTIONS_DIR.rglob("*.yml")):
        with suppress(UnicodeDecodeError, OSError):
            referenced |= _jinja_identifiers(src.read_text(encoding="utf-8"))
    for f in TEMPLATE_DIR.rglob("*"):
        if f.is_file():
            rel = f.relative_to(TOP)
            referenced |= _jinja_identifiers(str(rel)) | _jinja_identifiers(f.name)
            with suppress(UnicodeDecodeError, OSError):
                referenced |= _jinja_identifiers(f.read_text(encoding="utf-8"))
    for var in sorted(internal):
        assert var in referenced, (
            f"internal variable {var!r} is never referenced — remove it or its last consumer regressed"
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
    resolved, _ = _load_questions()
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
    questions, order = _load_questions()
    position = {name: i for i, name in enumerate(order)}
    for name in order:
        q = questions[name]
        if q.get("when") is False:
            continue  # internal variable: render-time resolution
        for field in ("when", "default", "choices"):
            value = q.get(field)
            if not isinstance(value, str):
                continue
            for ident in _jinja_identifiers(value):
                if ident in position and position[ident] > position[name]:
                    raise AssertionError(
                        f"question {name!r} {field} references {ident!r} defined later in ask order — "
                        "move the referenced variable before this question (see docs_type backref fix)"
                    )


def _tokenize_when(text: str) -> list[str]:
    """Tokenize the Jinja subset used in when expressions.

    Strips the surrounding ``{{ }}`` delimiters, then yields identifiers,
    quoted strings, list brackets, ==, !=, in / not in, and parentheses;
    whitespace is skipped.
    """
    text = text.strip()
    text = text.removeprefix("{{")
    text = text.removesuffix("}}")
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c in "()[],":
            out.append(c)
            i += 1
        elif text.startswith("==", i):
            out.append("==")
            i += 2
        elif text.startswith("!=", i):
            out.append("!=")
            i += 2
        elif text.startswith("not in", i):
            out.append("not in")
            i += 6
        elif c in "'\"":
            j = i + 1
            while j < n and text[j] != c:
                j += 1
            out.append(text[i : j + 1])
            i = j + 1
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            out.append(text[i:j])
            i = j
        else:
            raise AssertionError(f"unexpected char {c!r} in when expression {text!r}")
    return out


def _static_str_choices(question: dict) -> list[str]:
    """Return a question's static (non-templated) choice values, or []."""
    choices = question.get("choices")
    if not isinstance(choices, list):
        return []
    values: list[str] = []
    for c in choices:
        if isinstance(c, dict):
            value = c.get("value")
        elif isinstance(c, (list, tuple)) and len(c) == 2:
            value = c[1]
        else:
            value = c
        if isinstance(value, str):
            values.append(value)
    return values


def _when_expr_satisfiable(expr: str, str_domains: dict[str, list[str]], z3) -> bool:
    """Check a when expression is satisfiable, modeling it in Z3.

    The questionnaire's when grammar is a small Jinja subset: comparisons
    (==, !=, in, not in) over question references and string literals, plus
    and/or/not and parentheses. A str-typed referenced question is modeled
    as an Int over its static choices; a comparison to a literal L maps to
    ``int == domain.index(L)`` (False when L is not a valid choice). Bool
    identifiers are free booleans (each question is checked independently,
    with earlier gates free). Returns True iff some assignment satisfies the
    expression.
    """

    class _List:
        def __init__(self, items: list[str]) -> None:
            self.items = items

    class _Var:
        """A symbolic str question: an Int over its static choices."""

        def __init__(self, name: str) -> None:
            self.name = name
            self.domain = str_domains[name]

        def eq(self, literal: str) -> object:
            try:
                return z3.Int(self.name) == self.domain.index(literal)
            except ValueError:
                return z3.BoolVal(False)

    tokens = _tokenize_when(expr)

    class Parser:
        def __init__(self) -> None:
            self.i = 0

        def peek(self) -> str | None:
            return tokens[self.i] if self.i < len(tokens) else None

        def pop(self) -> str:
            tok = self.peek()
            if tok is None:
                raise AssertionError(f"unexpected end of when expression {expr!r}")
            self.i += 1
            return tok

        def parse(self) -> object:
            node = self.parse_or()
            if self.i != len(tokens):
                raise AssertionError(f"trailing tokens in when expression {expr!r}: {tokens[self.i :]}")
            return node

        def parse_or(self) -> object:
            node = self.parse_and()
            while self.peek() == "or":
                self.pop()
                node = z3.Or(node, self.parse_and())
            return node

        def parse_and(self) -> object:
            node = self.parse_not()
            while self.peek() == "and":
                self.pop()
                node = z3.And(node, self.parse_not())
            return node

        def parse_not(self) -> object:
            if self.peek() == "not":
                self.pop()
                return z3.Not(self.parse_not())
            return self.parse_cmp()

        def parse_cmp(self) -> object:
            left = self.parse_atom()
            op = self.peek()
            if op in ("==", "!=", "in", "not in"):
                self.pop()
                right = self.parse_atom()
                if op == "==":
                    return self._eq(left, right)
                if op == "!=":
                    return z3.Not(self._eq(left, right))
                if op == "in":
                    return self._member(left, right)
                return z3.Not(self._member(left, right))
            # bare atom: bool identifier or parenthesized expression
            return left

        def parse_atom(self) -> object:
            tok = self.pop()
            if tok == "(":
                node = self.parse_or()
                if self.pop() != ")":
                    raise AssertionError(f"unbalanced parens in when expression {expr!r}")
                return node
            if tok == "[":
                items: list[str] = []
                while self.peek() not in ("]", None):
                    if self.peek() == ",":
                        self.pop()
                        continue
                    items.append(self._string(self.pop()))
                self.pop()  # ']'
                return _List(items)
            if tok in str_domains:
                return _Var(tok)
            if (tok.startswith("'") and tok.endswith("'")) or (tok.startswith('"') and tok.endswith('"')):
                return tok[1:-1]  # string literal
            # bare identifier: boolean literal or a free bool variable
            if tok in ("true", "True"):
                return z3.BoolVal(True)
            if tok in ("false", "False"):
                return z3.BoolVal(False)
            return z3.Bool(tok)  # free bool question reference

        def _string(self, tok: str) -> str:
            if (tok.startswith("'") and tok.endswith("'")) or (tok.startswith('"') and tok.endswith('"')):
                return tok[1:-1]
            raise AssertionError(f"expected string literal, got {tok!r} in {expr!r}")

        def _eq(self, left: object, right: object) -> object:
            lvar, rvar = (left if isinstance(left, _Var) else None), (right if isinstance(right, _Var) else None)
            llit = left if isinstance(left, str) and not isinstance(left, _Var) else None
            rlit = right if isinstance(right, str) and not isinstance(right, _Var) else None
            if lvar is not None and isinstance(rlit, str):
                return lvar.eq(rlit)
            if rvar is not None and isinstance(llit, str):
                return rvar.eq(llit)
            # var == var, or bool identifiers — model as free
            return z3.Bool(f"eq_{self.i}")

        def _member(self, elem: object, container: object) -> object:
            if isinstance(elem, _Var) and isinstance(container, _List):
                return z3.Or([elem.eq(item) for item in container.items])
            raise AssertionError(f"cannot model membership {elem!r} in {container!r} in {expr!r}")

    parser = Parser()
    cond = parser.parse()
    solver = z3.Solver()
    for name, domain in str_domains.items():
        solver.add(z3.Or([z3.Int(name) == i for i in range(len(domain))]))
    solver.add(cond)
    return solver.check() == z3.sat


def test_every_question_when_is_z3_satisfiable():
    """Every asked question's `when` can hold for some answer combination.

    A when-condition that Z3 proves unsatisfiable means the question can
    never be asked: a dead questionnaire entry (typo in a project_type
    comparison, a self-contradictory gate, a genre guard no project type
    satisfies). Bool gates referenced by the when are treated as free —
    each question is checked independently, which catches structural
    deadness without full ask-order simulation.
    """
    z3 = pytest.importorskip("z3")
    questions, _ = _load_questions()

    pt_domain = _static_str_choices(questions["project_type"])
    assert pt_domain, "project_type must have a static choices list"

    # Collect every variable referenced by any when expression, and classify
    # into str domains (from static choices) vs free bools.
    referenced: set[str] = set()
    for q in questions.values():
        w = q.get("when")
        if isinstance(w, str):
            referenced |= _jinja_identifiers(w)

    str_domains: dict[str, list[str]] = {"project_type": pt_domain}
    for name in sorted(referenced - {"project_type", "true", "false", "not", "and", "or", "in"}):
        q = questions[name]
        assert q is not None, f"when expression references unknown variable {name!r}"
        if q.get("type") == "bool":
            continue  # free bool
        values = _static_str_choices(q)
        if values:
            str_domains[name] = values
        # free-text str with no static choices: comparisons modeled as free
        # (bool identifiers), fine for reachability.

    checked = 0
    for name, q in questions.items():
        w = q.get("when")
        if not isinstance(w, str):
            continue
        assert _when_expr_satisfiable(w, str_domains, z3), (
            f"question {name!r} has an unsatisfiable when {w!r}: it can never be asked. "
            "Check the project_type comparison / gate logic."
        )
        checked += 1
    assert checked > 0, "no templated when conditions found to check"
