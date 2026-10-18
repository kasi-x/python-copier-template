# Adoption Flow — plan → render → verify → merge or rollback

`architekton-py new <existing-project>` switches to **adopt mode**: instead of
overwriting, it adds what the template generates to what is already there,
reversibly. This page is the map: one paragraph per module under
`architekton/adopt_*.py`, in the order the transaction calls them.

## The transaction

```text
detect.py        →  adopt_run.py  →  adopt_revision.py  →  copier render  →  adopt_merge.py  →  adopt_confirm.py/report.py
                  │       (transaction body)                    (plan what to ask)      (overwrite=False)    (merge strategy)        (show plan or report)
                  │           └── adopt_tree.py  (snapshot, verify, roll back the tree)
                  │           └── adopt_journal.py (journal entries → --recover)
                  │           └── adopt_crash.py  (signal handler: interrupt → _undo_run)
                  └── adopt_cli.py (plan/apply/recover entry)
```

Every write goes through the journal and the crash handler: if the process
dies mid-run (or the user hits Ctrl-C), the snapshot is replayed byte for
byte.

## Module responsibilities (read order)

| File | One-line responsibility | Key guarantee |
|---|---|---|
| `detect.py` | Look at the target project, decide the mode (fresh / adopt / this-template-owned / foreign-template) | Never guesses wrong: refuses ambiguous states |
| `adopt_run.py` | Transaction body — orchestrates the whole run | **All or nothing**: writes happen inside journaled, signal-guarded block; on error, `_undo_run` restores the tree |
| `adopt_revision.py` | Which revision + which answers to expand | One source of truth for "what copier needs" |
| `adopt_tree.py` | Snapshot files/dirs, verify, roll back | **Byte-identical restore** — the safety net underneath everything |
| `adopt_journal.py` | Journal file: what was planned, written, merged | `--recover` replays this; refused if stale |
| `adopt_crash.py` | Signal handlers + `crash_drill` test | Interrupt → rollback automatically |
| `adopt_merge.py` | Merge strategy per file kind | **Adopter's content wins**: pyproject via pyproject_merge, line-files via file_merge; conflicts reported, never silently overwritten |
| `file_merge.py` | Append-only merge for `.gitignore`, `justfile`, `Makefile` | Prefix-preserving: original content must remain a prefix |
| `pyproject_merge.py` | Structured merge into `pyproject.toml` | tomlkit round-trips comments; missing deps added, existing never touched |
| `adopt_confirm.py` | Show plan, ask user, apply or step back | **Plan before apply** — dry-run / plan only is a first-class path |
| `adopt_report.py` | Human + machine report | What changed, what was skipped, why |

## Invariants you can rely on

- **Existing files stay byte-identical** unless you explicitly say otherwise
  (`overwrite=False` on the render + prefix-preserving merges).
- **No silent destruction** — `_MergeError` aborts the run and rolls back.
- **Crash-safe** — Ctrl-C or a kill inside the transaction restores the tree
  via the journal; a leftover journal makes the next run refuse until you
  `adopt.py --recover` or remove it.
- **Plan-only is real** — `--dry-run` computes the whole merge without
  writing, so you can review the diff (`adopt_report.py`) before touching
  the project.

## Where the model lives

This module set is the **Integration Surface** (L3): safety,
reversibility, explicitness. It is deliberately not flattened — the
transaction boundaries are the point. The generated content itself comes
from `template/` (L2), which is kept on one canonical source of truth so
adopt and `new` never disagree about what to emit.
