# Run linting

Code linting and format checks are handled by [ruff](https://docs.astral.sh/ruff) through the task runner's `lint` and `fix` tasks.

## Running the checks

The `lint` task is check-only — `ruff format --check .` followed by `ruff check .` — so it changes nothing and also works outside a git repository. You can run it on all files with this command:

```
$ task lint
```

(or `just lint`, `poe lint`, ... depending on your task runner).

Repository hygiene checks are not run locally: they run in CI via the repository hygiene workflow, which covers secret scanning (gitleaks), workflow linting (actionlint), YAML validity, missing end-of-file newlines, conflict markers, oversized files, conventional commit messages, REUSE lint and CITATION.cff validation.

## Fixing issues

The typical workflow is:

- Make a code change
- Run the `fix` task (`task fix` or `just fix`), which runs `ruff check --fix .` then `ruff format .`
- If anything changes it will be left in your working copy
- Review the changes, then `git add` and commit them

Run `fix` before committing so the `lint` task and CI stay green.

## VSCode support

The `.vscode/settings.json` will run ruff formatters on save, but will not try to auto-fix as that does things like removing unused imports which is too intrusive while editing.
