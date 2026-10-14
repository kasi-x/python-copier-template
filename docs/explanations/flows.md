# Processing Flows

Four end-to-end flows in one place: how answers become a project, how adoption
stays reversible, how legal content reaches `AGENTS.md`, and which CI workflow
watches what. Each diagram names real files, jobs, and tools — the prose under
it points at the implementation.

## Questionnaire to generated project

`questions/` declares the gates, `architekton/z3_witnesses.py` enumerates the leaf
space, `architekton/batch.py` renders each leaf through copier, and the invariant
layer checks the output. Details live in [Verification Architecture](verification.md).

```mermaid
flowchart TD
    Q["questions/*.yml<br/>(gates + layers)"] --> Z3["architekton/z3_witnesses.py build()"]
    Z3 --> WL["tests/matrix/witnesses.jsonl<br/>(272 leaves)"]
    WL --> TW["tests/test_witness_matrix.py<br/>(render each leaf via copier)"]
    TW --> BR["architekton/batch.py render()<br/>(skip_tasks=True, no venv)"]
    BR --> GP["generated project tree"]
    GP --> IV["architekton/invariants.py<br/>+ tests/matrix/invariants.yml"]
    IV --> TRI["tests/test_render_invariants.py<br/>(content predicates)"]
    TRI --> OK(["artifacts: src/, tests/,<br/>docs, CI, AGENTS.md"])
```

The render is a pure function of the template's git tree: the same commit
produces the same output. Anything that would break that (network fetches,
per-render stamps) is excluded or masked — see `mask_render_stamps` in
`architekton/batch.py`.

## Adopt and update: the crash-safe transaction

```mermaid
stateDiagram-v2
    [*] --> Planned: adopt() plans answers (detect.detect + derive_answers)
    Planned --> DryRun: --dry-run
    DryRun --> [*]
    Planned --> Journaled: _write_journal (.copier-adopt-journal.json, fsynced)
    Journaled --> Rendered: batch.render (skip_if_exists, overwrite=False)
    Rendered --> Verified: _verify (changed/removed/created)
    Verified --> RolledBack: existing file touched, _undo_run via _roll_back
    Verified --> Merged: clean add-only, _finish_with_merges
    Merged --> Committed: _remove_journal
    Committed --> [*]
    RolledBack --> [*]
    Journaled --> Killed: process killed (journal stays on disk)
    Rendered --> Killed
    Killed --> Recovered: adopt.py --recover (adopt_journal.recover)
    Recovered --> [*]
```

Two layers cover two failure classes: the in-process rollback
(`_signals_roll_back` in `architekton/adopt_crash.py`, plus `_roll_back` in
`architekton/adopt_tree.py`) handles failures the process survives; the journal
(`JOURNAL_NAME` in `architekton/adopt_types.py`) covers kills — while it exists,
the run has not committed, so `--recover` can finish the undo. A stale
journal blocks the next run (exit 4) until it is recovered.

## Ethics and law distribution: this template is one entry point

Legal content flows downstream through three external repositories before it
reaches a generated `AGENTS.md`. The full contract is
[Ethics as External Source](ethics-external.md); this is the downstream end
of that chain — rendered here for one consumer (new Python projects), not
the pipeline's end. The canonical org-wide picture, where this template is
one adoption entry point beside any other repository via daimonion, is the
[politeuma architecture diagram](https://github.com/politeuma/.github/blob/main/profile/diagram.md):
law-map is the rulebook, kanon renders the prose, daimonion delivers it,
and architekton-py is one way in.

```mermaid
flowchart LR
    OL["open-law<br/>(world legislation corpus)"] --> LM["law-map<br/>(THE RULEBOOK:<br/>obligation graph)"]
    LM --> CX["kanon<br/>(reviewed prose,<br/>generated MANIFEST.yml)"]
    CX --> DW["_shared/daimonion-when.jinja<br/>(answers → when conditions)"]
    DW --> DC[".daimonion.yml<br/>(declared conditions)"]
    DC --> AM["daimonion agents-md --write<br/>(fills the marker block)"]
    AM --> AG["AGENTS.md<br/>(empty markers + linter block)"]
    AM -.->|"same linter, other repos"| OTHER["any other repo<br/>(via daimonion)"]
```

Watchers on the chain, each naming exactly one failure:

## CI at a glance: four lanes

Each scheduled lane is staggered so a red run names exactly one cause.
`ci.yml` handles push/PR plus the nightly heavy tier; the weekly lanes only
watch drift that push/PR CI cannot see.

```mermaid
flowchart TD
    subgraph push["ci.yml (push main/tags, pull_request, nightly 0 3)"]
        CH["changes<br/>(docs-only gate)"] --> T["test (test-fast)<br/>test-meta"]
        L["lint (lint,type-check)"]
        H["hygiene"]
        T --> D["docs"]
        T --> EX["example (main only)"]
        T --> REL["release (tags only)"]
        HN["test-heavy + test-randomly<br/>(schedule only)"]
        T --> REQ["required-checks-passed"]
        L --> REQ
        H --> REQ
        D --> REQ
    end
    subgraph sched["scheduled-check.yml (weekly TUE 07:00)"]
        SL["lint / test / docs<br/>(toolchain drift)"]
        PX["pixi-render-test<br/>poetry-render-test"]
        LAW["law-map-review-by"]
        ODI["open-drift-issue"]
        SL --> ODI
        PX --> ODI
    end
    subgraph per["periodic.yml (weekly WED 08:00)"]
        LC["linkcheck (lychee)"]
        PR["patch-rot<br/>(copier contribution branches)"]
    end
    subgraph sc["scorecard.yml (push main, weekly SAT 01:30)"]
        AN["analysis<br/>(ossf/scorecard-action + upload-sarif)"]
    end
```

Adjacent but separate: `pr.yml` (job `validate-pr-title`, conventional-commit
titles), `e2e-ecosystem.yml` (weekly FRI cross-repo chain),
`dependency-audit.yml` (weekly pip-audit), `security.yml` (zizmor workflow
audit), and `update-rehearsal.yml` (the `copier update` path the adopt flow
depends on).
