# Formal models of the adopt protocol (Quint)

The crash-safety argument that backs the journal design in `tools/adopt.py`,
kept as machine-checkable models instead of a prose claim.  Provenance: the
models were written and verified during the §26.4 V2 spike on 2026-09-14
(TODO.md §27.3); they were adopted into the repository per TODO.md §27.7
item 3 so CI re-verifies them on every change instead of trusting the spike
transcript (`.github/workflows/quint.yml`).

## What the model abstracts

One adopt run, as the order of its durable steps (the render, the merges and
copier itself are out of scope; the observable tree is two booleans):

    write_journal   the old bytes and the may-create list are on disk
                    (fsynced) before the first byte of the target changes
      -> mutate     overwrite the pre-existing file | create a file
      -> verify     nothing existing moved, nothing unplanned created
      -> commit     drop the journal (only after a verified run)
         | rollback undo the run, drop the journal last

`crash` (SIGKILL / power loss) is enabled in every state: it writes nothing
and restores nothing, it only freezes the tree and the journal where they
are.  `--recover` after a crash is the same undo as the rollback, driven by
the journal; both drop the journal last.  Durability is deliberately
abstracted away: a write is wholly on disk or absent, so fsync *ordering* is
assumed, not checked -- the fsync itself is what V1's SIGKILL drill
(`tests/test_adopt.py`) exercises on the real implementation.

The state is nine booleans, so TLC's search is exhaustive over the whole
reachable graph (51 distinct states, 0 left on queue), not a sample: an
`[ok]` below means every reachable state was checked.  Each run takes a
couple of seconds.

## Files

- `adopt_crash.qnt` -- the protocol as implemented.  TLC proves all three
  invariants hold: `crash_window_covered`, `crash_point_recoverable`,
  `recovery_restores`.
- `adopt_crash_journal_late.qnt` -- the guard's guard: the same model with
  one change, the run may touch the tree *before* the journal is on disk.
  This variant is EXPECTED TO FAIL: TLC finds a 3-state / 2-step
  counterexample (init -> mutate -> crash) leaving a visibly changed tree
  with no commit and no journal -- nothing to recover with.  If this file
  ever verifies clean, the property the main model proves is too weak to
  guard the protocol; the CI workflow runs this check inverted and fails
  when the mutant passes.

## Running

quint is pinned at 0.32.0 (npm: `@informalsystems/quint`).  From the
repository root:

```console
$ quint verify --backend=tlc models/adopt_crash.qnt \
    --invariant=crash_window_covered,crash_point_recoverable,recovery_restores
...
153 states generated, 51 distinct states found, 0 states left on queue.
[ok] No violation found
```

The mutant must fail, and this is the exact command to see the
counterexample (TLC prints the trace: state 1 init, state 2 `mutate_create`,
state 3 `crash` with `journal |-> FALSE` and a changed tree):

```console
$ quint verify --backend=tlc models/adopt_crash_journal_late.qnt \
    --invariant=crash_point_recoverable
...
Error: Invariant q_inv is violated.
[violation] Found an issue
error: found a counterexample
```

Why trust the `[ok]` above at all (non-vacuity): the kill window the journal
exists for must actually be reachable.  That check is deliberately inverted
and expects a violation, so it is not part of CI:

```console
$ quint verify --backend=tlc models/adopt_crash.qnt --invariant='not(kill_window_reached)'
...
[violation] Found an issue        # good: the window is reachable
```

CI (`.github/workflows/quint.yml`) runs the first two: the good model must
exit 0, the mutant must exit non-zero *with a counterexample* -- a mutant
step that fails for any other reason (tooling, missing JVM) fails the job
too, so a broken toolchain cannot fake a passing guard.

## JVM requirement (empirically checked with quint 0.32.0)

`quint verify --backend=tlc` needs a JVM; quint bundles no JRE of its own.
The TLC path runs two Java programs -- it compiles the model via Apalache
0.56.1 and then runs TLC 2.19 (both are fetched by quint into `~/.quint` on
first use).  With no `java` on `PATH` the run dies at the launcher:
`apalache-mc: line 72: exec: java: not found`.

The workflow therefore needs a JDK on the runner, and GitHub's
`ubuntu-latest` images ship Temurin JDKs preinstalled, so it relies on the
preinstalled JVM and has no `setup-java` step.  Verified locally with
OpenJDK 21.0.12; if a future runner image drops the preinstalled JDK, add
`actions/setup-java` (temurin, 21) before the quint steps.
