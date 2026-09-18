#!/usr/bin/env python3
"""Model the questionnaire's `when` expressions, on the one shared parse.

Copier's `when` conditions are Jinja, and the questionnaire's shape is only
checkable if something can reason about them: which project types can reach a
question, which gate is asked where, whether a branch is satisfiable at all.
This module is that reasoner, and it encodes a `when` expression as a Z3
formula. The layering is fixed: tools/questionnaire.py owns parsing (the one
`!include` resolver, which also keeps each question's source fragment), and
this module owns only the `when`-expression semantics layered on the raw view
it exposes (`load_questions` delegates to `questionnaire.load_raw_questions`).
Copier's own loader is not consulted here -- it survives as a differential
oracle in tests, which pin that it agrees with the parser.

What it models
- the `when` grammar the questionnaire actually uses: `==`, `!=`, `in` and
  `not in` over question references and string literals, combined with
  `and`/`or`/`not` and parentheses;
- a question with static `choices` as an Int over its choice values, so
  `x == 'value'` becomes `Int(x) == domain.index('value')` and `x in [a, b]`
  becomes a disjunction. A literal outside the domain is False, which is what
  makes a typo'd `project_type == 'librry'` unsatisfiable;
- every other identifier as a free boolean, and each question is checked
  independently with the earlier gates free.

What it deliberately does not model
- Jinja beyond that subset: filters, attribute access, arithmetic, and `is`
  tests (the tokenizer raises on them rather than guessing).
- a comparison whose operand is a plain boolean identifier, or a boolean
  against a string: Jinja's `False == 'x'` is never true, but an unpinned str
  reference is a free boolean here, so the two cases are indistinguishable and
  the comparison stays free. Two str references (`x == y`) *are* modeled:
  equality of their choice indices.
- A question whose `choices` are templated or absent (`package_manager`,
  `oj_kind`) has no fixed domain, so it is a free boolean unless the caller
  supplies a domain for it. A comparison against such a variable is then
  unconstrained: satisfiable whatever the answer. Real Jinja is the only
  oracle for that, and tests/test_when_model.py is the differential test
  against it.
- Ask order and the derived internals: a `when: false` variable (has_web_api,
  kaggle, ...) is a free boolean, never computed from the questions it
  derives from.
- Unknown identifiers: a name that is not a question is satisfiable by
  design, so a misspelled variable is invisible here. The reference check in
  tests/test_copier_structure.py owns that class of bug.

Callers: tests/test_copier_structure.py (the questionnaire's shape),
tools/z3_witnesses.py (the leaf space, whose branches are cross-checked
through this encoder) and tests/test_when_model.py (the differential test
against copier/Jinja evaluation).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:  # tools/ is no root package (pyproject.toml)
    sys.path.insert(0, str(TOP))

from tools import questionnaire  # noqa: E402

COPIER_YML = TOP / "copier.yml"


def load_questions() -> tuple[dict[str, dict], list[str]]:
    """Return ({key: raw-question-dict}, ordered-keys) from copier.yml.

    A thin delegate to `questionnaire.load_raw_questions`: the dataclass
    parser in tools/questionnaire.py is the one `!include` resolver (only its
    Question records keep the source fragment a question came from, which the
    raw view cannot carry), so this module re-parses nothing and owns the
    `when`-expression semantics on top. The shape is unchanged -- the same
    raw dicts in copier's ask order the module always returned.
    """
    return questionnaire.load_raw_questions(COPIER_YML)


#: Jinja keywords `jinja_identifiers` reports as identifiers (the same set
#: tests/test_when_model.py pins): they are operators of the grammar, never
#: variables a condition reads. Consumers of the scanner subtract this set;
#: tools/question_graph.py extends it with `if`/`else`, which only its
#: `default:` expressions use.
JINJA_OPERATORS = frozenset(
    {"and", "or", "not", "in", "true", "false", "True", "False", "is", "defined", "none", "None"}
)


def jinja_identifiers(text: str) -> set[str]:
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


def static_str_choices(question: dict) -> list[str]:
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


def str_domains(questions: dict[str, dict], pt_domain: list[str] | None = None) -> dict[str, list[str]]:
    """The str-typed domain of every question the questionnaire's `when`s read.

    A referenced question with static choices contributes its choice values.
    A bool question, a free-text question, and a question whose choices are
    templated (its values depend on the earlier answers) are left out, so the
    encoder models them as free booleans. `pt_domain` is the project_type
    domain the caller's space uses; it defaults to the question's own static
    choices.
    """
    if pt_domain is None:
        pt_domain = static_str_choices(questions["project_type"])
    referenced: set[str] = set()
    for question in questions.values():
        when = question.get("when")
        if isinstance(when, str):
            referenced |= jinja_identifiers(when)
    domains: dict[str, list[str]] = {"project_type": pt_domain}
    for name in sorted(referenced):
        question = questions.get(name)
        if question is None or question.get("type") == "bool":
            continue
        values = static_str_choices(question)
        if values:
            domains[name] = values
    return domains


def tokenize_when(text: str) -> list[str]:
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
        elif text.startswith("not in", i) and not (text[i + 6 : i + 7].isalnum() or text[i + 6 : i + 7] == "_"):
            # The lookahead keeps `not include_web_api` from reading as the
            # operator `not in` plus a truncated identifier.
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


def when_expr_satisfiable(
    expr: str,
    str_domains: dict[str, list[str]],
    z3: ModuleType,
    *,
    pinned: Mapping[str, Any] | None = None,
) -> bool:
    """Check a when expression is satisfiable, modeling it in Z3.

    The questionnaire's when grammar is a small Jinja subset: comparisons
    (==, !=, in, not in) over question references and string literals, plus
    and/or/not and parentheses. A str-typed referenced question is modeled
    as an Int over its static choices; a comparison to a literal L maps to
    ``int == domain.index(L)`` (False when L is not a valid choice). Bool
    identifiers are free booleans (each question is checked independently,
    with earlier gates free). Returns True iff some assignment satisfies the
    expression.

    `pinned` asks the same question at a known assignment instead: each
    listed variable is fixed to that answer (a str answer makes the variable
    a one-value domain, so its comparisons are equality against the real
    answer; a bool answer fixes the free boolean) and the result is then
    whether the expression holds *there*. That is what
    tests/test_when_model.py compares against copier's own Jinja evaluation
    of the same expression — including for the str variables whose `choices`
    are templated and which `str_domains` therefore leaves free.
    """

    class _List:
        def __init__(self, items: list[str]) -> None:
            self.items = items

    class _Var:
        """A symbolic str question: an Int over its static choices."""

        def __init__(self, name: str) -> None:
            self.name = name
            self.domain = domains[name]

        def eq(self, literal: str) -> object:
            try:
                return z3.Int(self.name) == self.domain.index(literal)
            except ValueError:
                return z3.BoolVal(False)  # noqa: FBT003  WHYNOT: z3's own API takes a Python bool.

    domains = dict(str_domains)
    fixed: list[object] = []
    for name, answer in (pinned or {}).items():
        if name in domains and not isinstance(answer, str):
            raise AssertionError(f"cannot pin str question {name!r} to {answer!r}")
        if isinstance(answer, str):
            domains[name] = [answer]
        elif isinstance(answer, bool):
            fixed.append(z3.Bool(name) == z3.BoolVal(answer))  # noqa: FBT003  WHYNOT: z3's own API.
        else:
            raise AssertionError(f"cannot pin {name!r} to {answer!r}: only str and bool answers are modeled")

    tokens = tokenize_when(expr)

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
            if tok in domains:
                return _Var(tok)
            if (tok.startswith("'") and tok.endswith("'")) or (tok.startswith('"') and tok.endswith('"')):
                return tok[1:-1]  # string literal
            # bare identifier: boolean literal or a free bool variable
            if tok in ("true", "True"):
                return z3.BoolVal(True)  # noqa: FBT003  WHYNOT: z3's own API takes a Python bool.
            if tok in ("false", "False"):
                return z3.BoolVal(False)  # noqa: FBT003  WHYNOT: z3's own API takes a Python bool.
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
            if lvar is not None and rvar is not None:
                # Two str references: equality of the *answers*, not of the
                # indices (each question's domain indexes its own values, so
                # `Int(x) == Int(y)` would compare positions, not answers).
                # tests/test_when_model.py caught exactly that mistake, which is
                # why the pair is encoded as a disjunction over the answers both
                # domains share.
                shared = [value for value in lvar.domain if value in rvar.domain]
                if not shared:
                    return z3.BoolVal(False)  # noqa: FBT003  WHYNOT: z3's own API takes a Python bool.
                return z3.Or(
                    [
                        z3.And(
                            z3.Int(lvar.name) == lvar.domain.index(value),
                            z3.Int(rvar.name) == rvar.domain.index(value),
                        )
                        for value in shared
                    ]
                )
            # bool identifiers, or a bool against a str: free. Jinja would say
            # False for the mixed case, but an unpinned str reference is a free
            # boolean here, so the model cannot tell the two apart. The free
            # boolean is named by its OPERANDS, not the parser position, so the
            # same comparison repeated inside one expression is the same
            # unknown (a caller comparing two texts -- e.g. the XOR
            # equivalence check in tools/predicates.py -- would otherwise see
            # each copy as an independent boolean and call identical
            # predicates different).
            return z3.Bool(f"eq_{left}_{right}")

        def _member(self, elem: object, container: object) -> object:
            if isinstance(elem, _Var) and isinstance(container, _List):
                return z3.Or([elem.eq(item) for item in container.items])
            raise AssertionError(f"cannot model membership {elem!r} in {container!r} in {expr!r}")

    parser = Parser()
    cond = parser.parse()
    solver = z3.Solver()
    for name, domain in domains.items():
        solver.add(z3.Or([z3.Int(name) == i for i in range(len(domain))]))
    solver.add(*fixed)
    solver.add(cond)
    return solver.check() == z3.sat
