# Drift Detection: How a Template Rots, and Who Notices

A project template is one of the rare programs whose most dangerous
failures arrive **without any code change**. A pinned tool releases a new
major, a dependency's license changes underneath you, upstream fixes a
bug you never saw, a formatter release reflows a file you hand-wrote —
and the template renders exactly as confidently as before. This page is
the framework this repository uses to reason about that: every way a
template can be wrong has a **source**, every way it can be noticed has a
**timing**, and the two are independent axes. Keep the matrix honest and
rot has nowhere to hide; leave a cell empty and it becomes the story of
the bug you find six months late. The internal design notes live in
`notes/Strategy.md`; this page is the transferable version.

(The runtime verification these mechanisms feed into — input space,
render invariants, execution — is a different axis again; see
[Verification Architecture](verification.md).)

## The two axes

**Sources** — where wrongness comes from:

| | Source | Examples that actually happened here |
| --- | --- | --- |
| **A** | Static quality inside the template | a `when` expression referencing a question defined later; a jinja block that renders valid YAML only for one answer |
| **B** | The render and the rendered output | a generated project that fails its own `ruff format` under one `line-length` setting but not the other |
| **C** | Aging of external packages and toolchains | copier shipping a breaking major; a PyPI floor pin outliving the package; pip-audit finding a CVE in a locked dev dependency |
| **D** | The upstream fork | DiamondLightSource/python-copier-template merging fixes this repo never reviews |
| **E** | The meta-accident: your own dev toolchain breaking the template | a pre-commit `end-of-file-fixer` rewriting `.jinja` files, whose missing trailing newline is *meaningful* |

**Timings** — when the wrongness can be noticed:

| | Timing | Property |
| --- | --- | --- |
| **1** | Before commit | milliseconds; sees only what a local linter can see |
| **2** | Push / PR CI | minutes; the workhorse, but fires **only when someone changes code** |
| **3** | Scheduled | fires **with zero code changes — the only timing that does**; a red run names an external cause |
| **4** | Logical verification (Z3) | milliseconds, no render at all; proves reachability of the input space instead of sampling it |

The matrix is MECE on purpose: a fix belongs to exactly one source cell,
a check to exactly one timing cell, and "which cell catches this?" is a
question you can ask before writing the check. The failures that hurt are
the ones whose cell was silently empty.

## The matrix, filled in

| | 1: pre-commit | 2: push/PR CI | 3: scheduled | 4: logical (Z3) |
| --- | --- | --- | --- | --- |
| **A** | ruff / typos | the jinja+YAML structural sweep | — | the satisfiability sweep (`test_copier_structure.py`: typo'd gates, self-contradictions, unreachable combinations are *proven* absent, and meta-tests break the detector on purpose to prove it still detects) |
| **B** | — | render + generated lint/format + type-check + the example executed end to end | the weekly full check (same jobs as CI, `publish: false`) | — |
| **C** | — | renovate PRs | weekly pin drift report (MicroPython, CUDA, ROS 2 EOL, Python floor, Postgres, the copier ceiling); lock-file maintenance; Thursday `pip-audit` with a deduplicated issue on failure | — |
| **D** | — | — | weekly upstream commit check, URL-direct fetch, issue on drift | — |
| **E** | auto-fixers excluded from `.jinja` / `copier.yml` | — | — | — |

Nothing exotic lives in the cells — scheduled workflows, a weekly audit,
a Z3 encode of the questionnaire's `when` expressions. The engineering is
in refusing to leave a cell empty, and in the properties below.

## What the matrix taught us

**1. The scheduled cell is the only one that fires when nobody types.**
CI is change-triggered by construction, so source C (aging) is invisible
to it: the template sits still while the world moves. The weekly full
check exists to turn "the world changed" into a red run, and it carries
its own deduplicated issue ("Scheduled full check failed — no repo
changes involved") because a red schedule you don't subscribe to is a
cell that only pretends to be filled. Schedules are staggered across
weekdays so a failure names its workflow, and each workflow owns exactly
one concern — a Friday audit finding should never share a run with a
Tuesday link check.

**2. Satisfiability is a detection timing, not a vibe.** Encoding the
questionnaire's `when` logic for Z3 proves, before any render, that every
gate is reachable and no combination is contradictory — and it proves the
*absence* of whole classes of bugs (a typo'd gate name goes unsat) rather
than sampling for their presence. Two honesty rules keep it from being
theater: the Z3 model is a *projection* of jinja's evaluation, so a
per-expression test replays every `when` through copier's own machinery
and compares verdicts (~10k comparisons, asserting both polarities occur
per expression); and the enumerated leaves are pinned to a committed
ledger whose freshness check fails with the exact regeneration command.
A logical proof nobody can regenerate is a comment.

**3. The detectors rot too — so guard the guards.** Every mechanism in
the matrix has a meta-test that breaks it on purpose: the satisfiability
sweep has detectors fed typo'd literals and expected to catch them; the
witness ledger has a test that renames a fixture and expects the freshness
check to name the command that fixes it. The ⑤-style question — "does the
Z3-enumerated leaf space actually get tested?" — was answered by a
coverage ledger recording one verdict per leaf, written atomically by the
test session itself.

**4. Your dev toolchain is an error source (E), not a neutral actor.**
The worst template bug in this repo's history was inflicted by its own
linting: a pre-commit autofixer rewrote `.jinja` files whose
missing-trailing-newline was load-bearing. The general form: any tool
that *writes* to the tree is a mutation source, and the template's
meaningful oddities (no trailing newline, multi-document YAML, jinja
blocks) are exactly what such tools normalize away. Exclusions are the
fix, and "run the tool, then assert the tree didn't change" is the test
— the regression test became moot here only because the local hooks were
removed entirely and hygiene moved to CI.

**5. The matrix is a budget for new features.** The extension runbook's
first questions ([Extending the questionnaire](extending.md)) are "what
does it sit on?" and "how many leaves does it add?" — the drift matrix
adds the third: *which cell notices when this feature rots?* A feature
whose answer is "none" ships with a named, dated review obligation
instead — the ethics registry's `review_by` is the same matrix applied to
non-code facts, where the "scheduled" cell is a literal calendar date
that reddens CI when it passes.

## Costs, honestly

The timings are cheap in this order: pre-commit milliseconds, Z3
milliseconds (no render), CI minutes, scheduled the same CI cost paid
weekly for nothing changing. The expensive mistakes are all on the empty
side of the matrix: the width-dependent formatter bug (source B) shipped
because the lightweight render tier lacked one check and the heavyweight
tier sampled too narrowly; the un-pinned copier dependency (source C)
was one renovate merge away from breaking every test at once. The
recurring pattern is not "add more checks" — it is *name the source and
the timing for every check you already have*, then look at which cells
your actual incidents came from and fill those first.
