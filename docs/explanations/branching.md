# Branching Model: Code, Vendored Content, Release

This template's repository mixes three things with different review cadences
and different blast radii: the template's own code, vendored external content
(ethics sections, and anything else the external-source pattern in
[Ethics as External Source](ethics-external.md) later covers), and release
state. Keeping them on one branch means a legal-text edit and a renderer bug
fix share a merge train and a CI run. This page records the branch layout
that separates them. It is a design note; the branches are created lazily as
each stream first has real work.

## The three streams

| Stream | Branch pattern | What lands here | Cadence |
| --- | --- | --- | --- |
| **Pure code** | `main` + `exp/<name>` | template sources, questions, tools, tests, CI | continuous; `exp/*` for work that might be thrown away |
| **Vendored content** | `vendor/<source>` | `_shared/ethics/` snapshots from the external repo, any future vendored content | on upstream drift only — the sync workflow opens the PR |
| **Release** | tags on `main`, `release/<ver>` only if a hotfix line is ever needed | release tags (`6.1.0`), never long-lived branches | per release |

`main` stays the integration branch and the only one CI gates hard. The
separation is about *where work lands first*, not about maintaining parallel
histories.

## Why not long-lived parallel branches

A permanent `legal` or `content` branch that `main` periodically merges is
the wrong shape here: vendored content is a *snapshot*, not a parallel line
of development. It has no independent commits to preserve — the external
repo owns the history. So the vendored stream is a sequence of
`vendor/<source>` PRs that each replace the snapshot wholesale and merge
into `main` like any dependency bump. No branch lives long enough to drift.

The same argument kills a permanent `release` branch: releases are tags on
`main`, and the release workflow already runs on tag push. A `release/<ver>`
branch only earns its place the day a hotfix has to go out while `main` has
already moved on — create it then, from the tag, not before.

## Experimental work

`exp/<name>` is for template work that might not survive contact with the
witness suite — a new `project_type`, a questionnaire restructure, a
verification experiment. Rules:

- **CI runs on `exp/*` pushes** (the push trigger is not branch-scoped), so
  an experiment gets the full gate without touching `main`.
- **No review requirement, no merge guarantee.** An `exp` branch that works
  gets rebased onto `main` and merged as ordinary commits; one that doesn't
  gets deleted. Nothing cherry-picks *from* `exp` back into a feature
  branch — the experiment is the unit.
- **Naming carries the hypothesis**: `exp/scraping-project-type`, not
  `exp/wip`. A branch named after what it's testing is deletable on sight
  six months later; `wip` is not.

## What this buys

- **Blast radius is visible in the branch name.** A red CI run on
  `vendor/ethics` means upstream content changed; on `exp/foo` means the
  experiment is wrong; on `main` means the template broke. Today all three
  look identical.
- **Vendored content gets its own review gate.** A legal-text diff is a
  content decision — it should be a PR a human reads, not a line in a code
  merge. The `vendor/*` PR is exactly that.
- **`main` history stays code-only.** `git log main` reads as template
  changes; content bumps are merge commits whose PR holds the upstream diff.

## Relationship to the ethics split

This model is what [Ethics as External Source](ethics-external.md) needs on
the consuming side: the external repo owns content history, `vendor/ethics`
PRs are the sync mechanism, and `main` never blocks on upstream's cadence.
Until that split is implemented, `_shared/ethics/` edits land on `main`
directly — the branch model is forward-looking, not a reason to route
in-repo edits through a branch that has no upstream.
