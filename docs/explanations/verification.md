# Verification Architecture

Which layer of this repository's verification proves what, what each layer
costs, and the rules a new check has to satisfy before it lands.

This page is the written contract behind three things that already exist:
the tier selectors in `Taskfile.yml` / `pyproject.toml`, the witness tiers in
`tests/test_witness_matrix.py`, and the support levels in
[`support.yml`](../reference/support.md). Every number here is measured; the
source command for each one is listed in
[Where the numbers come from](#where-the-numbers-come-from).

The short version: the questionnaire's **input space** is proven by Z3, the
**rendered output** of every leaf is proven by declarative invariants, and a
bounded sample of the leaves is **executed** for real. Three layers, three
different jobs — no layer replaces another.

## The three layers

| Layer | Proves | Cannot prove | Input | Measured unit cost |
|---|---|---|---|---|
| **L1 — input space** | every `when` is satisfiable, no contradictory or unreachable combination exists, and the leaves can be enumerated | anything about what the answers *render* | `copier.yml` + `questions/*.yml` | milliseconds, no render |
| **L2 — output invariants** | every leaf's render satisfies its declared file-set and content predicates | install, run, network, docs build — anything needing a venv or an external tool | all **205** leaves | **0.58 s/leaf** serial (119 s ÷ 205); 205 leaves ≈ **10 s** with 16 xdist workers and the session render cache |
| **L3 — execution** | the generated project actually syncs, tests, type-checks and builds its docs | enumeration — it runs a sample, so it is evidence for those leaves only | a bounded sample of **8** leaves | **13–24 s/case**; the whole 8-leaf sample 132–195 s |

### L1 — the input space (Z3)

`tools/when_model.py` encodes each area gate's `when` expression for Z3 (the
tokenizer, `when_expr_satisfiable` and the string domains), and
`tests/test_copier_structure.py` asks the model two questions of the
questionnaire: is every `when` satisfiable, and does the sweep detect typo'd
gates, self-contradictions and impossible genre combinations (the detectors
have meta-tests that break them on purpose to prove they still detect).
`tools/z3_witnesses.py` turns the same model into the leaf list
(`tests/matrix/witnesses.jsonl`, 205 leaves), and
`tests/test_witness_matrix.py::test_witness_leaves_match_the_generator` keeps
the committed list equal to what the generator enumerates.

L1 **cannot** say anything about rendered content, cross-file consistency, the
equivalence of two task definitions, or whether a generated project runs: those
need Jinja + copier + filesystem execution semantics, which are outside Z3.

The Z3 side of `when` is a *projection* (re-implementation) of Jinja's
evaluation, so L1's green is only as strong as that projection. What keeps it
honest is `tests/test_when_model.py`: for every declared leaf it asks copier's
own questionnaire machinery (`Worker._ask` + `Question.get_when`) every
templated `when` — 48 expressions, 9,840 verdicts — and compares that verdict
with the model's. Six probe answer sets then vary the values the leaf space
holds at their copier defaults, for 10,128 comparisons in total, and the test
asserts **per expression** that both polarities were seen: a `when` whose inputs
nothing varies fails instead of quietly proving half of it. It also checks that
the string domains the production callers pass contain every answer copier
actually gives. The test states its own narrowing — concrete assignments rather
than abstract satisfiability, the questionnaire's current expressions, and the
leaf space plus those probes — while the abstract reachability side stays with
the sweeps in `tests/test_copier_structure.py`. Treat "Z3 is green" as "the
input space is honestly enumerated", never as "the template is correct".

### L2 — output invariants over every leaf

The witness `fast` tier renders every leaf with copier (`skip_tasks=True`, no
venv), asserts the leaf's declared artifact set (present *and* absent files),
and runs `ruff format --check` / `ruff check` over the rendered Python. Renders
go through `tests/render_cache.py`, so every tier sharing the same answers pays
for one copier run; the cache is fingerprint-addressed and lives in the
session's temporary directory.

This is the layer that grows best: cost is linear in leaves, and one leaf is
sub-second. It **cannot** express anything that requires the rendered project
to be installed or executed — a leaf whose file set and content predicates are
all correct can still fail to `uv sync`, fail its own pytest, or fail
`mkdocstrings`. That residual is exactly what L3 exists for.

### L3 — bounded execution of a sample

The witness `full` tier takes 8 leaves from `FULL_SAMPLE`: one per project
family whose checks run on a bare runner, plus the one gate-off leaf that
switches the agent prompts on. Each gets `uv sync`, the generated project's own
pytest, `basedpyright`, and its docs build. Every leaf getting this treatment
would be ~10 hours, so the sample is a deliberate bound; ros2 is out of the
sample entirely (its generated recipes need `/opt/ros/$ROS_DISTRO`, not a bare
runner). The leaves the sample does not cover stay in L2.

L3 **cannot** generalize. It is evidence for eight leaves, not for the other
197, and it is not a cheaper way to run L2 — it is the only way to observe the
external toolchain. See [Why L3 stays](#why-l3-stays-the-evidence) for what
keeping it has already caught.

## Tiers: the commands and their budgets

A tier is a contract, not a habit. `fast` means "the edit loop stays inside its
budget"; `heavy` means "this builds a venv or talks to the network". When a
check moves between tiers, the budget moves with it.

| Tier | Command | Selector | What runs |
|---|---|---|---|
| Edit loop | `task test-fast` | `-m "not heavy and not slow"` | L1 + L2 + everything that neither builds a venv nor touches the network |
| Slow | `task test-slow` | `-m slow` | the serial 205-leaf batch runner (`tools/batch.py` over `tests/matrix/witnesses.jsonl`) |
| Pre-push / nightly | `task test-heavy` | `-m heavy` | L3: `uv sync` + the generated project's pytest / type check / docs build (`network` follows where the case downloads) |
| Witness render | `uv run --no-sync pytest -q tests/test_witness_matrix.py -m fast` | `fast` | L2 over all 205 leaves |
| Witness execution | `uv run --no-sync pytest -q tests/test_witness_matrix.py -m full` | `full` | L3 over the 8-leaf sample (those tests are also `heavy` / `network`) |
| Full suite | `task test` | — | everything, with coverage |

When a number in this table disagrees with the suite, the ledger wins:
`tests/matrix/tiers.json` records each tier's marker expression, the node ids
it collects and a measured wall time, `tests/test_marker_drift.py` re-collects
every tier and fails on drift, and `UPDATE_TIERS=1 uv run --no-sync pytest -q
tests/test_marker_drift.py` re-records it after a deliberate tier change.

The edit-loop budget is **30 s**; anything that pushes `task test-fast` past it
is either marked `slow` / `heavy` or is a regression — for venv and network work
the marker-drift guard enforces that structurally. The run taken for this page
on 2026-09-14 was **652 passed, 1 skipped, 1 xfailed in 26.06 s**
(`uv run --no-sync pytest -q -m "not heavy and not slow"`, 16 cores). The count
grows as tests land, so read that as a dated observation of a moving suite and
take the current numbers from the ledger above.

## Growth rules

Adding a capability is not free, and the cost is predictable:

| Change | Leaf increment | Cost |
|---|---|---|
| One more include layer (composed with all base leaves) | **+76 leaves** | ≈ +45 s serial, ≈ +3 s at 16 workers, ≈ 0 once the render cache holds the answers |
| One more gate-off dimension | +8 base leaves → **+22 leaves** | ≈ +13 s serial, ≈ +1 s at 16 workers |
| One more `project_type` | its base leaves (e.g. +3 base ≈ +8 leaves) | **plus one invariant row** in the single invariant source, **plus one L3 sample leaf** (≈ +20 s) |

!!! warning "Include layers are exclusive today"
    A leaf carries **at most one** include layer (measured: 108 leaves with
    none, 97 with exactly one, maximum 1). The layer multiplier is ~2.7×
    rather than the product of four layers because of that exclusivity. Lifting
    it — allowing two layers on one leaf — turns the multiplier into a
    combinatorial product and the leaf count becomes exponential. Any change
    that touches layer composition must declare, up front, whether it keeps
    exclusivity (choose-one) or accepts the product, and the growth table above
    stops applying if it accepts the product.

The conclusion that drives the rules below: growth pushed into L2 stays bounded
(+22 leaves ≈ +1 s parallel, 0 s cached), while growth pushed into L3 is linear
in samples and each sample is 13–24 s. So a new check goes into L2 **unless
there is a reason it cannot be expressed there**.

## Before adding a check: five questions

Answer all five before writing the check; a "no answer" is a design decision
that has not been made yet.

1. **Which existing layer does it sit on?** L1 (input space), L2 (render
   invariant), or L3 (execution). If it is "a bit of both", split it.
2. **What is its leaf increment?** Use the growth table. If it multiplies
   rather than adds, the exclusivity question above must be answered first.
3. **Which invariant row does it need?** Every file the leaf must (or must not)
   have, and every content predicate over it, belongs to the single invariant
   source (TODO §23.4 / §24.4 T6) — never to a second hand-synced dict.
4. **Which tier runs it?** Pick from the tier table and check the budget it
   lands in. A check that builds a venv or touches the network carries `heavy`
   (and `network` when it talks to the network), no exceptions.
5. **Which support level does it get?** `supported` if CI executes it end to
   end, `best_effort` if it is declared and rendered but never executed — and it
   goes into `support.yml` with a measured `why`.

## Non-goals

Stated plainly, because the vaguer version — "Z3 proves the template is
correct" — is false:

- **Z3 proves the input space only.** Satisfiability of each `when`, the absence
  of contradictory or unreachable combinations, and a complete enumeration of
  the leaves. It does not prove anything about what those leaves render.
- **The `when` model is a re-implementation**, so a Z3 green is a statement
  about the model, not directly about Jinja. `tests/test_when_model.py`
  differentially compares the two at every declared leaf and states the limits
  of that assurance (concrete assignments, the current expressions, the leaf
  space plus the probes); nothing beyond those limits is covered by L1.
- **venv builds, real pytest runs, network access, Docker and external CI are
  covered by the heavy tier on purpose.** They cannot be expressed as L2
  predicates over rendered bytes, so they stay in L3 rather than being
  re-declared into a weaker form. The `heavy` tier is a deliberate design
  decision, not debt to be paid off.
- **The goal is the three-part set** — Z3 enumerates the input space,
  invariants cover every leaf's output, sampled execution covers the external
  toolchain — **not** "Z3 alone proves everything". A proposal that argues
  "Z3 already covers it" for a run-time property is arguing the wrong thing.

### Why L3 stays: the evidence

The 8-leaf sample is not ceremony. On 2026-09-13 it failed **three leaves**, all
of them invisible to L2 (whose 205 leaves stayed green at the same time):

1. `project_type=micropython/gate=recommended` — basedpyright exited 3 with
   `File or directory ".../smoke_example" does not exist`: the shared
   `include = ["{{ pkg_dir }}", "tests"]` assumed a package directory that the
   MicroPython layout does not have. The MicroPython branch now excludes the
   package and checks `tests` + `firmware/core` instead (the firmware tree has
   its own `pyrightconfig.json` pass).
2. `project_type=online_judge/.../atcoder` — `just docs` failed with
   `mkdocstrings: accessing 'smoke_example' raises ModuleNotFoundError`: a
   code-submission workspace ships no importable package, so the generated API
   reference had nothing to collect. The competitive-programming layout now
   omits the module nav and the `mkdocstrings` plugin.
3. `project_type=cli/gate=off:use_recommended_agent` — basedpyright exit 1:
   `run(parsed.prompt, model=parsed.model)` passed `argparse.Namespace`
   attributes, which type as `Any`. The generated CLI now parses into a typed
   `_CliArgs` namespace.

All three are fixed, and all three shipped inside a render-only pipeline that
was entirely green. That is the measured justification for holding L3 at a
sample rather than dropping it: the render layers prove the file sets, and only
execution proves the toolchain.

## Support levels

`support.yml` (repository root) is the machine-readable declaration of what
this template keeps working. It uses two levels:

- **`supported`** — executed end to end by the witness `full` tier: `uv sync`,
  the generated project's own pytest, basedpyright and its docs build.
  `tests/test_support_matrix.py` asserts the declared `supported` rows are
  exactly the ledger's `tier: full` leaves, so a claim here is a measured one.
- **`best_effort`** — declared so the questionnaire's existing answers keep
  rendering, but never CI-gated for execution. The witness `fast` tier still
  renders and ruff-checks these leaves; a regression that only breaks install or
  run is not caught for them.

Two related pieces of the same vocabulary live in `support.yml` as well: the
per-entry `why` (the measured evidence for the assigned tier) and
`tier_policy`, which maps a *class* of leaf to a tier. `none` is reserved for a
future exclusion and is declared per leaf as `tier: none` plus a `reason` in
`tests/matrix/witnesses.json`; no leaf uses it today, because every declared
leaf has a recorded run.

`support.yml` is the source, not the documentation: `tools/gen_docs.py --write`
renders [the support matrix](../reference/support.md) and the README summary
from it, and `--check` fails CI when those drift.

## Where the numbers come from

| Measurement | Source command | Recorded |
|---|---|---|
| 205 leaves, 108 with no include layer, 97 with exactly one (max 1) | `tests/matrix/witnesses.jsonl` (count of `include=` per leaf) | 2026-09-14, current tree |
| L1 model vs real Jinja: 10,128 comparisons (9,840 leaf verdicts + 6 probes × 48 expressions), both polarities asserted per expression | `uv run --no-sync pytest -q tests/test_when_model.py`; with the structure sweeps, `uv run --no-sync pytest -q tests/test_when_model.py tests/test_copier_structure.py` → 16 passed, 1 xfailed | 2026-09-14, this tree |
| L2 ≈ 0.58 s/leaf (119 s ÷ 205), 205 leaves ≈ 10 s at 16 workers + cache | the serial batch runner's `--durations` entry (119 s) in the 2026-09-13 audit | TODO §23.0 / §24.0 P4 / §24.1 |
| L3 13–24 s/case; the 8-leaf sample 132–195 s | `uv run --no-sync pytest -q tests/test_witness_matrix.py -m full` | TODO §24.0 P6 (PLAN §W9 top-5) |
| L3 found 3 defects L2 missed, with L2 green on every leaf | same 8-leaf sample; `-m fast` for the render layer | TODO §24.0 P6 |
| Edit loop 652 passed, 1 skipped, 1 xfailed in 26.06 s | `uv run --no-sync pytest -q -m "not heavy and not slow"` | 2026-09-14, this tree — a dated observation; the current per-tier counts are the ledger row below |
| Per-tier counts, marker expressions and wall times | `tests/matrix/tiers.json`; re-collect with `UPDATE_TIERS=1 uv run --no-sync pytest -q tests/test_marker_drift.py`, fill `wall_seconds` from a `time task <tier>` run | 2026-09-14, this tree |
| Growth table's +76 / +22 leaf increments and their second costs | derived in the 2026-09-13 audit from the ledger's leaf counts and the 0.58 s/leaf unit | TODO §24.1 |
| Edit-loop budget of 30 s (a contract, not a measurement) | declared for the tiers in the 2026-09-13 audit | TODO §24.2 |
| "all 205 leaves executed would be ~10 hours" | the `FULL_SAMPLE` rationale comment: 205 × (venv build + docs) at ~3 min | `tests/test_witness_matrix.py` |
