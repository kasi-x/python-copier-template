"""Rot-guard: every unconditionally-equivalent (site, internal) pair is accounted for.

tools/predicates.py collects every boolean condition site on the render +
question surface; the named boolean internals (`oj_bare`, `no_pkg`, the
`*_effective` family) are its shortcuts. TODO.md §18's unification was done
by hand against an inventory that could rot: a template condition quietly
re-spelling `oj_bare` without referencing it is exactly the drift the §18
guard tests pinned for the eight known sites, generalized to every site.

This test is the space-wide version. A render-side site S and a named
boolean internal I with definition D are *unconditionally* equivalent when
they cannot disagree anywhere in the questionnaire's free space -- checked
with tools/when_model.py's Z3 encoder on
`(S and not D) or (not S and D)` (unsatisfiable = equivalent), after
`FreeSpace` substitutes every boolean internal by its definition
recursively (cycle-guarded; string-valued internals have no variable in the
when grammar, so a site reading one is skipped as unmodelable rather than
silently modeled as a free boolean). The 272-leaf sweep the tool itself
runs samples the space; this proves over all of it, without running copier
once -- that is what keeps it in the fast tier.

Every pair the sweep proves equivalent must be one of:
  (a) the site actually references that internal (the shortcut in use);
  (b) the site IS that internal's own definition site;
  (c) declared in `DECLARED_EQUIVALENCES` below with a one-line reason --
      location -> internal -> reason, the same declared-not-discovered idiom
      as invariants.yml's `excluded` and test_answer_fixtures.py's
      `DEFAULT_REPEATS_ALLOWED`. The sweep starts from the empty registry:
      whatever it proves beyond (a)/(b) must be either renamed away or
      deliberately declared here, and a declared pair that stops being
      equivalent fails as stale -- the same lie in the other direction.

What this does not cover (a narrower claim beats an overstated one)
- The Z3 model's blind spots are conservative here: a filter, an
  unmodeled membership test or a str-typed reference makes the pair
  UNMODELABLE (skipped, counted), never equivalent -- the encoder only
  proves equivalence inside the grammar it actually models.
- Question `when:`s are out of scope: they are ask-time surface — an
  equivalence there is a vocabulary question, and the include-order rule
  (test_question_references_are_forward_only,
  docs/explanations/template-dev.md) governs them, not this sweep; the
  tool's report still shows their vectors.
- Leaf-space coincidences (`web_api` == `cors_effective` on every leaf
  because the recommended gate stays on) are the tool report's findings,
  not this test's: they are not unconditional, and Z3 separates them.
"""

import sys
from pathlib import Path

# z3-solver is a declared dev dependency (pyproject.toml): a missing z3 is a
# broken environment, not an unsupported platform, so this imports it loudly
# instead of skipping (the repo's rule since TODO §19).
import z3

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_when_model.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools import predicates  # noqa: E402
from tools import when_model  # noqa: E402

# The declared exceptions to (a)/(b): location -> internal -> the reason the
# equivalence is intentional. Declared, not discovered -- like invariants.yml's
# `excluded`, the test refuses an undeclared equivalence AND a stale entry.
# Today's three are one family: the `has_*` guards in questions/_combo.yml are
# the spelled-out predicate, and `web_api` / `data_science` /
# `data_science_layout` are its named aliases (questions/_internal.yml:
# "the effective booleans: the matching base project_type, or the
# corresponding combo opt-in"). §18 item 4 audited exactly this trio and kept
# it as three deliberate layers -- so a definition site may not reference its
# own alias by name; the alias IS the definition.
DECLARED_EQUIVALENCES: dict[str, dict[str, str]] = {
    "_combo.yml:has_web_api": {
        "web_api": "alias by definition: `web_api` = has_web_api is the render vocabulary's name for this"
        " exact predicate (questions/_internal.yml), so the definition site is equivalent to the alias it"
        " does not name -- the §18-recorded effective-layer idiom",
    },
    "_combo.yml:has_data_science": {
        "data_science": "same alias idiom: `data_science` = has_data_science by declaration (questions/_internal.yml)",
        "data_science_layout": "the chain's far end: data_science_layout = data_science = has_data_science,"
        " one predicate with three readers' names (questions/_internal.yml)",
    },
}

# Sanity floor for the sweep below: the collector must keep finding the real
# surface (hundreds of sites), not shrink to a token list after a refactor.
MIN_SITES = 100


def test_every_unconditional_site_internal_equivalence_is_accounted_for():
    """Z3: no render-side site duplicates a named internal without referencing (or declaring) it."""
    questions, _order = when_model.load_questions()
    free = predicates.FreeSpace(questions)
    sites = predicates.collect_sites()
    internals = free.bool_defs

    checked = 0
    unmodelable = 0
    alias_covered = 0
    equivalent: set[tuple[str, str]] = set()
    violations: list[str] = []
    for site in sites:
        if site.kind == predicates.QUESTION:
            continue  # question `when`s are ask-time surface; see the docstring
        for name, definition in internals.items():
            if site.kind == predicates.INTERNAL and site.location.endswith(f":{name}"):
                continue  # (b): the internal's own definition site
            if name in site.refs:
                continue  # (a): the shortcut is in use
            verdict = free.verdict(site.expr, name, z3)
            if verdict == predicates.FreeSpace.UNMODELABLE:
                unmodelable += 1
                continue
            checked += 1
            if verdict != predicates.FreeSpace.EQUIVALENT:
                continue
            equivalent.add((site.location, name))
            # (a') the site names ANOTHER internal for the same predicate -- the
            # alias family (`data_science` / `data_science_layout`, both defined
            # in questions/_internal.yml as one predicate with two readers'
            # names) is the vocabulary in use, not a re-spelling. This is a
            # refinement of (a), not a registry row: the site literally
            # references an internal it is equivalent to.
            if any(
                ref in internals and free.verdict(site.expr, ref, z3) == predicates.FreeSpace.EQUIVALENT
                for ref in site.refs
            ):
                alias_covered += 1
                continue
            if name not in DECLARED_EQUIVALENCES.get(site.location, {}):
                violations.append(
                    f"{site.kind} {site.location}: {{% if {site.expr} %}} is unconditionally equivalent to"
                    f" `{name}` (= {definition}). Reference the internal instead of re-spelling it, or"
                    " declare the pair in DECLARED_EQUIVALENCES with the reason it is intentional"
                )
    declared_pairs = {(location, name) for location, names in DECLARED_EQUIVALENCES.items() for name in names}
    stale = sorted(f"{location} -> {name}" for location, name in declared_pairs - equivalent)
    assert not stale, f"DECLARED_EQUIVALENCES entries no longer equivalent (stale, remove them): {stale}"
    assert not violations, (
        f"{len(violations)} site(s) duplicate a named internal unconditionally, unregistered:\n  "
        + "\n  ".join(violations[:10])
    )
    assert checked > 50, (
        f"the sweep only proved {checked} (site, internal) relationships"
        f" ({unmodelable} unmodelable, {alias_covered} alias-covered): is the collector broken?"
    )


def test_collector_finds_the_whole_surface_including_every_named_internal():
    """The classifier's raw material: hundreds of sites, and every boolean internal among them."""
    sites = predicates.collect_sites()
    _questions, _order = when_model.load_questions()
    internals = predicates.bool_internals(_questions)
    found = {site.location.rsplit(":", 1)[-1] for site in sites if site.kind == predicates.INTERNAL}
    missing = sorted(set(internals) - found)
    assert len(sites) >= MIN_SITES, (
        f"the collector found only {len(sites)} condition sites (< {MIN_SITES}): template/, _shared/,"
        " _tasks.jinja, copier.yml's _tasks and the questionnaire must all be scanned"
    )
    assert not missing, f"boolean internal(s) {missing} missing from the collected sites: definitions are sites too"
