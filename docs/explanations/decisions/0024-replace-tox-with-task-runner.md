# 24. Replace tox with a per-project task runner

Date: 2026-08-31

## Status

Accepted (supersedes [8. Use tox and pre-commit](./0008-use-tox.md))

## Context

ADR 8 introduced tox as the job orchestrator that runs the same checks
locally as CI (`tox -e pre-commit|type-checking|tests|docs`). This served the
template well, but:

- tox's headline feature — running the same test suite under multiple Python
  versions — was never used here: version testing always happened in the CI
  matrix (`_test.yml` receives `python-version` from the caller).
- The template's strictness axes (`recommended`/`full` vs `none`/`basic`)
  made the tox env set conditional, which leaked tox-isms into the copier
  questions and CI.
- Users increasingly prefer a task runner that matches their language/ecosystem
  habits: Task, Just, poethepoet, Make — and pixi has its own native tasks.
- uv already covers the isolated-environment role (`uv run --locked`) without
  a second tool.

## Decision

Replace tox with a **per-project task runner**, selected at generation time:

- `task_runner` question (Task / Just / poethepoet / Make) for uv/poetry,
  plus pixi's native tasks when `package_manager == pixi`
  (`task_runner_pixi`; poethepoet is not offered there).
- The canonical task list (lint / type-check / test / docs / docs-serve /
  docs-linkcheck / competition ML pipeline / data-science extras) lives once
  in `_tasks.jinja` at the template repo root and is imported
  (`{% raw %}{% import ... with context %}{% endraw %}`) by each output:
  `Taskfile.yml`, `justfile`, `Makefile`, `[tool.poe.tasks]`,
  `[tool.pixi.feature.dev.tasks]`.
- CI invokes the *same* tasks through a new `_tasks.yml` reusable workflow
  that takes `task_runner` + `task` inputs and installs the runner's binary
  when needed (arduino/setup-task, extractions/setup-just). `_test.yml` and
  `_docs.yml` gained the same input.

## Consequences

- One task definition is shared by local dev, GitHub Actions, and GitLab CI;
  drift between them is no longer possible.
- `tox-uv` and `[tool.tox]` are gone from both the template and this repo;
  this repo now dogfoods a `Taskfile.yml` and its CI uses `task_runner: task`.
- Local multi-version test loops (`tox -p` across Python versions) are no
  longer one command; use `uv run --python <ver> pytest` per version or the
  CI matrix. This was already the case before — tox envs were single-version.
- Renovate is configured to leave the two runner-setup actions
  (`arduino/setup-task`, `extractions/setup-just`) on template-managed pins.
