# architekton/ — the tooling around the template

You rarely need to open this directory to change the template: questions
live in `questions/`, generated files in `template/` and `partials/`. Start
with `task where -- <setting>`, which tells you which of those files to edit.

This directory holds the CLI that renders the template, plus the
machinery that proves every combination of answers still renders. It is
grouped by job below. (`tests/test_tool_layers.py` keeps this map complete:
a module missing here fails the test.)

## Commands people and agents call

| Module | What it does |
| --- | --- |
| `cli.py` | `architekton-py new` and the subcommands below it |
| `where.py` | Every file a question touches: where to edit to change it |
| `explain.py` | Why a preset or an answer has its value, from the questions' own help text |
| `suggest.py` | Propose presets and answers for stated requirements, then validate them |
| `answers_for.py` | The reverse direction: name the features, get the answers that produce them |
| `scaffold.py` | Generate the skeleton of a new question, opt-in layer or preset |
| `verify.py` | Check a generated project's composition contract |

## Reading the questionnaire

| Module | What it does |
| --- | --- |
| `questionnaire.py` | `copier.yml` + `questions/*.yml` as data, in ask order |
| `file_gates.py` | `questions/99-files.yml`, the table of which files exist for which answers |
| `when_model.py` | The `when:` expressions, and the Jinja identifier scanner everything shares |
| `question_graph.py` | What reads what, and where a new question may be placed |
| `answers.py` | The project details every test render starts from |
| `render_inputs.py` | Fingerprints of the inputs a render depends on |

## Proving that every combination renders

| Module | What it does |
| --- | --- |
| `z3_witnesses.py` | Enumerate the answer combinations ("witness leaves") with Z3 |
| `batch.py` | Render a batch of answer sets and judge each result |
| `invariants.py` | The file-set and content rules each render must satisfy |
| `gen_invariants.py` | Prototype that derives invariant rows from the questionnaire |
| `predicates.py` | Classify every condition in questions and templates over all leaves |
| `render_delta.py` | Prove which leaves a working-tree change can affect (`task verify-delta`) |
| `update_rehearsal.py` | Replay `copier update` for every leaf, release tag to HEAD |
| `support_ledger.py` | Read `tests/matrix/support.yml`, the declared support tiers |

## Adopting the template into an existing project

| Module | What it does |
| --- | --- |
| `detect.py` | What a target project already has, and which mode fits |
| `adopt.py` | Entry point: adopt reversibly |
| `adopt_cli.py` | Command line: plan, apply, recover |
| `adopt_run.py` | The transaction: plan, render, verify, merge or roll back |
| `adopt_revision.py` | Which revision and answers to expand |
| `adopt_merge.py` | Add what the template generated to what already exists |
| `adopt_confirm.py` | Show the plan, ask, apply or step back |
| `adopt_tree.py` | Snapshot, verify, roll back the tree |
| `adopt_journal.py` | The crash journal behind `--recover` |
| `adopt_crash.py` | Crash points and the rollback signal handler |
| `adopt_report.py` | Human and machine reports of a run |
| `adopt_types.py` | Shared errors, records and constants |
| `file_merge.py` | Append-only merge for text files |
| `pyproject_merge.py` | Merge dependencies and tool config into an existing `pyproject.toml` |
| `git.py` | The git runner the drivers share |

## Generated documentation

| Module | What it does |
| --- | --- |
| `gen_docs.py` | Regenerate the questionnaire-derived blocks in `docs/` (`--write`), or check them for drift |
| `gen_docs_model.py` | The model behind those blocks: paths, vocabulary, groupings |
| `gen_docs_sections.py` | The catalogue blocks: project types, areas, features |
| `gen_docs_prose.py` | Help text and `when` conditions as prose |
| `gen_docs_graph.py` | The ask order as a mermaid graph |
| `gen_docs_blocks.py` | Block markers, drift check and rewrite |
| `docs_i18n.py` | Stage a translated docs site |
| `gen_zensical_ja.py` | Generate `zensical.ja.toml` for the Japanese site |

## MCP server (the same tools, for agents)

| Module | What it does |
| --- | --- |
| `mcp_server.py` | Entry point (`task mcp`) |
| `mcp_shared.py` | The server instance and path conventions |
| `mcp_questionnaire.py` | Ask order, presets, explanations, proposals |
| `mcp_render.py` | The single render entry point and tree comparison |
| `mcp_render_loop.py` | Render, diff, lint, run a batch |
| `mcp_witness.py` | Leaves, inverse lookup, tier runners |
| `mcp_project.py` | Project inspection and adoption |

## Maintenance scripts (run on their own, import nothing from here)

| Module | What it does |
| --- | --- |
| `hygiene.py` | Merge markers, trailing newlines, YAML, file sizes (`task hygiene`) |
| `check_upstream.py` | Compare pinned versions against their upstreams |
| `check_upstream_fork.py` | New commits on the upstream template's main |
| `check_questionnaire_diff.py` | Guard against changes that break `copier update` |
| `generate_license_template.py` | Regenerate LICENSE templates from `licenses/` |
