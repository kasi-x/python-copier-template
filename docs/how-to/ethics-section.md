# How to add an ethics / regional / operational rule

Field rules (a retired NTP server, a licensing drift, a jurisdiction's
data rules) are prose sections owned by
[law-map's guidance tree](https://github.com/politeuma/law-map/tree/main/guidance/sections)
(CC BY 4.0; the archived [kanon](https://github.com/politeuma/kanon) repo is
only a pointer there now).
This repo no longer vendors them: it maps questionnaire answers onto the
guidance abstract `when` conditions in `_shared/daimonion-when.jinja`, emits the
result as the generated project's `.daimonion.yml`, and leaves an empty
marker block in `AGENTS.md` for `daimonion agents-md --write` to fill. The
split is content vs. wiring: guidance is responsible for what a section says
and whether its sources are still right; this repo decides which abstract
conditions a generated project declares. Who decides what goes in the
generated projects is stated in
[GOVERNANCE.md](https://github.com/politeuma/architekton-py/blob/main/GOVERNANCE.md):
contributors draft and research; the maintainer owns the defaults and
the promotions. The architecture is explained in
[Ethics Content Lives in Kanon](../explanations/ethics-external.md).

## Write or correct the section upstream

Section text — new sections, factual corrections, dead source links —
goes to law-map's guidance tree as a pull request, following its
`CONTRIBUTING.md`. There is nothing to vendor here: when the guidance change
is merged, projects pick it up by running `daimonion agents-md --write`.
Obligation-level changes (which statute requires
what) go through law-map's
[Legal RFC](https://github.com/politeuma/law-map/issues/new?template=legal_rfc.yml).

Write the rule as a one-line summary plus a link to the primary source;
never paste statutes or license texts verbatim, and keep the
not-legal-advice footer. Name concrete shapes in 禁止パターン and
copy-pasteable settings in 推奨設定, not slogans — back the rule with at
least one bad/good code-or-config pair, the way the active sections do.
Fill the `en:` front-matter block (title, summary, prohibited) alongside the
Japanese prose — daimonion renders one or the other into the marker block
depending on the project's `agents_md_language` (`en` renders `en:`, `ja`
renders the Japanese prose), so a section without an `en:` block falls back
to Japanese even in English projects.
Keep snippets free of `{{ }}` / `{% %}`: the section file is plain Markdown
with YAML front matter (never rendered as jinja), but double braces in new
template-adjacent docs would still be evaluated, not printed.

## Declare the condition here

If the new section's guidance `when` is one this template never derives
(a new abstract condition, or a new answer that implies an existing one),
extend the derivation macro `_shared/daimonion-when.jinja` once — both the
generated `.daimonion.yml` and the composition manifest's `when:` list
interpolate that macro, so one edit serves both. `jp`, `eu_market` and
`ai_assisted` are deliberately not derived: the config emits them as
commented hints for the user to decide.

Then check the result:

```shell
uv run --locked pytest tests/test_daimonion_parity.py tests/test_daimonion_config.py
```

The guards pin: the parity test (every witness leaf's derived `when` set
selects the same guidance sections the old gates did), the config test (the
`when` list order, provenance comments, manifest agreement, and the empty
marker pair with no vendored prose), and the `daimonion-config` predicate
in `tests/test_render_invariants.py` (every leaf class carrying a condition
names it in `tests/matrix/invariants.yml`).

## Enforcement levels

| Level | Meaning | Consumer |
| --- | --- | --- |
| `L0` | the section reaches a reader | the linter-rendered AGENTS.md block |
| `L2` | something fails the build | e.g. the `license-check` task in generated CI (pip-licenses; needs no prose) |

## Market-triggered rules: the regions table

Some rules have no questionnaire channel at all: whether Japan's
third-party-transmission disclosure duty or the EU Accessibility Act
applies depends on the markets a project ships to, and a
`target_markets` question would add a leaf-space dimension for two
sections. Those rules do not derive a `when` condition;
instead the generated project ships `ethics/regions.yml` (web_api
renders only — both current rules are frontend/UI duties), a per-rule
summary table whose `serves:` entries point at the guidance section URLs.
The AGENTS.md block links to the file rather than including the sections.

## Keeping sections alive

Every guidance section's `review_by` is the date its 制度変更ウォッチ items
must be re-checked by. That cadence lives upstream now — re-checks land as
law-map pull requests, not template edits.
