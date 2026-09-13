//! Repository copy of the V2 spike model (provenance: TODO.md §27.3; written
//! during the §26.4 spike, TLC-verified 2026-09-14, adopted into the repo per
//! §27.7 item 3 so CI -- .github/workflows/quint.yml -- can re-verify it).
//!
//! What TLC proves (quint 0.32.0, `--backend=tlc`, exhaustive over the whole
//! reachable graph: 51 distinct states, 0 left on queue): all three invariants
//! hold -- `crash_window_covered`, `crash_point_recoverable`,
//! `recovery_restores`.  From every crash point, a tree that has drifted is
//! either the committed result of a verified run or still covered by the
//! journal that `--recover` undoes.  See models/README.md for the commands.
//!
//! Skeleton model of the adopt protocol in `tools/adopt.py` (V1: on-disk
//! journal + `--recover`), written for the crash-safety question only.
//!
//! TODO §26.4 item 5 / §25.3 V2.  Non-goal: the render, the merges, copier,
//! the journal's file format.  What is modelled is the order of the durable
//! steps and what a crash in between them leaves behind:
//!
//!     write_journal   the old bytes, the may-create list: on disk and fsynced
//!                     before the first byte of the target changes
//!       -> mutate     overwrite the pre-existing file | create a file
//!       -> verify     no existing file moved, nothing unplanned was created
//!       -> commit     drop the journal (only after a verified run)
//!          | rollback undo the run, drop the journal last
//!
//! `crash` (SIGKILL, power loss) is enabled in every state: it writes nothing
//! and restores nothing, it only freezes the tree and the journal where they
//! are.  `--recover` is the same undo as the rollback, driven by the journal;
//! both drop the journal last, so a crash in the middle of an undo is a crash
//! point like any other.
//!
//! What the model deliberately abstracts away is durability: a write is either
//! wholly on disk or absent, so fsync ordering is *assumed*, not checked.  The
//! model answers "does the journal (as a step that happens before the first
//! mutation) cover every crash point", not "is the fsync itself durable" --
//! the latter stays with V1's SIGKILL drill (tests/test_adopt.py).
//!
//! Check it (quint 0.32.0, run from this directory):
//!
//!     npx --yes @informalsystems/quint run adopt_crash.qnt \
//!       --invariants crash_window_covered crash_point_recoverable recovery_restores \
//!       --max-steps=40 --max-samples=20000 --seed=1
//!     npx --yes @informalsystems/quint verify adopt_crash.qnt --backend=tlc \
//!       --invariant=crash_window_covered,crash_point_recoverable,recovery_restores
//!     npx --yes @informalsystems/quint verify adopt_crash.qnt \
//!       --invariant=crash_window_covered,crash_point_recoverable,recovery_restores --max-steps=16
//!     # not vacuous: the kill window has to be reachable (expect a violation)
//!     npx --yes @informalsystems/quint verify adopt_crash.qnt --backend=tlc \
//!       --invariant='not(kill_window_reached)'
//!
//! The TLC run is the complete one: the state is nine booleans, so TLC
//! enumerates the whole reachable graph (51 states, 0 left on queue) instead of
//! sampling it.  Apalache's `--inductive-invariant` would prove the same thing
//! without enumerating, but that mode is broken in this toolchain (quint
//! 0.32.0 + Apalache 0.56.1 rejects even `n <= 3` over one integer with "n is
//! used before it is assigned").

module adopt_crash {
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

  // --- the property, as written ----------------------------------------------

  // The tree matches the state the run found.
  val pre_run = st.old_bytes_kept and not(st.created_file)

  // Someone looking at the project would see a change.
  val visible_change = not(st.old_bytes_kept) or st.created_file

  // No partial adoption is observable: from any crash point, a tree that has
  // drifted from the pre-run state is either the committed result of a
  // verified run, or still covered by the journal that `--recover` undoes.
  val crash_window_covered = visible_change implies (st.committed or st.journal)

  // The same, stated at the crash points rather than at the drifts: whatever
  // state a kill leaves behind is recoverable.
  val crash_point_recoverable = (st.dead and visible_change) implies (st.committed or st.journal)

  // A completed `--recover` leaves the tree as it was before the run.
  val recovery_restores = st.recovered implies pre_run

  // `crash_window_covered` is not inductive on its own (a live run that has not
  // written its journal yet satisfies it, and one mutation would break it).
  // This is the strengthening that makes the induction step go through -- it is
  // preserved by every step, and it implies the property (not pre_run =
  // visible_change).  It is written out for the next reader; the complete check
  // here is TLC's exhaustive search, because Apalache's `--inductive-invariant`
  // mode is unusable in this toolchain (see the file header).
  val no_partial_adoption_inv = pre_run or st.journal or st.committed

  // Not an invariant -- the check is deliberately inverted (`--invariant=
  // 'not(kill_window_reached)'`, expect a violation).  The crash point the
  // journal exists for (drifted tree, journal still there, process gone) must
  // be reachable, or the property above protects a window this model never
  // opens and the proof is vacuous.  TLC finds it.
  val kill_window_reached = st.dead and st.journal and visible_change

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

  // A run may start from a pre-run tree with no journal in the way (so the
  // simulator can also run a second episode after a rollback or a recovery).
  val can_start =
    pre_run and not(st.journal) and not(st.dead) and not(st.committed) and not(st.rolling_back)

  // A live run that has written its journal: the states in which it may touch
  // the tree or finish.
  val live = st.journal and not(st.dead) and not(st.rolling_back) and not(st.committed) and not(st.rolled_back)

  action write_journal = all {
    can_start,
    st' = { ...st, journal: true, verified: false, rolled_back: false, recovered: false },
  }

  // The backup is on disk, so the run may now overwrite the pre-existing file.
  action mutate_modify = all {
    live,
    st' = { ...st, old_bytes_kept: false },
  }

  // ... and create a file that was not there.
  action mutate_create = all {
    live,
    st' = { ...st, created_file: true },
  }

  // What the run wrote is compared with what it promised (the render must not
  // move an existing file, and what it creates must be what the plan named).
  action verify = all {
    live,
    visible_change,
    st' = { ...st, verified: true },
  }

  // Commit: the journal is dropped and the tree stays as the run left it.
  action commit = all {
    live,
    st.verified,
    st' = { ...st, journal: false, committed: true },
  }

  // A failed verification, or SIGINT/SIGTERM: the same undo `--recover` runs.
  action begin_rollback = all {
    live,
    st' = { ...st, rolling_back: true },
  }

  // --- the undo: rollback and `--recover` are the same three steps -----------

  // The undo is running: the rollback of a live run, or `--recover` after a
  // kill.  `dead` stays set while it runs -- the process that recovers is a
  // new one, and what matters is that no adopt progress is possible.
  val undoing = st.journal and (st.dead or st.rolling_back)

  // Put the recorded old bytes back.
  action undo_restore = all {
    undoing,
    st' = { ...st, old_bytes_kept: true },
  }

  // Delete what the run created (read off the disk: present now, absent before).
  action undo_remove_created = all {
    undoing,
    st' = { ...st, created_file: false },
  }

  // Drop the journal last: a kill anywhere before this still leaves it for the
  // next `--recover`, and recovering twice is a no-op.
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

  // SIGKILL, a power loss.  Nothing is undone here; the tree and the journal
  // are left exactly as they are.
  action crash = all {
    not(st.dead),
    st' = { ...st, dead: true },
  }

  // `--recover` when there is no journal: nothing was changed (the run died
  // before it wrote one) or the run had already committed.  Both are success.
  action recover_nothing = all {
    st.dead,
    not(st.journal),
    pre_run or st.committed,
    st' = { ...st, dead: false },
  }

  // The journal's unlink is deliberately not fsynced, so a power loss can bring
  // it back (adopt.py `_remove_journal`).  The tree is already pre-run, and
  // recovering again is a no-op -- modelled so that path is checked too.
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
