//! Repository copy of the V2 spike mutant (provenance: TODO.md §27.3; written
//! during the §26.4 spike, TLC-checked 2026-09-14, adopted into the repo per
//! §27.7 item 3).
//!
//! EXPECTED TO FAIL -- this is the guard's guard.  With the journal written
//! one step late, TLC (quint 0.32.0, `--backend=tlc`) finds a 3-state /
//! 2-step counterexample (init -> mutate -> crash): a visibly changed tree,
//! no commit, no journal -- nothing to recover with.  If this file ever
//! verifies clean, the main model's proof guards nothing; CI
//! (.github/workflows/quint.yml) runs this check inverted and fails when the
//! mutant passes.  See models/README.md for the exact commands.
//!
//! VARIANT of `adopt_crash.qnt`: the journal write is late by one step.
//!
//! TODO §26.4 item 5: "the guard's guard".  Same skeleton, same property, one
//! change -- the run may touch the tree before the journal is on disk, so the
//! journal is written *after* the first mutation instead of before it:
//!
//!     can_start  = pre_run and no journal and alive      (unchanged)
//!     touching   = alive                                  (NEW: no `journal` in the guard)
//!     mutate_*   use `touching` instead of `live`
//!     write_journal  may run while the run is alive, mutated or not
//!
//! Everything else -- verify, commit, the undo, crash, recovery -- is the same
//! as the main model.  The model must find a trace that mutates and then dies
//! before the journal exists: a visibly changed tree, no commit, no journal.
//!
//! Check it (quint 0.32.0, run from this directory -- each expects a violation):
//!
//!     # the drift itself, with the process still alive
//!     npx --yes @informalsystems/quint verify adopt_crash_journal_late.qnt \
//!       --backend=tlc --invariant=crash_window_covered
//!     # the kill point, and the dead end it leaves
//!     npx --yes @informalsystems/quint verify adopt_crash_journal_late.qnt \
//!       --backend=tlc --invariant=crash_point_recoverable
//!     # the same by random simulation, with a seed to reproduce
//!     npx --yes @informalsystems/quint run adopt_crash_journal_late.qnt \
//!       --invariant=crash_window_covered --max-samples=20000 --max-steps=10
//!
//! The main model, checked exhaustively the same way, has no such trace.

module adopt_crash_journal_late {
  // The observable tree is two booleans -- all the crash ordering needs:
  //   old_bytes_kept  the pre-existing file still holds its original bytes
  //   created_file    one of the files the run creates is present
  // The pre-run state is (true, false).
  type State = {
    old_bytes_kept: bool,
    created_file: bool,
    journal: bool, // the journal is on disk (written by rename: present whole, or absent)
    verified: bool,
    committed: bool, // reached the commit point: journal dropped after a verified run
    rolling_back: bool, // a live-run undo (failed verify, SIGINT/SIGTERM) is in progress
    rolled_back: bool,
    dead: bool, // the process is gone: only the undo path (`--recover`) can follow
    recovered: bool, // a journal-driven undo ran to completion
  }

  var st: State

  // --- the property, unchanged -----------------------------------------------

  val pre_run = st.old_bytes_kept and not(st.created_file)

  val visible_change = not(st.old_bytes_kept) or st.created_file

  val crash_window_covered = visible_change implies (st.committed or st.journal)

  val crash_point_recoverable = (st.dead and visible_change) implies (st.committed or st.journal)

  val recovery_restores = st.recovered implies pre_run

  val no_partial_adoption_inv = pre_run or st.journal or st.committed

  // The bug's end state: a drifted tree, no journal, a dead process, no commit.
  // This is exactly the negation of `crash_point_recoverable`, and no action of
  // the model is enabled in it (every undo step needs the journal,
  // `recover_nothing` needs the pre-run tree or a commit, `write_journal` and
  // `crash` need a live process) -- so a trace that reaches it dead-ends, which
  // is what "no recovery exists" means.  Checking it as an invariant (expect a
  // violation) shows the state is reachable.
  val unrecoverable = st.dead and not(st.journal) and visible_change and not(st.committed)

  // --- the protocol ----------------------------------------------------------

  action init = st' = {
    old_bytes_kept: true,
    created_file: false,
    journal: false,
    verified: false,
    committed: false,
    rolling_back: false,
    rolled_back: false,
    dead: false,
    recovered: false,
  }

  // VARIANT (1/3): the journal may still be written first, or not.
  val can_start =
    not(st.journal) and not(st.dead) and not(st.committed) and not(st.rolling_back) and not(st.rolled_back)

  // A live run that has written its journal: the states in which it may finish.
  val live = st.journal and not(st.dead) and not(st.rolling_back) and not(st.committed) and not(st.rolled_back)

  // VARIANT (2/3): a live run may touch the tree with no journal on disk.
  val touching = not(st.dead) and not(st.rolling_back) and not(st.committed) and not(st.rolled_back)

  action write_journal = all {
    can_start,
    st' = { ...st, journal: true, verified: false, rolled_back: false, recovered: false },
  }

  // VARIANT (3/3): `live` -> `touching`.
  action mutate_modify = all {
    touching,
    st' = { ...st, old_bytes_kept: false },
  }

  action mutate_create = all {
    touching,
    st' = { ...st, created_file: true },
  }

  action verify = all {
    live,
    visible_change,
    st' = { ...st, verified: true },
  }

  action commit = all {
    live,
    st.verified,
    st' = { ...st, journal: false, committed: true },
  }

  action begin_rollback = all {
    live,
    st' = { ...st, rolling_back: true },
  }

  // --- the undo: rollback and `--recover` are the same three steps -----------

  val undoing = st.journal and (st.dead or st.rolling_back)

  action undo_restore = all {
    undoing,
    st' = { ...st, old_bytes_kept: true },
  }

  action undo_remove_created = all {
    undoing,
    st' = { ...st, created_file: false },
  }

  action undo_drop_journal = all {
    undoing,
    pre_run,
    any {
      all {
        st.rolling_back and not(st.dead),
        st' = { ...st, journal: false, rolling_back: false, rolled_back: true },
      },
      all {
        st.dead,
        st' = { ...st, journal: false, dead: false, recovered: true },
      },
    },
  }

  // --- crash and recovery ----------------------------------------------------

  action crash = all {
    not(st.dead),
    st' = { ...st, dead: true },
  }

  action recover_nothing = all {
    st.dead,
    not(st.journal),
    pre_run or st.committed,
    st' = { ...st, dead: false },
  }

  action unlink_lost = all {
    st.recovered,
    not(st.journal),
    st' = { ...st, journal: true, recovered: false, dead: true },
  }

  action step = any {
    write_journal,
    mutate_modify,
    mutate_create,
    verify,
    commit,
    begin_rollback,
    undo_restore,
    undo_remove_created,
    undo_drop_journal,
    crash,
    recover_nothing,
    unlink_lost,
  }
}
