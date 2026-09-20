# How to add an ethics / regional / operational rule

Field rules (a retired NTP server, a licensing drift, a jurisdiction's
data rules) live as sections under `_shared/ethics/`, registered in its
`REGISTRY.yml`. The design goal: a new rule must not move the
questionnaire, the witness leaf space, or anyone's render — it
accumulates as documentation first and is promoted only when a
distribution bundle forms. Who decides what goes in the generated
projects is stated in
[GOVERNANCE.md](https://github.com/kasi-x/python-copier-template/blob/main/GOVERNANCE.md):
contributors draft and research; the maintainer owns the defaults and
the promotions. The mechanics behind this page are explained in
[Authoring Template Sources](../explanations/template-dev.md)
("Accumulate ethics/regional/operational rules as sections first").

## Add a rule as a draft

A draft is documentation only: nothing includes it, no render changes,
and every guard accepts it without any other file being touched.

1. Copy `_shared/ethics/_template.md.jinja` to the matching bundle
   directory — `baseline/` (rules any project kind can trip),
   `region/` (a jurisdiction's rules), `sector/` (an industry's),
   `domain/` (a purpose the questionnaire's `domain_traits` select) —
   as `<id>.md.jinja`.
2. Fill in every field. The section opens with the matching header and a
   scope blockquote; the first five lines are the LLM/human entry point:
   if none of the triggers apply, the reader skips the section.
3. Register one row in `_shared/ethics/REGISTRY.yml` with
   `status: draft` and `rendered_from: []`. Keep the id, version
   (`YYYY-MM-DD.rev`), and status in agreement with the file header —
   the guards check both directions.
4. Check your work:

   ```shell
   uv run --locked pytest tests/test_ethics_registry.py
   ```

   The guards pin: row shape (id, version, dates, primary sources,
   scope, scale, audience, enforcement), header agreement, the body
   naming its scale and every audience entry, a documented presence
   trigger (`設定側トリガー`) that compiles and stays unique across
   rows, and — for drafts — that no template file includes you.

Write the rule as a one-line summary plus a link to the primary source;
never paste statutes or license texts verbatim, and keep the
not-legal-advice footer. Name concrete shapes in 禁止パターン and
copy-pasteable settings in 推奨設定, not slogans.

## Promote a draft to active

A draft promotes only when a bundle forms: three sections sharing one
distribution condition, or one section needing a distinct code/test gate
(enforcement L2). A promotion changes generated renders, so it wires the
verification stack as it goes — each step below has a check that catches
its omission.

| # | Touchpoint | What catches the omission |
| --- | --- | --- |
| 1 | Registry row: bump `version`, set `status: active`, name the parent(s) in `rendered_from` (usually `template/{% if agents_md_effective %}AGENTS.md{% endif %}.jinja`) | `test_ethics_registry.py`: a distributed row must name parents that actually reference the file |
| 2 | The include, on one line, in the parent's include chain, gated on existing answers (never a new question) | the `ethics-appendix` predicate in `tests/test_render_invariants.py` — it fails a leaf missing the section *and* a leaf shipping it uninvited |
| 3 | The same gate as a named trait helper + an `ETHICS_SECTIONS` entry (h1 marker + selector) | the docstring rule in that file: one spelling per trait, no inline disjunctions to drift |
| 4 | `tests/matrix/invariants.yml`: content pairs `[AGENTS.md, "<h1 marker>"]` on every row whose leaves select the section | those rows' leaves fail the content predicate |
| 5 | `task witness` + the fast tier | the ledger freshness and content checks |

The audience in the registry row is the human-readable word for the gate
(`iot` may map to `micropython`, as `baseline-pki-chain` does); the gate
and the selector spell the mapping, the row keeps the word.

## Enforcement levels

| Level | Meaning | Consumer |
| --- | --- | --- |
| `L0` | the section reaches a reader | the generated AGENTS.md appendix, the MCP tools |
| `L1` | the presence trigger is machine-readable | `tools/ethics.py match()`, the MCP `check_ethics` tool, `template://ethics` |
| `L2` | something fails the build | e.g. `baseline-license-drift`'s `license-check` task in generated CI |

New sections start at `L0`. A `L1` lift is free — the trigger span is
already parsed for every row; drafts warn through `check_ethics` even
while they ship nowhere. A `L2` lift needs a real gate with an offline
contract (see how `license-check` stays out of `type-check`/`check`).

## Structured data: the `lang/` dictionaries

Rules whose substance is a table (protection terms per jurisdiction,
per-country filing deadlines) keep the prose summary in the section and
the data in `_shared/ethics/lang/<name>.yml` — see
`copyright-terms.yml`, the first one. The table names the section it
serves (`serves:`), matches its `review_by`, carries primary sources per
row, and the section references it back; a guard in
`tests/test_ethics_registry.py` holds the two together.

## Keeping sections alive

Every row's `review_by` is the date its 制度変更ウォッチ items must be
re-checked by. A passed date fails the registry test, so CI reddens
until someone re-checks the primary sources, updates the body, and bumps
the row's `version` and `review_by` (or supersedes the row via
`superseded_by`). The re-check is a good first contribution; the bump is
a one-line registry edit.
