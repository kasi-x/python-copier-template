Title: Regions table — the codex-side schema for market-triggered rules

## Context

Some ethics rules gate on *where the product ships*, not the project kind —
Japan's third-party-transmission disclosure duty, the EU Accessibility Act.
Asking "which markets?" in the questionnaire would add a leaf-space
dimension for a handful of sections, so the template instead ships
`ethics/regions.yml` (web_api renders): a per-rule summary table whose
`serves:` entries point back at the section draft it abbreviates. This note
specifies the table's codex-facing half, so a future split leaves the schema
stable and consumer-neutral.

## Schema (version 1)

```yaml
version: 1
review_by: YYYY-MM-DD          # earliest review_by among the rows served
rules:
  - id: region-eu-eaa          # registry/manifest id, kebab-case
    serves: _shared/ethics/region/eu-eaa.md.jinja   # the full section draft
    jurisdiction: eu
    statute: Directive (EU) 2019/882
    applies_to: consumer-facing e-commerce / e-books / banking UI in the EU
    duties: [list, of, short, obligation, strings]
    triggers: [accessibility, wcag, a11y]          # human-scan keywords
    sources: [https://...]                          # primary sources only
```

## Contract rules

- `serves` must name a section file registered in the codex's manifest; the
  template additionally requires the served row's `file:` to match exactly
  (no renamed-file drift).
- `review_by` is `min(served rows' review_by)` — the first rule needing
  re-check sets the table's horizon.
- `sources` are https primary sources; secondary commentary stays in the
  section body, not the table.
- `duties`/`triggers` are lists; `id` matches `^[a-z0-9]+(-[a-z0-9]+)*$`.
- The table is a *reference*, not distribution: it names the section file
  but embeds none of its body. That lexical distinction is what lets the
  draft-isolation check exempt `serves:` lines.

## Consumer obligations (template side)

- Ship the table only where the rendered project could plausibly serve the
  market (`web_api` today); link it from AGENTS.md so the channel cannot
  drop silently.
- Pin `serves:`-vs-registry agreement in the vendor-side test suite.
