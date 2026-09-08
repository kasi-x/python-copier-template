# copier-fork workbench

Workbench for contributing back to `copier-org/copier`: fork operations,
new-feature specs, and PR-ready patches.

Two hubs, split on purpose:

- `notes/COPIER_UPSTREAM.md` + `notes/upstream-drafts/` — the nine filed
  contribution candidates (with upstream source refs against copier 9.18.1),
  postable English drafts `01`–`10`, and two ready-to-file patches.
  That material is frozen: do not rework it here.
- This directory — all *new* work: feature specs (`FEATURES.md`),
  new patches (`patches/`), and fork helpers (`scripts/`).

## Non-goals

- No vendored upstream code. This directory never contains a copy of copier
  itself. Files under `patches/` are diffs authored against upstream
  (quoted context lines only) — our own contribution, not a copy.
- Nothing here reaches generated projects. The workbench lives outside
  `template/` (same as `_shared/`, `questions/`, `tools/`), so copier never
  copies it into a rendered project. No `copier.yml` exclusion needed.

## Layout

| Path                 | Role                                                      |
| -------------------- | --------------------------------------------------------- |
| `README.md`          | This file: the hub.                                       |
| `FEATURES.md`        | Additional copier features under study (F1–F7 + research).|
| `patches/`           | New PR-ready patches (`<area>-<slug>.patch`) + status doc.|
| `scripts/`           | Fork setup / upstream sync / patch verification helpers.  |

## Workflow

1. One time: `scripts/fork-setup.sh` forks `copier-org/copier`, clones it,
   and wires the `upstream` remote (upstream branch convention: `master`).
2. Stay current: run `scripts/sync-upstream.sh` from inside the checkout
   (`cd /path/to/copier` first — it acts on the current directory).
3. Spec first: write or extend the feature in `FEATURES.md`, then implement
   it in the fork on a topic branch.
4. Export: `git format-patch -1 --stdout HEAD > patches/<area>-<slug>.patch`,
   then check it with `scripts/verify-patch.sh`.
5. File it yourself. Copier's `AI_POLICY.md` forbids autonomous agent
   filing, and drafts must be reworded in your own words before posting.
   The exact `gh` commands live under "投稿手順" in
   `notes/COPIER_UPSTREAM.md`.

Baseline: copier 9.18.1 (this repo's `.venv`). Re-verify source-line refs
when the fork moves past it.
