# Additional copier features under study

Essential copier-side features, distilled from building and operating this
template. The nine reported candidates (`notes/COPIER_UPSTREAM.md` items
1–9) are fixes to existing behavior; the items below are *new* capability.
Each one earned its place by solving a pain this template hit for real
— no speculative catalog.

Rules for promoting an idea here:

- A real template-author pain behind it (ours or a cited upstream issue).
- Staged smallest-first: docs, then message, then flag, then subcommand.
- Design-heavy items go through upstream Discussion before an issue or PR.

Filing order: small UX/docs wins first (F3, F5), then F6, then the
design-heavy F1/F2/F4/F7 via Discussion. Research items stay parked until
upstream appetite is confirmed.

## F1. Machine-readable questionnaire export (LLM-friendly)

Status: proposed.

Problem: agents and CI cannot drive the interactive questionnaire. Answering
requires parsing help text, and `--data-file` mistakes surface one at a
time. This template's own question logic is machine-verified (Z3
satisfiability over every `when` path) yet not machine-readable to callers.

Proposal: a read-only flag (name open to bikeshed, e.g.
`copier copy --print-questions --format json`) emitting the resolved
question list — name, type, `when`, `choices`, `default`, `help` — for a
given `--data`/`--defaults` input, so an agent can answer programmatically.
Shares its missing-answer report format with F3.

Staging: 1) issue with a schema sketch, 2) read-only flag, 3) wire the F3
machine-readable missing list into the same schema.

## F2. `copier template lint`

Status: proposed.

Problem: every serious template reimplements the same structural checks.
Ours took ~750 lines (`tests/test_copier_structure.py`): every asked
question has a `default`, every `when`/`default`/`choices` reference
resolves, question references are forward-only, every `when` is
satisfiable, template path/body references exist.

Proposal: a `copier template lint` subcommand (or `copier copy --check`)
running that checklist with an error/warning split (dead `when: false`
variables warn; dangling references fail).

Staging: 1) docs "template author checklist" page, 2) lint with the
error/warning split.

## F3. Batch missing-answer report (+ machine-readable form)

Status: proposed (extends `notes/` item 5 and draft `05`).

Problem: non-interactive runs abort on the *first* missing required answer
as a bare `ValueError` with a traceback — one CI round-trip per answer.

Proposal: collect all missing required answers and report them once as a
`UserMessageError` (clean message, exit 1):
`Missing answers for required questions: package_name, git_platform`.
With `--format json`, emit `{"missing": [...]}` using the F1 schema so
agents can close the loop without parsing prose.

## F4. Extension dependency declaration (`_requires` sketch)

Status: partially obsolete (2026-09-09) — this template removed its only
`_jinja_extensions` consumer (copier-template-extensions) and now generates
with a bare `uvx copier copy --trust ...`. The `_requires` sketch stays
valid for templates that genuinely need third-party extensions, but it is
no longer on this template's own critical path.

Problem (as filed): `_jinja_extensions` must be importable by copier
itself, but the template has no key to declare that. Isolated runners
(`uvx copier copy`) die with `ExtensionNotFoundError` and no actionable
hint.

Proposal: a `copier.yml` key sketch (e.g. `_requires: [package-spec, ...]`)
that copier validates and reports precisely ("this template needs
`copier-template-extensions`; re-run with `uvx --with ...`"). Never
auto-install: installing into the user's environment is code execution, so
at most validate, and gate any future action on `--trust`.

Staging: docs recipes + error-message hint first (small PRs), key design
via Discussion.

## F5. Stale-tag checkout warning

Status: proposed (extends `notes/` item 9 and draft `09`).

Problem: `copier copy <url>` without `--vcs-ref` checks out the latest git
*tag*, not the default branch. A fork that has not cut its own releases
inherits upstream's tags, so that tag can point at a long-abandoned ancestor
— users silently receive the old questionnaire and the old files. This exact
trap produced two real bug reports against this template in one week, before
its own 6.0.0 detach release became the newest tag and the plain command
started resolving the right template.

Proposal: when the resolved ref is a tag N commits behind the default
branch, warn, e.g. `Warning: using tag 5.4.0, which is 44 commits behind
the default branch main. Pass an explicit ref — a newer release tag, or
--vcs-ref=main for unreleased branch work — to render that instead.`
The clone already exists, so detection is one
`git rev-list --count <branch>..<tag>` call. Docs note first (small),
warning second.

## F6. Trust-list management CLI

Status: proposed (extends `notes/` item 7 and draft `07`).

Problem: `--trust` can be persisted in the settings `trust` list, but there
is no CLI path and the docs bury it — so every F1-style refusal message
that says "add it to the trust list" points at an undiscoverable remedy.

Proposal: docs example first (small), then a CLI sketch such as
`copier settings trust add|list|remove <url-prefix>`.

## F7. Dry-run / preview rendering

Status: proposed.

Problem: CI and agents cannot preview what a template *would* generate:
resolving answers, rendering to a temp dir, and listing the file set with a
summary — writing nothing. Today the only preview is a real copy.

Proposal: `copier copy --dry-run` resolving answers (reusing the F3
report on gaps), rendering to a temp dir, printing the file list plus a
summary, and writing nothing to the destination. Unsafe-feature refusal
(item 1 wording) still fires before any render.

## Research (parked — Discussion first, no proposal yet)

- Multiselect question type. Our base+layer combos (`include_*` booleans
  over a single-choice `project_type`) work around its absence; native
  support would need answers-file compatibility work.
- Dynamic `_subdirectory` per answer. Genre-split trees were measured and
  rejected here (64 shared files across 8 genres); native support would
  change that math, but only upstream can decide.
- Programmatic interface for copier (API client, MCP server, or schema over
  stdio) for agent-driven generation. Needs upstream appetite confirmed
  before any spec.
