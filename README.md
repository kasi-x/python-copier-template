[![CI](https://github.com/kasi-x/python-copier-template/actions/workflows/ci.yml/badge.svg)](https://github.com/kasi-x/python-copier-template/actions/workflows/ci.yml) [![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/kasi-x/python-copier-template/badge)](https://scorecard.dev/viewer/?uri=github.com/kasi-x/python-copier-template) [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# python-copier-template

## TL;DR
Prerequisites: [uv](https://docs.astral.sh/uv) (its `uvx` shim runs copier) and [git](https://git-scm.com). Both commands below expand this fork's **newest release tag**, so no revision flag is needed:
```shell
python-copier-template new my-project --preset library   # the shipped CLI, from a clone of this repo: picks the release, renders, records the answers
uvx copier copy --trust https://github.com/kasi-x/python-copier-template.git my-project   # or drive copier directly
```

An opinionated [copier](https://copier.readthedocs.io) template for Python
projects: create a new project from it, update existing projects in line with
it, and keep them in sync as it changes. One questionnaire covers libraries,
web APIs, CLIs, data-science pipelines, competitive programming, ROS 2 packages
and MicroPython firmware — and its logic is machine-verified (Z3 satisfiability
over every question path) rather than only documented.

## What you get

Each area of the questionnaire first asks "use the recommended settings?"
(default: yes), so the recommended path is usually a single keystroke:

- **Eight project types** — `library`, `web_api`, `cli`, `data_science`,
  `online_judge`, `script`, `ros2`, `micropython`, each with its own layout,
  CI and docs.
- **A toolchain of your choice** — uv, pixi or poetry; just, Task, poethepoet,
  Make, pyinvoke, duty or pixi's native tasks; zensical, Sphinx or great-docs.
- **Quality gates** — ruff (ALL rules), basedpyright + pyrefly, typos, vulture,
  deptry, pip-audit, pytest + coverage + hypothesis, hardened CI with pinned
  actions, SECURITY.md and OpenSSF Scorecard.
- **Opt-in layers** — the data-science layout, a FastAPI service, MCP servers,
  polite web scraping, CTF tooling, cloud providers and Sentry.

The [feature catalogue](docs/reference/features.md) walks through all of it,
[the questionnaire reference](docs/reference/questionnaire.md) lists every
question, and the [support tiers reference](docs/reference/support.md) says
which combinations CI executes end to end. For the comparison with the upstream
template and the alternatives, see
[Vision & Positioning](docs/explanations/vision.md); the template in action is
the [example project](https://github.com/kasi-x/python-copier-template-example).

## Create a new project

The shipped CLI is the recommended path. It runs from a clone of this
repository, picks the release to expand, decides between creating a project and
adopting an existing one, and reports the files the target already has:

```shell
git clone https://github.com/kasi-x/python-copier-template.git
uv run --project python-copier-template python-copier-template new my-project --preset library
```

`--preset library` answers the one question that defines the project family
(`cli`, `web-api`, `data-science`, `ros2`, `micropython` and
`online-judge-atcoder` also exist); drop it and copier asks the
[whole questionnaire](docs/reference/questionnaire.md) instead, which needs a
terminal.

Without a preset you can also drive copier directly, which is all the CLI
wraps. `--trust` is required: the template runs post-generation tasks (the
adoption report, the next-steps hint and the REUSE `LICENSES/` copy), and
without it copier generates nothing and exits with status 4:

```shell
git init --initial-branch=main /path/to/my-project
uvx copier copy --trust https://github.com/kasi-x/python-copier-template.git /path/to/my-project
```

Both paths expand this fork's newest release tag;
[Create a new project](docs/tutorials/create-new.md) covers the flags, the
presets, adoption and pinning an exact release, and
[generating a project non-interactively](docs/reference/non-interactive.md)
covers `--defaults` with an answers file for CI.

## Everyday commands

The generated project drives lint, type-check, test and docs through the task
runner you chose (`just` by default; `task`, `poe`, `invoke`, `duty`, `make` or
pixi's native tasks are the alternatives — one shared task definition, invoked
by CI too). Swap `task` for your runner; the task names are the same:

```shell
task lint        # ruff format --check + ruff check (check-only)
task fix         # ruff --fix + format, plus typos -w at the recommended strictness
task type-check  # basedpyright + pyrefly, vulture, deptry, typos
task test        # pytest, with coverage at the recommended strictness
task docs        # build the documentation site
task check       # lint + type-check + test
```

`task audit` and `task license-check` need the network and so stay out of
`check`.

## Where to go next

- **[Documentation site](https://kasi-x.github.io/python-copier-template)** — the full docs, in
  [tutorials](docs/tutorials.md), [how-to guides](docs/how-to.md),
  [explanations](docs/explanations.md) and [reference](docs/reference.md),
  starting from the [docs index](docs/index.md).
- **New here** — the [installation tutorial](docs/tutorials/installation.md) and
  [create a new project](docs/tutorials/create-new.md).
- **Already have a repo** — [adopt this template into it](docs/tutorials/adopt-existing.md), or
  [update an existing project](docs/how-to/update-template.md) that already uses it.
- **Template internals** — [authoring template sources](docs/explanations/template-dev.md),
  the [structure](docs/explanations/structure.md) and
  [how a change is verified](docs/explanations/verification.md).

## License, contributing and releases

Licensed under [Apache-2.0](LICENSE). This repository is the template's own
source (not a generated project): [source](https://github.com/kasi-x/python-copier-template) ·
[docs site](https://kasi-x.github.io/python-copier-template) ·
[releases](https://github.com/kasi-x/python-copier-template/releases), whose
notes are generated by [git-cliff](https://git-cliff.org) from the tag's
conventional commits ([CHANGELOG.md](CHANGELOG.md)). Contributions are welcome
— see [CONTRIBUTING.md](.github/CONTRIBUTING.md), the
[contributing how-to](docs/how-to/contribute.md) and
[GOVERNANCE.md](GOVERNANCE.md); report vulnerabilities as described in
[SECURITY.md](SECURITY.md).
