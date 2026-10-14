# The language-independent contract of "constitutive trust"

This page evaluates what part of this template's "reliable scaffolding" is
Python-specific and what part is a language-independent contract, and how a
small standalone prototype could test that contract before any second-language
template is proposed. It is an evaluation, not a commitment to
build another template.

## The three mechanisms

architekton-py's trust claims rest on three mechanisms. Each decomposes into a
Python-coupled implementation and a contract that names no Python:

### 1. Configuration-space verification (Z3)

- <lt-m v="**"/>Contract<lt-m v="**"/>: a questionnaire is a set of <lt-m v="*"/>questions<lt-m v="*"/> (typed domains:
  select/multi/bool/string), each with a `when:` guard over earlier answers.
  The product of reachable answer vectors is finite. Verification means:
  enumerate the reachable leaves, prove every leaf renders, and prove every
  rendered leaf is reachable.
- <lt-m v="**"/>Python coupling<lt-m v="**"/>: the questionnaire is copier's YAML+Jinja format; the
  encoder (`architekton/when_model.py`, `architekton/z3_witnesses.py`) parses Jinja
  expressions and copier's merge semantics.
- <lt-m v="**"/>Reusable minimum<lt-m v="**"/>: the <lt-m v="*"/>predicate algebra<lt-m v="*"/> — `and`/`or`/`not`,
  `==`/`!=`/`in` over a flat answer dictionary — plus the leaf-enumeration
  invariant. Any system that can express "question Q is asked iff predicate P
  holds" can carry this.

### 2. Registry-to-distribution policy (ethics sections)

- <lt-m v="**"/>Contract<lt-m v="**"/>: a versioned registry maps <lt-m v="*"/>rules<lt-m v="*"/> to <lt-m v="*"/>audiences<lt-m v="*"/>; a generator
  distributes exactly the rules whose gate predicate holds for the concrete
  artifact. Drafts are isolated: referenceable by id, never inlined.
- <lt-m v="**"/>Python coupling<lt-m v="**"/>: `REGISTRY.yml` gates evaluate over copier internal
  variables; the appendix is a Jinja include inside `AGENTS.md.jinja`.
- <lt-m v="**"/>Reusable minimum<lt-m v="**"/>: `{id, version, status, gate, body}` rows and a
  restricted predicate evaluator over leaf context. The leaf context is the
  same algebra as mechanism 1.

### 3. Post-generation drift detection

- <lt-m v="**"/>Contract<lt-m v="**"/>: the artifact records <lt-m v="*"/>what was chosen<lt-m v="*"/> (answers), <lt-m v="*"/>by what<lt-m v="*"/>
  (template ref), and <lt-m v="*"/>under which rule versions<lt-m v="*"/> (registry snapshot). A
  later check compares recorded vs. current to answer "what changed and
  why".
- <lt-m v="**"/>Python coupling<lt-m v="**"/>: `.copier-answers.yml`, the contract manifest, and the
  rehearsal harness are copier- and pytest-shaped.
- <lt-m v="**"/>Reusable minimum<lt-m v="**"/>: three recorded facts — answers pointer, template ref,
  rule-version list — plus a diff verb. No runtime needed.

## The shared kernel

All three mechanisms reduce to the same kernel:

```text
Leaf algebra:  flat key→value answers; predicates in {and,or,not,eq,neq,in}
Enumeration:   finite reachable-leaf set; reachability ⇔ renderability
Distribution:  versioned rows gated by predicates; drafts isolated
Audit trail:   (answers*, ref, rule-versions) recorded at generation time
               (*sensitive values withheld by declaration)
```

A second-language template needs each mechanism only insofar as it has the
same four-shaped problem: many conditional questions, gated policy text, and
drift after generation. Rust/Go/Node scaffolders (cargo-generate, cookiecutter
variants) share the shape; the Jinja/copier surface does not transfer, but
the kernel — ~600 lines of predicate parsing, Z3 wiring, and restricted eval
— does.

## Prototype proposal (small, standalone)

Before any second-language template: build a tiny standalone checker that
consumes a <lt-m v="*"/>language-neutral questionnaire description<lt-m v="*"/>:

- Input A: `questionnaire.yml` — questions with `domain`, `when` in the
  restricted predicate grammar (no Jinja surface).
- Input B: `sections.yml` — registry rows `{id, version, status, gate}`.
- Output: reachable-leaf count, per-leaf distributed rule ids, and an
  `audit.json` per leaf (answers pointer, ref, rule versions).

Success conditions (all must hold to justify pursuing a language port):

1. The checker reproduces a <lt-m v="*"/>hand-computed<lt-m v="*"/> leaf enumeration for a
   questionnaire of ≥3 orthogonal dimensions (e.g. 2×3×4 = 24 leaves) with
   zero divergence, including a deliberately unreachable leaf it must prove
   unsatisfiable.
2. The audit trail answers "what changed" for a simulated rule-version bump
   without re-rendering anything.
3. Total ownership cost is legible: the whole tool ≤ ~800 lines, one
   dependency class (an SMT solver or a BDD/SAT library), no Jinja.

If (3) fails — if the predicate grammar cannot be kept this small — that is
the signal that the contract is more coupled to Jinja than this evaluation
claims, and the port should not proceed.

## What this does NOT propose

- No new supported language or project type in this template. Evaluation
  first, and expanding Python's supported surface is out of scope.
- No shared runtime. The reusable artifact is a *specification + a
  reference checker*, not a library the Python template would import — the
  existing `architekton/` stack stays the Python implementation of record.
- No commitment. If the prototype shows the maintenance owner and cost are
  not clearly better than status quo, this page stands as the record of why
  the port was declined.
