# Ethics Sections as an External Source

The ethics appendix (`_shared/ethics/`, surfaced into generated `AGENTS.md`)
is the one part of this template whose content has its own review cadence —
OWASP revisions, FIPS finalization, Let's Encrypt chain ceremonies, regional
law — independent of the template's release cycle. That makes it the natural
candidate to split into its own repository so other templates and projects
can consume the same reviewed text. This page records the design for that
split: what moves, what stays, and why the sync happens at vendor time and
never at render time. It is a design note, not yet implemented.

## Why not fetch at render time

The tempting version — `copier copy` pulls the latest ethics text from the
external repo — breaks the property the whole verification stack rests on:

- **A render must be a pure function of the template's git tree.** The Z3
  witness leaves, the render invariants, and the update rehearsal all assume
  that the same commit produces the same output. A network fetch makes the
  output depend on the day it ran.
- **Offline contract.** `task check` / `task type-check` deliberately exclude
  network so a fresh clone works offline; a render-time fetch would be the
  first violation.
- **`copier update` determinism.** The update path diffs the recorded
  revision against the target revision. If the text between them can drift
  outside git, the merge produces diffs no commit explains — the exact class
  of bug the rehearsal exists to catch.

So the external repo is the *source of truth for content*, and this repo
*vendors* a snapshot. The render never sees the network.

## What moves, what stays

The split is content vs. wiring — the line is drawn at "does this text
reference a template flag":

| Moves to the external repo | Stays here |
| --- | --- |
| Section bodies (`*.md.jinja` prose) | `REGISTRY.yml` — the gate column names template flags (`scraping_effective`, `oj_code`, `mcp_effective`); moving it would leak the flag namespace into a repo that should not know it exists |
| `review_by` dates and watch metadata | The `when:`/audience mapping (which leaf classes get which section) |
| Source citations in each section's `why` | The enforcement level (L0/L1/L2) and the invariants.yml predicates that check it |
| The `_template.md.jinja` section shape | `tools/ethics.py` presence triggers and the appendix assembly in `AGENTS.md.jinja` |

The external repo holds **flag-agnostic content**: each section is a file
with frontmatter (`id`, `audience`, `review_by`, `sources`) and a prose body.
It must not contain `{{ scraping_effective }}`-style conditionals — gating is
this repo's job, applied at vendor time by the registry row.

## The sync contract

Same pattern as `check-upstream-fork`: a scheduled workflow diffs the
external repo's sections against the vendored copy and opens a PR when they
diverge. A human reviews the diff (a section edit is a content decision, not
a merge), then the vendor commit lands. The marker file records which
external SHA is vendored, so the check only fires on genuinely new upstream
work — the permanent-red trap the fork check escaped.

```text
ethics-sections (source of truth)      python-copier-template
┌──────────────────────────┐         ┌────────────────────────────┐
│ sections/*.md.jinja       │  sync   │ _shared/ethics/ (vendored) │
│  flag-agnostic prose      │ ──────► │ REGISTRY.yml (flag gating) │
│  frontmatter: id,         │   PR    │ invariants.yml predicates  │
│   audience, review_by     │         │ tools/ethics.py triggers   │
└──────────────────────────┘         └────────────────────────────┘
        ▲ own review cadence                 ▲ scheduled sync opens PR
        (OWASP / FIPS / LE watch)            on content drift only
```

## Versioning

The vendored snapshot is pinned to an external SHA (the marker file), not a
floating `main`. A template release therefore ships a *known* ethics text —
the release notes can name it — and a `copier update` between two template
tags shows the ethics diff as part of the template diff, reviewable like any
other change. Bumping the vendored SHA is a deliberate act (the sync PR),
which is what keeps a surprise upstream edit out of a user's `copier update`.

## When this is worth doing

The split pays for itself only when a second consumer exists — another
template, a sibling project, an organization wanting the same reviewed
sections. For a single consumer the vendor machinery is cost without
benefit: `_shared/ethics/` is already a clean content/wiring split inside
this repo, and the registry already isolates flag knowledge. The trigger to
implement this page is the first external consumer asking for the sections,
not before.
