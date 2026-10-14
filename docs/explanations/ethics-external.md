# Ethics Content Lives in Kanon; the Template Emits Conditions

The ethics appendix used to be vendored prose: `_shared/ethics/` carried a
pinned snapshot of kanon sections, `_shared/ethics/REGISTRY.yml` gated each
one on template flags, and the generated `AGENTS.md` shipped the matching
prose inline. That changed: **content moved to kanon, the linter owns the
wiring, and this template only emits configuration.**

The one part of this template whose content has its own review cadence —
OWASP revisions, FIPS finalization, Let's Encrypt chain ceremonies, regional
law — lives upstream as **[kanon](https://github.com/politeuma/kanon)**,
the canonical section texts of the Good-future charter, so other templates
and projects consume the same reviewed text. What moved, what stayed, and
why the render stays pure is recorded here: this page is the record of that
move, superseding the old vendor-snapshot design below only where it
describes vendoring (the "why not fetch at render time" property still
holds, restated for the new shape).

Kanon is itself one layer of a larger legal distribution chain (the canonical
picture is the [politeuma architecture diagram](https://github.com/politeuma/.github/blob/main/profile/diagram.md),
where law-map is the rulebook and this template is one adoption entry point
among others — any existing repository adopts the same rules through daimonion):

```text
open-law            law-map                 kanon      daimonion
world legislation   THE RULEBOOK            reviewed prose   rendered block
-> unified corpus -> obligation graph     -> AGENTS.md sections -> agent guide
                                              (any repo via      (this template:
                                               daimonion)        new Python projects)
```

`open-law` fetches statutes, `law-map` organizes them as machine-readable
technical obligations (statute, precedent, and guidance share one
functional-equivalence node), `kanon` renders the human- and agent-facing
prose, and `daimonion` (the linter) matches sections to a project and writes
them into its guide.

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
never sees the network at render time. The render emits only a declarative
config; prose enters the project later, through the linter, on the user's
machine.

## What moved, what stays

The split is content vs. wiring — the line is drawn at "does this text
reference a template flag":

| Moved to kanon + daimonion | Stays here |
| --- | --- |
| Section bodies (prose, triggers, `review_by` dates, sources) | `_shared/daimonion-when.jinja` — the single answer-to-condition derivation macro |
| The `when:`/audience mapping (which abstract condition selects which section: kanon's generated `MANIFEST.yml`) | The emitted `.daimonion.yml` (the project's declared conditions, in kanon's `when` vocabulary) |
| Section selection and block rendering (`daimonion agents-md --write`) | The empty marker pair in the generated `AGENTS.md` (`<!-- daimonion:ethics:begin -->` / `<!-- daimonion:ethics:end -->`) |
| Presence triggers and `check_ethics` matching | The composition manifest's `when:` list (the same macro, the public record `verify` reads) |
| The enforcement level's L1/L2 machinery that reads prose | The L2 `license-check` gate (pip-licenses; needs no prose) and the `daimonion-config` render predicate that holds the `when` list |

Kanon holds **flag-agnostic content**: each section is `sections/<tier>/<slug>.md`
(plain Markdown with YAML front matter — `id`, `version`, `status`, `when`,
`placement`, `triggers`, `sources`, `obligations`), and `sections/MANIFEST.yml`
is generated from that front matter by kanon's `tools/manifest.py` (never edited
by hand). It never names a template flag.
This repo maps its answers onto kanon's abstract vocabulary once, in
`_shared/daimonion-when.jinja`:

- `library` ← `project_type == 'library'`, `cli` ← `project_type == 'cli'`,
  `embedded` ← `project_type == 'micropython'`;
- `personal_data` / `face_recognition` / `medtech` ← the `domain_traits`
  answers; `scraping` ← `scraping_effective`; `oj_code` ← `oj_code`;
  `mcp` ← `mcp_effective`; `data_science` ← `data_science_layout` (not
  `ds_stack`); `kaggle` ← the kaggle workspace; `web_api` ← `web_api`;
  `commercial` ← the `distribution` answer;
- `jp`, `eu_market`, `ai_assisted` are not derivable from the questionnaire
  and are emitted as commented hints for the user to decide.

`always` sections apply without being listed and are never emitted.

## The sync contract (new shape)

```text
kanon (source of truth)                 this template              generated project
┌──────────────────────────┐         ┌─────────────────────┐         ┌────────────────────┐
│ sections/*.md             │  read   │ .daimonion.yml       │ linter  │ AGENTS.md            │
│  flag-agnostic prose      │ ──────► │ (declared when list) │ ──────► │ (filled marker block)│
│  MANIFEST.yml (generated  │   at    │ manifest when:       │ agents- │ `daimonion agents-md │
│   from front matter)      │ render  │ (same macro)         │ md      │  --write`            │
└──────────────────────────┘         └─────────────────────┘         └────────────────────┘
        ▲ own review cadence              ▲ render-pure                    ▲ prose enters here,
        (OWASP / FIPS / LE watch)         (no network)                     on the user's machine
```

There is no weekly vendor-sync PR anymore: nothing is vendored, so nothing
can drift. When kanon adds or revises a section, projects pick it up by
running `daimonion agents-md --write` — the same command that fills the
block the first time. The template's side of the contract is the derivation
macro plus two tests:

- `tests/test_daimonion_parity.py` proves the cutover changed *which leaf
  gets which section*: the old registry gates (frozen constant) and kanon's
  `applies()` over the derived `when` set select identical section-id sets
  for all 272 witness leaves.
- `tests/test_daimonion_config.py` renders contrasting presets and pins the
  `.daimonion.yml` `when` list, the manifest agreement, and the empty marker
  pair with no vendored prose.

Two guards close the gaps this shape leaves. The linter is **pinned**: the
`daimonion_spec` internal (`questions/_internal.yml`) names one daimonion
commit, and every generated `uvx --from` call uses it, so the prose a render
gets is fixed by the template tag rather than by daimonion's `main` (a
hash-pinned PyPI release replaces the git URL once daimonion is published).
An **empty block fails CI**: the post-gen fill only warns when offline, so
the generated `ci.yml` runs `daimonion agents-md --check` as a required job.

kanon's prose is Japanese-only. Until kanon ships English text, the default
`agents_md_language: en` renders English summaries of the selected
sections above the marker block from `_shared/ethics-summary-en.md.jinja`, a
translation of the pinned kanon revision's rule-summary lines (titles and
the three rules, not the full sections). `ja` keeps the Japanese block only.
`tests/test_daimonion_config.py` pins that partial's rows against kanon's
manifest and its selection against kanon's `applies()`.

## Versioning

A template release no longer ships a *known ethics text* — it ships a known
*derivation*. The prose a project carries is whatever kanon revision the
user's linter run rendered, recorded in the marker block's `kanon=` stamp.
`copier update` between two template tags therefore shows only derivation
changes (a condition added, removed, or re-derived); prose updates arrive
through the linter, reviewable as a normal `agents-md --write` diff.

## Status

The move is done: `_shared/ethics/`, its registry, and the appendix include
chain are deleted; `tools/ethics.py` and its MCP surface are deleted with
them. The remaining references:

- **Section ids**: `law-map` obligations link prose via `related_sections`
  ids of the form `<tier>-<slug>`, which resolve to
  `sections/<tier>/<slug>.md` in kanon (plain Markdown with YAML front
  matter; `MANIFEST.yml` is generated from it). Unchanged by this move.
- **`daimonion diff`** (no `--strict`) stays the generated project's
  `legal-check` task: it matches changed lines against the rendered block's
  triggers and only reports — the adoption-mode default, so the first week
  never goes red on findings. Pass `--strict` explicitly when a finding
  should fail the run.
- **Migration**: a project generated before the move carries appendix prose
  inline. Its next `daimonion agents-md --write` replaces the stale text
  with the linter-managed block; the `_src_path` legacy-URL migration
  (old `politeuma/daimonion` template URL → `politeuma/architekton-py`)
  is handled by the detect path before `copier update` runs.
