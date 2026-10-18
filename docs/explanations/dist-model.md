# The dist model: render once, distribute flat

The template has two audiences with different needs:

- **consumers** want a project — the rendered output. Asking them to run
  copier to get it makes them pay the questionnaire's full complexity
  (17 question files, every `{% if %}` in every template) for the four
  knobs they actually change.
- **maintainers** want the questionnaire — the sources a change flows
  through.

`dist/` is the consumers' artifact: every `presets/*.yml` rendered flat
(699 files, ~9 s, `task static`), published to the **`dist` branch** on
every push to `main` and uploaded as release assets on every tag.
`bootstrap.sh` on that branch re-attaches the four knobs that genuinely
vary (preset, project name, package name, log library): it fetches a preset
tree, rewrites the placeholder names, and swaps in
`variants/logging_setup/<preset>/<lib>.py` — each variant rendered by the
same `gen_static.py` run, so a choice changes real file content, not just a
name.

Consumers who need the full questionnaire still render locally with
copier — the same `batch.render` call produced the distributed bytes, so
the two paths cannot drift (`gen_static.py --check` is the drift gate).

## What stays dynamic

Ask-time questions can only be generated: `partial questions` (shared
fragments like `log_library`) resolve at question time, before any file
exists. Those live under `meta/questionnaire/` — `tree.yml` records which
generated `questions/NN-*.yml` each source produces and where each
variant's follow-ups plug in, `areas/` and `fragments/` hold the sources,
and `architekton/gen_questions.py` expands the `# !fragment` / `# !catalog`
markers. Everything *below* the question layer — the rendered tree itself —
is what gets distributed flat.

## Which files exist lives in the path names

There is no existence table. `template/{% if web_api %}app{% endif %}/`
means the `app/` directory renders only for web_api; a segment rendering to
"" is skipped by copier, so no `_exclude` list exists anywhere. Computed
names (`{{ pkg_dir }}`, `{% if is_uv %}uv.lock{% elif is_pixi %}pixi.lock{%
endif %}`) use the same spelling. `architekton/file_gates.py` reads the
tree back into the gate list that `detect`, `predicates` and `where`
consume, and `tests/test_file_gates.py` enforces the convention (every
`{% %}` segment is a well-formed `if`/`endif` gate).

## Where a change lives

| Want to change | Edit |
| --- | --- |
| a question's text / order | `meta/questionnaire/areas/<NN>-*.yml` (generated areas) or `questions/NN-*.yml` (hand-written) |
| a shared question | `meta/questionnaire/fragments/` — spliced via `# !fragment` |
| a variant's facts (distro, version floor) | `meta/catalog.yml` — questions + macros + upstream checks regenerate from it |
| whether a file renders | the `{% if %}` in its `template/` name |
| a variant's pyproject | `partials/types/<variant>/pyproject.toml.jinja` (dispatcher: `template/{% if render_pyproject %}pyproject.toml{% endif %}.jinja`) |
| what `dist` ships | `architekton/gen_static.py` + `.github/workflows/_dist_branch.yml` |
