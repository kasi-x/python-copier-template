#!/usr/bin/env python3
"""Classify every boolean condition site on the render + question surface.

TODO.md §18's unification work (items 2/3/4) was done by hand: an inventory
classified every condition site, equivalent forms were named as internal
variables (`oj_bare`, `no_pkg`), and rot-guards were written by hand. This
module mechanizes that inventory as a permanent facility, built on machinery
that already exists: the questionnaire loaders (tools/questionnaire.py,
tools/when_model.py), the 225-leaf witness space (tools/z3_witnesses.py), the
leaf-class rows (tools/invariants.py) and the Z3 `when` encoder. Four
capabilities:

1. **Site collection** (``collect_sites``): every boolean condition on the
   render + question surface -- question `when:`s, boolean internal variables
   (`when: false`, bool-typed defaults; string-valued internals like `pkg_dir`
   are not predicates), `{% if %}`/`{% elif %}` tags in template file NAMES,
   the same tags in file bodies across `template/`, `_shared/*.jinja` and
   `_tasks.jinja`, and the `when:` of each `_tasks:` entry. Each site records
   its location, the expression as written, and its kind.
2. **Evaluation** (``evaluate``): for every leaf answer set, copier's own pass
   runs once (the tests/test_when_model.py oracle pattern: `Worker._ask` +
   `_render_context`), and every site is rendered against the resulting
   context with copier's jinja env, truthed the way `Question.get_when`
   truths it (`cast_to_bool`). A site yields one boolean per leaf; sites that
   error or read non-scalar values are classed unevaluable and reported
   separately -- never crash the report.
3. **The report** (``main``): the classification tree from
   tests/matrix/invariants.yml (each row's leaf count, top-down with numbers),
   per-internal reference and fire counts, equivalence classes over the leaf
   space, mechanically-detected unification candidates, and shortcut
   suggestions (naming candidates above ``SHORTCUT_MIN_SITES`` sites;
   flattening candidates = internals that never split the space).
4. **The free-space oracle** (``FreeSpace``): whether two condition texts can
   ever disagree over the whole questionnaire space, decided with
   ``when_model.when_expr_satisfiable`` after substituting boolean internals
   by their definitions. tests/test_predicate_classifier.py is the guard that
   runs it: every unconditionally-equivalent (site, internal) pair must be a
   reference, a definition site, or declared in that test's registry.

Usage:

    python tools/predicates.py            # the human report (on stderr)
    python tools/predicates.py --json     # the machine report (stdout; prose stays on stderr)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zlib import crc32

import jinja2

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:  # tools/ is no root package (pyproject.toml)
    sys.path.insert(0, str(TOP))

from copier._main import Worker  # noqa: E402
from copier._tools import cast_to_bool  # noqa: E402
from tools import invariants  # noqa: E402
from tools import questionnaire  # noqa: E402
from tools import when_model  # noqa: E402
from tools import z3_witnesses  # noqa: E402

#: A raw (unnamed) equivalence class is a naming candidate only when it shows
#: up at this many distinct sites or more. Below that, look-alike conditions
#: are usually one-off phrasing rather than a concept worth naming; at three
#: or more, the same predicate is being re-spelled often enough that the next
#: edit can drift one copy -- the point where §18 named `oj_bare` / `no_pkg`.
SHORTCUT_MIN_SITES = 3

#: Kinds of condition site (the `Site.kind` values, and the report's buckets).
QUESTION = "question"
INTERNAL = "internal"
FILENAME = "filename"
BODY = "body"
TASK = "task"

#: The template surfaces body conditions are scanned in (repo-relative).
TASKS_FILE = "_tasks.jinja"
SHARED_GLOB = "_shared/*.jinja"
TEMPLATE_DIR = "template"

# Jinja block tags: the ones this scanner tracks, and the raw blocks it must
# blank first ({% raw %} output belongs to another tool, never to copier).
_BLOCK = re.compile(r"\{%-?\s*(if|elif|else|endif|for|endfor)\b\s*(.*?)\s*-?%\}", re.DOTALL)
_RAW = re.compile(r"\{%-?\s*raw\s*-?%\}.*?\{%-?\s*endraw\s*-?%\}", re.DOTALL)

# Jinja keywords `when_model.jinja_identifiers` reports as identifiers (the
# same set tests/test_when_model.py pins): they are operators of the grammar,
# never variables a condition reads.
_JINJA_OPERATORS = frozenset(
    {"and", "or", "not", "in", "true", "false", "True", "False", "is", "defined", "none", "None"}
)


@dataclass
class Site:
    """One boolean condition site, and its verdict on every witness leaf.

    ``expr`` is the condition as written (tag braces stripped) -- what a
    reader sees, what the reference counts and the free-space guard use.
    ``eval_expr`` is what the vector evaluates: for a branch in an
    `{% if %}`/`{% elif %}` chain this composes the guard ("none of the
    previous branches and this one"), which is when the branch actually
    renders. ``vector`` holds one bool per leaf, or ``None`` with ``error``
    set when the site is unevaluable.
    """

    kind: str
    location: str
    expr: str
    eval_expr: str
    refs: frozenset[str]
    vector: list[bool] | None = None
    error: str | None = None


def _inner(text: Any) -> str:
    """The expression inside a Jinja tag: `{{ x }}` -> `x`, already plain strings pass through."""
    inner = str(text).strip()
    if inner.startswith("{{") and inner.endswith("}}"):
        inner = inner[2:-2]
    return inner.strip("+- \t")


def _refs(text: str) -> frozenset[str]:
    """The identifiers a condition reads (when_model's scanner owns the rules; keywords are not reads)."""
    return frozenset(when_model.jinja_identifiers("{{ " + text + " }}")) - _JINJA_OPERATORS


def _site(kind: str, location: str, expr: str, eval_expr: str | None = None) -> Site:
    return Site(kind=kind, location=location, expr=expr, eval_expr=eval_expr or expr, refs=_refs(expr))


def _questionnaire_records() -> tuple[dict[str, questionnaire.Question], dict[str, Any]]:
    """The questionnaire as data: records by name, plus the `_`-prefixed settings."""
    questions, settings = questionnaire.load_questions()
    return {question.name: question for question in questions}, settings


def bool_internals(questions: dict[str, dict]) -> dict[str, str]:
    """The named boolean internals: `when: false` entries whose type is bool, name -> definition.

    The resolved copier.yml (when_model's loader) is the authority, per the
    render-reads-effective rule: these are the names render-side conditions
    are supposed to reference. String-valued internals (`pkg_dir`,
    `task_runner_effective`, ...) compute placements and names, not
    predicates, so they are not sites.
    """
    return {
        name: _inner(details.get("default"))
        for name, details in sorted(questions.items())
        if details.get("when") is False and details.get("type") == "bool" and details.get("default") is not None
    }


def _chain_eval(previous: list[str], expr: str) -> str:
    """When an `{% elif %}` branch actually renders: no earlier branch fired, and this one holds."""
    guards = " and ".join(f"not ({earlier})" for earlier in previous)
    return f"{guards} and ({expr})" if guards else expr


def _scan_blocks(text: str) -> list[tuple[int, str, str, str]]:
    """(line, keyword, expr-as-written, evaluated guard) for every top-level `{% if %}`/`{% elif %}`.

    `{% elif %}` guards are composed through their chain (``_chain_eval``).
    Conditions nested in `{% for %}` loops are skipped on purpose: they are
    per-iteration checks over loop variables (`t.shell` in a serializer), not
    predicates on the questionnaire, and would be unevaluable anyway.
    """
    found: list[tuple[int, str, str, str]] = []
    chains: list[list[str]] = []
    loop_depth = 0
    for match in _BLOCK.finditer(_RAW.sub(" ", text)):
        keyword, expr = match.group(1), _join_lines(match.group(2))
        line = text.count("\n", 0, match.start()) + 1
        if keyword == "for":
            loop_depth += 1
        elif keyword == "endfor":
            loop_depth -= 1
        elif keyword in ("if", "elif") and not loop_depth:
            if keyword == "if" or not chains:
                chains.append([])
            previous = chains[-1]
            evaluated = expr if keyword == "if" else _chain_eval(previous, expr)
            chains[-1].append(expr)
            found.append((line, keyword, expr, evaluated))
        elif keyword == "else" and chains:
            chains[-1] = ["true"]  # a branch after `else` can never render
        elif keyword == "endif" and chains:
            chains.pop()
    return found


def _join_lines(expr: str) -> str:
    """Multi-line conditions joined into one expression (the report prints one line per site)."""
    return " ".join(expr.split())


def _filename_sites() -> list[Site]:
    """`{% if %}`/`{% elif %}` tags in template path segments (copier renders the whole path).

    Directory segments are scanned once -- at the directory's own path -- not
    again for every file below them, so one gate in a directory name is one
    site.
    """
    sites: list[Site] = []
    root = TOP / TEMPLATE_DIR
    seen: set[tuple[str, str]] = set()
    for path in sorted({root, *root.rglob("*")}):
        parts = path.relative_to(root).parts
        for depth, segment in enumerate(parts):
            parent = Path(TEMPLATE_DIR, *parts[:depth]).as_posix()
            if (parent, segment) in seen:
                continue
            seen.add((parent, segment))
            base = Path(parent, segment).as_posix()
            for ordinal, (_line, _keyword, expr, evaluated) in enumerate(_scan_blocks(segment)):
                sites.append(_site(FILENAME, f"{base}::{ordinal}", expr, evaluated))
    return sites


def _body_files() -> list[Path]:
    """Every file copier renders as a template body: template/, _shared/*.jinja, _tasks.jinja."""
    root = TOP / TEMPLATE_DIR
    files = sorted(path for path in root.rglob("*") if path.is_file())
    files += sorted(TOP.glob(SHARED_GLOB))
    files.append(TOP / TASKS_FILE)
    return files


def _body_sites() -> list[Site]:
    """`{% if %}`/`{% elif %}` tags in file bodies, with their line numbers."""
    sites: list[Site] = []
    for path in _body_files():
        rel = path.relative_to(TOP).as_posix()
        for line, _keyword, expr, evaluated in _scan_blocks(path.read_text(encoding="utf-8")):
            sites.append(_site(BODY, f"{rel}:{line}", expr, evaluated))
    return sites


def _task_sites(settings: dict[str, Any]) -> list[Site]:
    """The `when:` of each `_tasks:` entry in copier.yml."""
    sites: list[Site] = []
    for index, entry in enumerate(settings.get("_tasks") or []):
        when = entry.get("when") if isinstance(entry, dict) else None
        if isinstance(when, str):
            sites.append(_site(TASK, f"copier.yml _tasks[{index}]", _inner(when)))
    return sites


def collect_sites() -> list[Site]:
    """Every boolean condition site on the render + question surface, in a stable order."""
    records, settings = _questionnaire_records()
    sites = [
        _site(QUESTION, f"{question.source}:{question.name}", _inner(question.when))
        for question in records.values()
        if isinstance(question.when, str)
    ]
    resolved, _order = when_model.load_questions()
    internals = bool_internals(resolved)
    sites += [
        _site(INTERNAL, f"{records[name].source if name in records else 'copier.yml'}:{name}", definition)
        for name, definition in internals.items()
    ]
    sites += _filename_sites()
    sites += _body_sites()
    sites += _task_sites(settings)
    return sites


def leaf_contexts(leaves: list[Any]) -> Any:
    """Yield (leaf, rendered context, jinja env) once per leaf, copier running the pass.

    The oracle every consumer of "what does this answer set actually resolve
    to" shares (tools/answers_for.py runs it over the whole leaf space the
    same way ``evaluate`` does). `Worker._ask` is copier's own questionnaire
    pass (it resolves the internal `when: false` variables in definition
    order) and `_render_context` is the context every render sees; both are
    private because copier exposes no other way to run that pass -- the
    tests/test_when_model.py oracle pattern, `vcs_ref="HEAD"` so the
    checkout's own questionnaire is what renders.
    """
    with tempfile.TemporaryDirectory() as dst:
        worker = Worker(src_path=str(TOP), dst_path=Path(dst), defaults=True, quiet=True, vcs_ref="HEAD")
        for leaf in sorted(leaves, key=lambda leaf: leaf.id):
            worker.data = dict(leaf.answers)
            worker._ask()  # pyright: ignore[reportPrivateUsage]  WHYNOT: the oracle is copier's own pass (tests/test_when_model.py precedent).
            yield leaf, worker._render_context(), worker.jinja_env  # pyright: ignore[reportPrivateUsage]  WHYNOT: same.


def _scalar_reads(refs: frozenset[str], context: Any) -> str | None:
    """Why a condition cannot be rendered against this context, or None if it can.

    A condition reading a list/dict (`adopt_protect`) is classed unevaluable
    rather than silently truthed (a list is truthy however empty its
    contents): the vector would look like a classification while proving
    nothing. A name the pass never produced stays renderable -- that is
    copier's own `get_when` semantics (an undefined name renders falsy), and
    the questionnaire's reference check owns typos.
    """
    for name in sorted(refs):
        if name in context and isinstance(context[name], (list, dict)):
            return f"non-scalar read: {name}"
    return None


def _distinct_evaluations(sites: list[Site]) -> dict[str, tuple[frozenset[str], list[bool | None], str | None]]:
    """One evaluation slot per distinct evaluated expression (identical guards share their vector)."""
    distinct: dict[str, tuple[frozenset[str], list[bool | None], str | None]] = {}
    for site in sites:
        if site.eval_expr not in distinct:
            distinct[site.eval_expr] = (_refs(site.eval_expr), [], None)
    return distinct


def _evaluate_expression(
    expr: str,
    refs: frozenset[str],
    context: Any,
    env: Any,
    compiled: dict[str, Any],
) -> tuple[bool | None, str | None]:
    """(bool, None) when the expression verdicts against this context, (None, why) when it cannot.

    Rendering wraps the expression back in `{{ }}` because that is what
    copier evaluates: a `when` value is stored and compiled with its
    delimiters, and a tag-less source would render to its own literal text.
    """
    reason = _scalar_reads(refs, context)
    if reason is not None:
        return None, reason
    try:
        if expr not in compiled:
            compiled[expr] = env.from_string("{{ " + expr + " }}")
        return cast_to_bool(compiled[expr].render(context)), None
    except Exception as error:  # noqa: BLE001  CONTEXT: any Jinja failure classes the site, it never kills the sweep.
        return None, f"{type(error).__name__}: {error}"


def evaluate(sites: list[Site], leaves: list[Any]) -> None:
    """Fill in each site's per-leaf vector (or its unevaluable reason), in place.

    Copier's pass runs once per leaf; identical expressions are rendered once
    per leaf and shared. Truthiness is `cast_to_bool` of the rendered value --
    exactly what `Question.get_when` does internally -- so `== 'x'` rendering
    to the *string* "True"/"False" verdicts the same way copier's own
    conditions do.
    """
    distinct = _distinct_evaluations(sites)
    compiled: dict[str, Any] = {}  # compiled sources are pure per env (tests/test_when_model.py memoizes the same way)
    for _leaf, context, env in leaf_contexts(leaves):
        for expr, (refs, values, _error) in distinct.items():
            value, reason = _evaluate_expression(expr, refs, context, env, compiled)
            values.append(value)
            if reason is not None and distinct[expr][2] is None:
                distinct[expr] = (refs, values, reason)
    for site in sites:
        _refs_unused, values, error = distinct[site.eval_expr]
        if error is not None or any(value is None for value in values):
            site.error = error or "rendered undefined on some leaf"
            site.vector = None
        else:
            site.vector = [bool(value) for value in values]


def _fires(vector: list[bool]) -> int:
    """How many leaves the condition holds on."""
    return sum(vector)


class FreeSpace:
    """The Z3 oracle: can two condition texts ever disagree, over the whole questionnaire space?

    Boolean internals are substituted by their definitions (recursively,
    cycle-guarded), so the comparison is over questions alone; the free space
    is `when_model.str_domains` (domain-backed str questions become Ints over
    their choices, every bool is free). This is the machinery
    tests/test_predicate_classifier.py sweeps: a site and a named internal
    that *cannot* disagree are unconditionally equivalent, whatever the 225
    witnesses happen to sample.
    """

    EQUIVALENT = "equivalent"
    DISTINCT = "distinct"
    UNMODELABLE = "unmodelable"

    def __init__(self, questions: dict[str, dict]) -> None:
        self.domains = when_model.str_domains(questions)
        self.questions = questions
        self.bool_defs = bool_internals(questions)
        self.str_internals = {
            name
            for name, details in questions.items()
            if details.get("when") is False and details.get("type") != "bool"
        }
        self._substituted: dict[str, str | None] = {}
        self._identifier_sets: dict[str, frozenset[str]] = {}
        self._verdicts: dict[tuple[str, str], str] = {}
        self._probe_values: dict[str, dict[int, bool | None]] = defaultdict(dict)
        self._probe_templates: dict[str, Any] = {}
        # autoescape off on purpose: probes render boolean predicates, and escaping would
        # corrupt the quotes inside them (this is not HTML).
        self._probe_env = jinja2.Environment(autoescape=False)  # noqa: S701  CONTEXT: probes only refute, Z3 decides.
        self._probes = self._build_probes()

    def _build_probes(self) -> list[dict[str, Any]]:
        """Concrete assignments that try to make two texts disagree.

        Every question gets a defined scalar in every probe (a domain value
        where the question has one, a well-mixed deterministic boolean
        elsewhere), so a probe can never differ merely because a name is
        missing, and the polarity patterns are scattershot on purpose: two
        predicates that differ anywhere almost surely differ on one of them,
        which is what lets their pair skip Z3. Probes only refute: a pair
        that agrees on all of them still goes to Z3 for the real proof.
        """
        names = sorted(set(self.questions) | set(self.domains))
        domain_default = {name: self.domains[name][0] for name in names if name in self.domains}
        # static choices of every other str question: rotating through them
        # makes `layout == 'src'`-style comparisons vary across probes instead
        # of freezing at one value (a str question the question-`when`s never
        # reference is outside str_domains, but its comparisons still render).
        choices = {
            name: when_model.static_str_choices(self.questions[name])
            for name in names
            if name in self.questions and name not in self.domains
        }

        def booleans(pattern: int) -> dict[str, Any]:
            values: dict[str, Any] = {}
            for name in names:
                if name in domain_default:
                    values[name] = domain_default[name]
                elif choices.get(name):
                    values[name] = choices[name][pattern % len(choices[name])]
                else:
                    values[name] = crc32(f"{pattern}:{name}".encode()) % 2 == 1
            return values

        probes = [booleans(pattern) for pattern in range(24)]
        probes += [
            {**booleans(0), domain: value} for domain in sorted(domain_default) for value in self.domains[domain]
        ]
        return probes

    def _probe_at(self, text: str, index: int) -> bool | None:
        """The text's verdict on one probe (rendered on first use), or None if it will not render.

        A text that fails a probe is marked inconclusive from there on: its
        pairs fall through to Z3, which either proves equivalence or raises
        into UNMODELABLE -- a probe error must never be read as a difference.
        """
        cached = self._probe_values[text]
        if index not in cached:
            if index > 0 and cached.get(index - 1) is None:
                cached[index] = None
            else:
                try:
                    # wrap in delimiters: a bare expression is literal text to Jinja
                    if text not in self._probe_templates:
                        self._probe_templates[text] = self._probe_env.from_string("{{ " + text + " }}")
                    cached[index] = cast_to_bool(self._probe_templates[text].render(self._probes[index]))
                except Exception:  # noqa: BLE001  CONTEXT: any render failure is "inconclusive" (the pair falls through to Z3), never a difference.
                    cached[index] = None
        return cached[index]

    def substituted(self, text: str, _stack: tuple[str, ...] = ()) -> str | None:
        """`text` with boolean internals inlined by their definitions, or None if it reads one it cannot.

        None means unevaluable for the oracle: a cycle, or a reference to a
        string-valued internal (the when grammar has no str variables -- a
        bare `pkg_dir` would silently become a free boolean, a wrong model).
        """
        if not _stack and text in self._substituted:
            return self._substituted[text]
        result = self._substitute(text, _stack)
        if not _stack:
            self._substituted[text] = result
        return result

    def _substitute(self, text: str, stack: tuple[str, ...]) -> str | None:
        """The recursive worker (``substituted`` owns the memo)."""
        parts = re.split(r"('[^']*'|\"[^\"]*\")", text)
        out: list[str] = []
        for index, part in enumerate(parts):
            if index % 2:  # a quoted string literal: never substituted
                out.append(part)
                continue
            replaced = self._replace_identifiers(part, stack)
            if replaced is None:
                return None
            out.append(replaced)
        return "".join(out)

    def _replace_identifiers(self, part: str, stack: tuple[str, ...]) -> str | None:
        """One outside-the-quotes segment, its internal identifiers inlined (attribute/kwargs spared)."""
        identifier = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
        out: list[str] = []
        last = 0
        for match in identifier.finditer(part):
            name = match.group(0)
            if match.start() > 0 and part[match.start() - 1] == ".":
                replacement: str | None = name  # attribute access: `x.name` reads the attribute
            elif part[match.end() :].startswith("=") and not part[match.end() :].startswith("=="):
                replacement = name  # keyword argument: `filter(name=...)` names a parameter
            elif name in self.str_internals:
                replacement = None  # a str internal in a boolean condition: outside the grammar
            elif name not in self.bool_defs:
                replacement = name  # a question reference: stays for the encoder
            elif name in stack:
                replacement = None  # a definitional cycle: not a well-formed predicate
            else:
                expanded = self.substituted(self.bool_defs[name], (*stack, name))
                replacement = None if expanded is None else f"({expanded})"
            if replacement is None:
                return None
            out.append(part[last : match.start()])
            out.append(replacement)
            last = match.end()
        out.append(part[last:])
        return "".join(out)

    def verdict(self, site_expr: str, internal: str, z3: Any) -> str:
        """`equivalent` / `distinct` / `unmodelable` for one (condition text, named internal) pair.

        Equivalence is decided by the shared encoder on the two one-direction
        witnesses ``(S and not D)`` / ``(D and not S)``: both unsatisfiable
        means the two can never disagree. Three cheap filters run first, all
        sound (they only ever answer "distinct" or shortcut the trivial
        case): identical substituted texts, the identifiers-after-substitution
        intersection (a function that ignores a variable it never reads
        cannot equal one that must move with it), and the probe renders
        (``_build_probes``).
        """
        key = (site_expr, internal)
        if key not in self._verdicts:
            self._verdicts[key] = self._verdict_uncached(site_expr, internal, z3)
        return self._verdicts[key]

    def _probes_disagree(self, site: str, definition: str) -> bool:
        """Whether any concrete probe already catches the two texts disagreeing.

        A text whose probe render fails is inconclusive: this returns False
        and lets Z3 decide rather than misreading an error as a difference.
        """
        for index in range(len(self._probes)):
            site_value = self._probe_at(site, index)
            definition_value = self._probe_at(definition, index)
            if site_value is None or definition_value is None:
                return False
            if site_value != definition_value:
                return True
        return False

    def _encoder_verdict(self, site: str, definition: str, z3: Any) -> str:
        """The Z3 proof: two witnesses, one per direction (S and not D) / (D and not S).

        Each text appears in one witness only, because the encoder names an
        unmodeled comparison's fallback boolean by parser position -- a text
        repeated inside one XOR would meet its own copy as a *different*
        free boolean and read "distinct" for identical predicates. Both
        witnesses unsatisfiable means the texts can never disagree.
        """
        try:
            for witness in (f"(({site}) and not ({definition}))", f"(({definition}) and not ({site}))"):
                if when_model.when_expr_satisfiable(witness, self.domains, z3):
                    return self.DISTINCT
        except (AssertionError, ValueError):
            return self.UNMODELABLE  # outside the when grammar: filters, unmodeled membership, ...
        return self.EQUIVALENT

    def _identifiers(self, text: str) -> frozenset[str]:
        """``_refs`` memoized per substituted text (the sweep compares the same texts thousands of times)."""
        if text not in self._identifier_sets:
            self._identifier_sets[text] = _refs(text)
        return self._identifier_sets[text]

    def _verdict_uncached(self, site_expr: str, internal: str, z3: Any) -> str:
        site = self.substituted(site_expr)
        definition = self.substituted(self.bool_defs[internal])
        if site is None or definition is None:
            return self.UNMODELABLE
        if site == definition:
            return self.EQUIVALENT
        if not self._identifiers(site) & self._identifiers(definition):
            return self.DISTINCT  # disjoint reads (see `verdict`): cannot be the same predicate
        if self._probes_disagree(site, definition):
            return self.DISTINCT
        return self._encoder_verdict(site, definition, z3)


def _classification_tree(leaves: list[Any]) -> list[tuple[invariants.LeafClass, int, list[str]]]:
    """Every invariants.yml row with its leaf count and a summary of the leaves it selects."""
    matrix = invariants.load()
    rows: list[tuple[invariants.LeafClass, int, list[str]]] = []
    for row in matrix.rows:
        selected = [leaf.id for leaf in leaves if row.matches(matrix.facts(leaf.answers))]
        rows.append((row, len(selected), selected))
    return rows


def _internal_sites(sites: list[Site]) -> dict[str, Site]:
    """The boolean internals' definition sites, by name."""
    return {site.location.rsplit(":", 1)[-1]: site for site in sites if site.kind == INTERNAL}


def _named_vectors(sites: list[Site], internals: dict[str, str]) -> dict[str, tuple[bool, ...]]:
    """Name -> the internal's per-leaf vector, taken from its own definition site."""
    internal_sites = _internal_sites(sites)
    named: dict[str, tuple[bool, ...]] = {}
    for name in internals:
        site = internal_sites.get(name)
        if site is not None and site.vector is not None:
            named[name] = tuple(site.vector)
    return named


def _classes(sites: list[Site], named: dict[str, tuple[bool, ...]]) -> list[dict[str, Any]]:
    """Sites grouped by identical leaf vector, biggest fire count first.

    A class carries its size, its fire count, and (for the report's "is this
    class already named?" column) the internal whose vector it equals, if any.
    Unevaluable sites are not classes: they have no vector to group by.
    """
    grouped: dict[tuple[bool, ...], list[Site]] = defaultdict(list)
    for site in sites:
        if site.vector is not None:
            grouped[tuple(site.vector)].append(site)
    owners: dict[tuple[bool, ...], list[str]] = defaultdict(list)
    for name, vector in sorted(named.items()):
        owners[vector].append(name)
    classes: list[dict[str, Any]] = []
    for vector, members in grouped.items():
        classes.append(
            {
                "vector": vector,
                "fires": _fires(list(vector)),
                "named_internal": " ".join(owners.get(vector, [])) or None,
                "sites": members,
            }
        )
    return sorted(classes, key=lambda entry: (-entry["fires"], -len(entry["sites"]), entry["sites"][0].location))


def _unification_candidates(sites: list[Site], named: dict[str, tuple[bool, ...]], total: int) -> list[dict[str, Any]]:
    """Sites whose vector equals a named internal's while the site never references it.

    Mechanical equality is not intent -- this is the *candidate* list (the §18
    "use the shortcut" list), not an instruction; the guard test holds the
    stronger, space-wide version of the same question. Two restrictions keep
    the list about renaming and not about dead conditions: the site must
    actually split the space (a never-firing site "matches" every never-firing
    internal, an always-firing one every constant -- that coincidence is the
    flattening report's business, not a rename suggestion), and definition
    sites are excluded (an internal aliasing another internal is deliberate;
    only consumers -- question/filename/body/task -- can "use the shortcut").
    Sites are grouped, because several internals legitimately coincide on the
    leaf space (the effective layers and their raw gates, for one): the
    finding is the site's to judge, the internal list is ranked evidence.
    """
    matched: dict[str, dict[str, Any]] = {}
    for site in sites:
        if site.vector is None or site.kind in (INTERNAL, QUESTION):
            continue
        fires = _fires(site.vector)
        if not 0 < fires < total:
            continue
        names = sorted(name for name, vector in named.items() if name not in site.refs and tuple(site.vector) == vector)
        if names:
            matched[site.location] = {"site": site.location, "kind": site.kind, "expr": site.expr, "internals": names}
    return sorted(matched.values(), key=lambda entry: (-len(entry["internals"]), entry["site"]))


def _shortcut_suggestions(sites: list[Site], classes: list[dict[str, Any]], leaves: list[Any]) -> dict[str, list[Any]]:
    """The naming and flattening candidates (thresholds are module constants, with reasons)."""
    total = len(leaves)
    naming = [
        {
            "fires": entry["fires"],
            "sites": [site.location for site in entry["sites"]],
            "expr": entry["sites"][0].expr,
        }
        for entry in classes
        if entry["named_internal"] is None and 0 < entry["fires"] < total and len(entry["sites"]) >= SHORTCUT_MIN_SITES
    ]
    referenced: dict[str, int] = defaultdict(int)
    for site in sites:
        for name in site.refs:
            referenced[name] += 1
    internal_sites = _internal_sites(sites)
    flattening = [
        {"internal": name, "fires": _fires(site.vector), "referencing_sites": referenced[name]}
        for name, site in sorted(internal_sites.items())
        if site.vector is not None and not 0 < _fires(site.vector) < total
    ]
    return {"naming": naming, "flattening": flattening}


def _unevaluable(sites: list[Site]) -> list[dict[str, str]]:
    """Every site that could not be classed, with the first reason it gave."""
    return [
        {"location": site.location, "kind": site.kind, "reason": site.error or "unevaluable"}
        for site in sites
        if site.error is not None
    ]


def _tree_lines(tree: list[tuple[invariants.LeafClass, int, list[str]]]) -> list[str]:
    """The classification tree: every row top-down with its leaf count and a leaves summary."""
    lines = [f"classification tree -- {len(tree)} rows over the leaf space (tests/matrix/invariants.yml)"]
    for row, count, _leaf_ids in tree:
        summary = ", ".join(f"{path}={value}" for path, value in row.select.items())
        lines.append(f"  {row.id:<46} {count:>4} leaves  [{summary}]")
    return lines


def _internal_lines(sites: list[Site], internals: dict[str, str], total: int) -> list[str]:
    """Per named internal: its definition, how many sites reference it, how many leaves it fires on."""
    referenced: dict[str, int] = defaultdict(int)
    for site in sites:
        for name in site.refs:
            referenced[name] += 1
    internal_sites = _internal_sites(sites)
    lines = [f"named boolean internals ({len(internals)}) -- definition, referencing sites, fire count over {total}"]
    for name, definition in internals.items():
        site = internal_sites.get(name)
        fires = f"{_fires(site.vector)}/{total}" if site is not None and site.vector is not None else "unevaluable"
        lines.append(f"  {name:<34} fires {fires:>7}  referenced at {referenced[name]:>3} sites  = {definition}")
    return lines


def _class_lines(classes: list[dict[str, Any]], total: int) -> list[str]:
    """The equivalence classes: size, fire count, and whether the class is a named internal."""
    evaluable = sum(len(entry["sites"]) for entry in classes)
    lines = [
        (
            f"equivalence classes over the leaf space -- sites with identical vectors "
            f"({len(classes)} classes, {evaluable} evaluable sites)"
        )
    ]
    for index, entry in enumerate(classes, start=1):
        owner = f"= named internal `{entry['named_internal']}`" if entry["named_internal"] else "unnamed"
        lines.append(f"  class {index:<4} fires {entry['fires']:>4}/{total}  {len(entry['sites']):>3} sites  {owner}")
        lines += [f"        {site.kind:<9} {site.location:<72} {{% if {site.expr} %}}" for site in entry["sites"][:12]]
        if len(entry["sites"]) > 12:
            lines.append(f"        ... and {len(entry['sites']) - 12} more sites with this vector")
    return lines


def _candidate_lines(candidates: list[dict[str, Any]]) -> list[str]:
    """The unification candidates: site vector == a named internal the site does not reference."""
    lines = [
        (
            f"unification candidates ({len(candidates)}) -- a site whose vector equals a named internal it does "
            "not reference (mechanical equality is not intent: judge each one before renaming)"
        )
    ]
    for candidate in candidates:
        names = ", ".join(f"`{name}`" for name in candidate["internals"])
        lines.append(f"  {candidate['kind']:<9} {candidate['site']:<70} == {names}")
        lines.append(f"            {{% if {candidate['expr']} %}}")
    return lines


def _shortcut_lines(suggestions: dict[str, list[Any]], total: int) -> list[str]:
    """The shortcut suggestions: naming candidates and flattening candidates."""
    naming, flattening = suggestions["naming"], suggestions["flattening"]
    lines = [
        (
            f"shortcut suggestions -- naming candidates: an unnamed class splitting the space at "
            f">= {SHORTCUT_MIN_SITES} sites ({len(naming)}); flattening candidates: a named internal that "
            f"never splits ({len(flattening)})"
        )
    ]
    lines += [
        (
            f"  name this: fires {candidate['fires']:>4}/{total} at {len(candidate['sites'])} sites, "
            f"e.g. {{% if {candidate['expr']} %}} (first: {candidate['sites'][0]})"
        )
        for candidate in naming
    ]
    lines += [
        (
            f"  flatten?  `{candidate['internal']}` fires on {candidate['fires']}/{total} leaves "
            f"({candidate['referencing_sites']} sites reference it) -- a shortcut that never splits is dead weight"
        )
        for candidate in flattening
    ]
    return lines


def report(
    sites: list[Site],
    leaves: list[Any],
    tree: list[tuple[invariants.LeafClass, int, list[str]]],
    internals: dict[str, str],
) -> str:
    """The human-readable report."""
    total = len(leaves)
    kinds = defaultdict(int)
    for site in sites:
        kinds[site.kind] += 1
    buckets = ", ".join(f"{kind}={kinds[kind]}" for kind in (QUESTION, INTERNAL, FILENAME, BODY, TASK))
    named = _named_vectors(sites, internals)
    classes = _classes(sites, named)
    candidates = _unification_candidates(sites, named, total)
    lines = [
        (
            f"predicate classifier: {len(sites)} condition sites over {total} witness leaves ({buckets}; "
            f"{len(_unevaluable(sites))} unevaluable)"
        ),
        "",
        *_tree_lines(tree),
        "",
        *_internal_lines(sites, internals, total),
        "",
        *_class_lines(classes, total),
        "",
        *_candidate_lines(candidates),
        "",
        *_shortcut_lines(_shortcut_suggestions(sites, classes, leaves), total),
    ]
    unevaluable = _unevaluable(sites)
    if unevaluable:
        lines += ["", f"unevaluable sites ({len(unevaluable)}) -- reported, never crash the report:"]
        lines += [f"  {entry['kind']:<9} {entry['location']:<72} {entry['reason']}" for entry in unevaluable]
    return "\n".join(lines)


def json_report(
    sites: list[Site],
    leaves: list[Any],
    tree: list[tuple[invariants.LeafClass, int, list[str]]],
    internals: dict[str, str],
) -> dict[str, Any]:
    """The machine-readable report (`--json`)."""
    named = _named_vectors(sites, internals)
    classes = _classes(sites, named)
    return {
        "leaves": len(leaves),
        "internals": internals,
        "sites": [
            {
                "kind": site.kind,
                "location": site.location,
                "expr": site.expr,
                "eval_expr": site.eval_expr,
                "refs": sorted(site.refs),
                "vector": site.vector,
                "error": site.error,
            }
            for site in sites
        ],
        "tree": [
            {"id": row.id, "leaves": count, "select": row.select, "sample_leaf_ids": selected[:3]}
            for row, count, selected in tree
        ],
        "classes": [
            {
                "fires": entry["fires"],
                "named_internal": entry["named_internal"],
                "sites": [site.location for site in entry["sites"]],
            }
            for entry in classes
        ],
        "unification_candidates": _unification_candidates(sites, named, len(leaves)),
        "shortcuts": _shortcut_suggestions(sites, classes, leaves),
        "unevaluable": _unevaluable(sites),
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point: collect, evaluate, report (stderr prose; `--json` puts the machine report on stdout)."""
    parser = argparse.ArgumentParser(description="Classify every condition site over the witness leaf space.")
    parser.add_argument("--json", action="store_true", help="print the machine-readable report to stdout")
    args = parser.parse_args(argv)
    sites = collect_sites()
    _leaf_space, leaves = z3_witnesses.build()
    evaluate(sites, leaves)
    tree = _classification_tree(leaves)
    _resolved, _order = when_model.load_questions()
    internals = bool_internals(_resolved)
    if args.json:
        print(json.dumps(json_report(sites, leaves, tree, internals), indent=2))
    else:
        print(report(sites, leaves, tree, internals), file=sys.stderr)
    print(
        f"predicates: {len(sites)} sites, {len(_unevaluable(sites))} unevaluable, {len(leaves)} leaves", file=sys.stderr
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
