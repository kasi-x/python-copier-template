# Propose a configuration from requirements

`architekton-py suggest` turns "what the project needs" into a preset candidate,
then checks the full answer set before anything is generated. The model (or
you) proposes; the questionnaire's own machinery disposes:

```shell
architekton-py suggest "internal API, postgres, github actions"  # preset candidates with reasons
architekton-py suggest --validate answers.yml                    # check a drafted answer set (exit 2 when rejected)
```

The flow the command enforces:

1. <lt-m v="**"/>Propose from requirements.<lt-m v="**"/> `suggest` ranks the `presets/*.yml`
   families by keyword match — no model, no render, no network. Each match
   names its score, its human reasons, and the answers it pins.
2. <lt-m v="**"/>Draft the full answer set.<lt-m v="**"/> Write every answer the render needs (the
   preset's pins plus the rest of the questionnaire — see
   <lt-m v="["/>Questionnaire<lt-m v="](../reference/questionnaire.md)"/> for the full list).
3. <lt-m v="**"/>Validate before generating.<lt-m v="**"/> `--validate` runs the draft through
   copier's own questionnaire pass and rejects unknown questions, values
   outside the choices, answers to questions that would never be asked, and
   layer includes on a base that cannot carry them, with machine-readable
   `{question, reason}` pairs. Only an approved set reaches `architekton-py new
   --preset` (or `--data-file`).

What is refused, and why:

- <lt-m v="**"/>Unknown questions<lt-m v="**"/> — copier would silently render the default instead,
  so a typo (`unknown_q`) fails rather than generating the wrong project.
- <lt-m v="**"/>Values outside the choices<lt-m v="**"/> — copier's own choice verdict, including
  the templated `oj_kind` choices and the `domain_traits` multiselect.
- <lt-m v="**"/>Answers to unasked questions<lt-m v="**"/> — a forced value copier keeps but the
  render discards (e.g. `include_scraping: true` on a `web_api` base).
- <lt-m v="**"/>Layers on non-combinable bases<lt-m v="**"/> — `include_web_api: true` on `ros2`
  trips the `combinable` / `has_*` guard in `questions/_combo.yml`.
- <lt-m v="**"/>Derived internals<lt-m v="**"/> — `combinable`, `has_web_api` and friends are
  computed at render time and must not be answered.

A combination no `support.yml` row promises is a warning, not a rejection:
it renders, but no tier is promised (see
<lt-m v="["/>Support<lt-m v="](../reference/support.md)"/>).

The same gate is available to agents over MCP as `suggest_config`
(requirement words in, candidates out) and `validate_answers` (candidate
answers in, `{"ok", "errors"}` out; see [Use the template's own MCP
server](mcp-tools.md)). The logic lives in `architekton/suggest.py`; the CLI
subcommand and the MCP tools are thin shells over it. The questionnaire
itself is untouched — the no-model CLI/questionnaire path keeps working
exactly as before.

## Related

- <lt-m v="["/>Presets<lt-m v="](../reference/presets.md)"/> — the ready-made answer files `suggest` ranks.
- <lt-m v="["/>Questionnaire<lt-m v="](../reference/questionnaire.md)"/> — the full question list with gates.
- <lt-m v="["/>Support<lt-m v="](../reference/support.md)"/> — the declared tiers the validation quotes.
- <lt-m v="["/>Explain a Preset or an Answer<lt-m v="](explain.md)"/> — why one choice, and what changes otherwise.
