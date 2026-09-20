# Generating a project non-interactively

For CI or scripted generation, answer the questionnaire from a file instead of a
terminal. The [Create a new project](../tutorials/create-new.md) tutorial covers
the shipped CLI's `--preset <name>`, which is the shortest non-interactive form;
this page is the copier-level reference.

Every question has a default, so a minimal answers file plus `--defaults` fully
determines the project; anything in the file overrides that default:

```bash
# Create answers file
cat > answers.yml << 'EOF'
---
project_type: library
package_name: my_package
description: My awesome package
git_platform: github.com
github_org: my-org
EOF

# Generate project
uvx copier copy --trust --defaults \
    --data-file answers.yml /path/to/my-project
```

Notes:

- `--defaults` answers every question it would ask with its default, so it
  never prompts. A value from `--data-file` counts as answered, which also
  drives the `when` gating of the follow-up questions (e.g.
  `use_recommended_integrations: false` reveals the integration details and
  `--defaults` fills them in).
- Values supplied for a question whose `when` is false (e.g. `docs_type`
  while `use_recommended_docs` is true) are still validated against the
  choices — pass the gate answer too, or drop the unused value.
- `--answers-file` must be a path **relative to the destination directory**
  (copier requirement), e.g. `.copier-answers.yml`.

## Tell the template what you want

The inverse question comes up just as often: for the features you want, which
answers produce them? The 248 witness leaves in `tests/matrix/witnesses.jsonl`
each carry a full answer set whose render context copier has already computed,
so "features -> answers" is an exact filter over verified configurations, not
a guess — `tools/answers_for.py` is that filter:

```bash
# Name the features as constraints over any question or derived internal
uv run --locked python tools/answers_for.py \
    --require use_gpu_effective=true --require kaggle=true

# ...and prove the top match by rendering it: every constraint is checked
# against the rendered tree (context pass over the render's recorded answers,
# plus the artifacts the internals gate, e.g. Dockerfile.gpu)
uv run --locked python tools/answers_for.py \
    --require zensical=true --require web_api=true --render --keep
```

Each constraint is `name`, `name=value`, `-name` or `name!=value`. A name may
be an asked question (`docker`, `docs_type`, `license`, ...) or a derived
internal (`mcp_effective`, `use_gpu_effective`, `sphinx`,
`license_effective`, ...); an unknown name is rejected with the closest real
names. Every match is reported with its full answers as a `--data-file`-ready
YAML block and the artifacts its class ships; when nothing matches, the tool
names the constraint that eliminated the most leaves and the nearest leaf
with what it misses — the match is exact over the declared leaf space, so a
combination no leaf carries (`docker=true`, say: every leaf keeps that
question's default) is reported as such, not guessed. `--json` puts the same
payload on stdout, `task answers-for` is the task wrapper, and the MCP server
exposes it as `recommend_answers`
(see [Drive the template's tools over MCP](../how-to/mcp-tools.md)).

## Troubleshooting

- Exit status 4, nothing generated → you omitted `--trust`
- "Question X is required" → add X to your answers file (see
  `questions/*.yml` for every question and its default)
- "Invalid choice for X" → check the valid choices in `questions/*.yml`

For a whole batch of requests, judged and reported as machine-readable results,
see [Run a batch of generation requests](../how-to/batch.md).
