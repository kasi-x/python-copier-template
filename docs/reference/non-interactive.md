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

## Troubleshooting

- Exit status 4, nothing generated → you omitted `--trust`
- "Question X is required" → add X to your answers file (see
  `questions/*.yml` for every question and its default)
- "Invalid choice for X" → check the valid choices in `questions/*.yml`

For a whole batch of requests, judged and reported as machine-readable results,
see [Run a batch of generation requests](../how-to/batch.md).
