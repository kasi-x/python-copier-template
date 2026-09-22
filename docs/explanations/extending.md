# Extending the questionnaire: platforms, layers, gates

This is the runbook for growing the template — a new bot platform, a new
opt-in layer, a new gate, a new judge. The architecture is built so that
every step below has a machine check that catches its omission; the runbook
exists so you can walk the list before running the checks, not instead of
them. Read [Verification Architecture](verification.md) first for the three
layers (input space, render invariants, execution) the checks live in.

## Answer the five questions before writing code

1. **What does it sit on?** A platform is an opt-in layer over an existing
   base (`cli` / `web_api`), not a new project type. A gate sits behind an
   existing `use_recommended_*`. If nothing existing carries it, that is a
   design discussion, not an extension (see
   [Vision & Positioning](vision.md)'s scope rules).
2. **How many leaves does it add?** Each gate dimension and each included
   layer grows the witness leaf space (§24.1: +1 gate ≈ +22 leaves, +1 layer
   over all bases ≈ +76). The current budget is enforced by the
   `LEAF_BUDGET` assertion in the meta tier; exceeding it deliberately means
   raising the constant and re-measuring the witness job's wall time.
3. **Which invariant row claims it?** Every leaf the expanded space gains
   must be claimed by a `tests/matrix/invariants.yml` row — an unclaimed
   dimension fails at load time, before any render.
4. **Which tier runs it?** The witness fast tier renders every leaf
   automatically; a bounded `full`-tier sample needs a support declaration.
5. **What is its support level?** Full-tier-executed or best-effort, with
   the reason recorded (see the support declarations the ledger's
   `tier`/`why` columns carry).

## The checklist

| # | Touchpoint | What catches the omission |
| --- | --- | --- |
| 1 | Question + gate in `questions/_combo.yml` (raw `when`; never reference an effective there) | Z3 satisfiability sweep + the forward-reference tests in `tests/test_copier_structure.py`; `task question-graph` shows where definitions may live |
| 2 | Effective internals in `questions/_internal.yml` (`*_effective`, per-platform variants), placed where the forward-reference order allows | forward-reference tests; `task question-graph` for placement |
| 3 | Scaffold bodies in `_shared/` + single-line wrappers per placement (one line, comment + include, no trailing newline) | `test_machine_gate` (Jinja parses), the single-newline test |
| 4 | Dependencies, entry points, `.env.example` gate, `_tasks` model rows | `test_pyproject_fmt` / `test_generated_lint` / the agent command table (derived from the same `_tasks` model) |
| 5 | `tests/matrix/invariants.yml` rows claiming the new dimension | load-time refusal of unclaimed dimensions (`tools/invariants.py`) |
| 6 | `task witness` — regenerate `witnesses.jsonl` / `witnesses.json` | the freshness check fails with the exact command |
| 7 | `task verify-delta` — proves which leaves the change can reach: the semantic diff narrows the candidate set, only candidates re-render, and the verdict is either "PROVEN render-identical" or the exact leaves and files that changed | the manifest diff (byte-exact per candidate) and the `--audit` sampling of unaffected leaves |
| 9 | `UPDATE_TIERS=1 uv run --no-sync pytest -q tests/test_marker_drift.py` — re-records the ledger AND the doc-table counts automatically; wall times stay a human step | the tier-membership guard (a mis-stated count fails) |
| 9 | `uv run --locked python tools/gen_docs.py --write` if the gate needs a `CONDITION_PROSE` entry | `test_generated_docs_sync.py` / `gen_docs --check` |
| 10 | Markers: anything building a venv gets `heavy` (+ `network`) | the structural marker scan (`tests/test_marker_drift.py`) |
| 11 | A test module for the layer: render presence/leak + one `heavy` real-execution case | the fast tier (leak checks) and the pre-push tier (execution) |
| 12 | Docs: how-to page + `zensical.toml` nav + the features/support catalogue + `tools/check_upstream.py` floor pins | `gen_docs --check`, the support-matrix test, the upstream-check rule |
| 13 | `task predicates` — read the new sites' equivalence classes and shortcut suggestions | `tests/test_predicate_classifier.py` refuses unconditional duplicates of named internals |
| 14 | Full gates: `task lint`, `task type-check`, `task test-fast`, `task test-meta` | everything above, wired |

## The tools this runbook leans on

- `task predicates` — the condition-site inventory: equivalence classes over
  the 272-leaf space, fire counts per internal (a special case that never
  splits is a flattening candidate), naming candidates for repeated raw
  classes, and the unification guard.
- `task question-graph` — where a new internal or question may live given
  the forward-reference order, and what moving a node would break.
- `task witness` — regenerate and judge every leaf; the freshness check and
  the invariants registry make forgetting it impossible to miss.
- `UPDATE_TIERS=1 ...` — re-record the tier ledger and the documented
  counts; wall times and their `measured` dates remain human work.

## The rule the machinery cannot check for you

Mechanical equality is not intent. Two conditions that agree on every leaf
today may be separate on purpose (the layout exclusion lists; the
combinable triple guard; the `oj_bare`/`no_pkg` distinction). When the
classifier reports a coincidence, decide which of the two is the intent,
name that one, and register the other with a reason — the registries
(`DECLARED_EQUIVALENCES`, `DEFAULT_REPEATS_ALLOWED`, `invariants.yml`'s
`excluded`) exist for exactly that, and each one fails when its entry goes
stale.
