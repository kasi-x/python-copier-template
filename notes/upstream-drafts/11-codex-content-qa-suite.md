Title: Codex-side content QA suite — the checks that live with the sections, not with the template

## Context

`good-future-codex` (the planned external home of `_shared/ethics/` section
content — see `docs/explanations/ethics-external.md`) holds flag-agnostic
prose. Today the template repo's `tests/test_ethics_registry.py` carries two
classes of assertions: *contract* checks (row shape, gate safety, appendix
freshness, draft isolation — they pin the wiring this repo owns) and
*content* checks (prose conventions the codex must hold regardless of who
vendors it). This note drafts the second class as the codex repo's own
suite, so the template's copy can slim to the contract surface once the
codex exists.

## Proposed codex QA suite

Each item names the assertion and the template-side test it replaces or
mirrors. All run offline; none needs copier.

| Check | Source assertion (tests/test_ethics_registry.py) |
| --- | --- |
| Frontmatter/header agreement: `{# ethics: id=... version=... status=... #}` matches the codex's own MANIFEST.yml row | `test_section_headers_agree_with_registry` (registry row → codex manifest row) |
| Body names its scale (`国内問題`/`地域問題`/`世界問題`) and every audience token | `test_section_bodies_repeat_scale_and_audience` |
| Every section documents a parseable `(?i)` presence trigger in its 運用チェック, unique across rows | `test_every_row_documents_a_parseable_presence_trigger` |
| No `{{ }}`/`{% %}` in prose bodies — flag-agnostic content must not carry copier context | `test_draft_sections_are_not_distributed` (the `{{` assertion), plus the ethics-external.md rule |
| ```python blocks are ruff-format-clean at 88 and 120 | `test_python_examples_are_ruff_format_clean` |
| `review_by` not in the past; `version` bumped when body changes | `test_no_review_date_has_passed` (codex-side: version-vs-body diff on PR) |
| Retired-identifier denylist entries are named in the section that owns them | `test_kyushu_ntp_denylist_and_detector` |
| `lang/` tables: `serves:` names a registered section, `review_by` matches, per-row sources are https | `test_copyright_terms_table_matches_its_section` |

## What stays in the template (contract surface only)

Row shape/required keys, `rendered_from` parent wiring, gate safety and
boundness, generated-appendix freshness, draft isolation, the regions-table
`serves:` binding, and the per-leaf `ethics-appendix` predicate. These pin
the vendored snapshot's wiring; the codex cannot see them.

## Expected effect

The template's registry test file drops ~150 lines of prose-shape asserts;
the codex gains the same checks keyed to its own MANIFEST.yml. A content
edit that breaks a prose rule fails in the codex repo before the vendor PR
opens, not in the template's CI afterward.
