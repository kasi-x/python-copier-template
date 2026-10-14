[![CI](https://github.com/ConstitutiveTemplates/architekton-py/actions/workflows/ci.yml/badge.svg)](https://github.com/ConstitutiveTemplates/architekton-py/actions/workflows/ci.yml) [![Update rehearsal](https://github.com/ConstitutiveTemplates/architekton-py/actions/workflows/update-rehearsal.yml/badge.svg)](https://github.com/ConstitutiveTemplates/architekton-py/actions/workflows/update-rehearsal.yml) [![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ConstitutiveTemplates/architekton-py/badge)](https://scorecard.dev/viewer/?uri=github.com/ConstitutiveTemplates/architekton-py) [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# architekton-py

## TL;DR
Prerequisites: [uv](https://docs.astral.sh/uv) (its `uvx` shim runs everything below) and [git](https://git-scm.com). No clone of this repository is needed; every command expands this fork's **newest release tag**:
```shell
uvx --from git+https://github.com/ConstitutiveTemplates/architekton-py.git architekton-py new my-project --preset library   # shipped CLI: picks the release, renders, records the answers (clones+caches the template on first use)
uvx copier copy --trust https://github.com/ConstitutiveTemplates/architekton-py.git my-project   # or drive copier directly
```

**architekton-py** (formerly *daimonion* and *foundry*, originally *python-copier-template*) is an opinionated
[copier](https://copier.readthedocs.io) template for Python projects: create a
new project from it, update existing projects in line with it, and keep them
in sync as it changes. One questionnaire covers libraries,
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
  chat bots (Discord / Slack / LINE / Gmail), polite web scraping, CTF
  tooling, cloud providers and Sentry.
- **Field rules, not vibes** — every generated project ships an `AGENTS.md`
  agent guide plus an ethics/regional appendix matched to the project kind:
  dependency-license drift, post-quantum crypto standards, AI-and-copyright,
  PKI trust chains, personal data, EU CRA duties, medical-device software,
  face recognition, ML fairness and LLM/MCP security. Sections are
  registered, dated and enforcement-graded (`_shared/ethics/`), held to the
  renders by invariants, and machine-readable through the template's MCP
  server (`check_ethics`, `template://ethics`).

The [feature catalogue](docs/reference/features.md) walks through all of it,
[the questionnaire reference](docs/reference/questionnaire.md) lists every
question, and the [support tiers reference](docs/reference/support.md) says
which combinations CI executes end to end. For the comparison with the upstream
template and the alternatives, see
[Vision & Positioning](docs/explanations/vision.md); the template in action is
the [example project](https://github.com/ConstitutiveTemplates/architekton-py-example).
Fifteen seconds of it, end to end:

![demo: render the cli preset, then run the generated project's checks](docs/assets/demo.gif)

## Create a new project

The shipped CLI is the recommended path. It picks the release to expand,
decides between creating a project and adopting an existing one, and reports
the files the target already has. Installed via `uvx` it clones and caches
the template repo on first use, so no checkout of this repository is needed:

```shell
uvx --from git+https://github.com/ConstitutiveTemplates/architekton-py.git \
    architekton-py new my-project --preset library
```

`--preset library` answers the one question that defines the project family
(`cli`, `web-api`, `data-science`, `ros2`, `micropython`, `online-judge-atcoder`
and `mcp-server` also exist; `bare` is `library` minus the optional
infrastructure extras — no devcontainer, `.vscode`, renovate, secrets/lint
config, security workflow, or issue/PR templates); drop it and copier asks the
[whole questionnaire](docs/reference/questionnaire.md) instead, which needs a
terminal.

Without a preset you can also drive copier directly, which is all the CLI
wraps. `--trust` is required: the template runs post-generation tasks (the
adoption report, the next-steps hint and the REUSE `LICENSES/` copy), and
without it copier generates nothing and exits with status 4:

```shell
git init --initial-branch=main /path/to/my-project
uvx copier copy --trust https://github.com/ConstitutiveTemplates/architekton-py.git /path/to/my-project
```

Both paths expand this fork's newest release tag. Pointing `new` at an
*existing* project runs the same one-liner in adopt mode instead — it adds
the missing infrastructure (CI, quality tooling, `AGENTS.md`) and verifies
the files you already have stay byte-identical
([adopt this template](docs/tutorials/adopt-existing.md)):

```shell
cd /path/to/existing-project
uvx --from git+https://github.com/ConstitutiveTemplates/architekton-py.git architekton-py new .
```

[Create a new project](docs/tutorials/create-new.md) covers the flags, the
presets, adoption and pinning an exact release, and
[generating a project non-interactively](docs/reference/non-interactive.md)
covers `--defaults` with an answers file for CI. For the inverse question —
you know the features you want, not the answers that produce them —
`task answers-for -- --require <name>=<value>` searches the verified answer
space (the same page's *Tell the template what you want*).

## Everyday commands

The generated project drives lint, type-check, test and docs through the task
runner you chose (`just` by default; `task`, `poe`, `invoke`, `duty`, `make` or
pixi's native tasks are the alternatives — one shared task definition, invoked
by CI too). Swap `task` for your runner; the task names are the same:

```shell
task lint        # ruff format --check + ruff check (check-only)
task fix         # ruff --fix + format (typos stays report-only in type-check)
task type-check  # basedpyright + pyrefly, vulture, deptry, typos
task test        # pytest, with coverage at the recommended strictness
task docs        # build the documentation site
task check       # lint + type-check + test
```

`task audit` and `task license-check` need the network and so stay out of
`check`.

## Where to go next

- **[Documentation site](https://constitutivetemplates.github.io/architekton-py)** — the full docs, in
  [tutorials](docs/tutorials.md), [how-to guides](docs/how-to.md),
  [explanations](docs/explanations.md) and [reference](docs/reference.md),
  starting from the [docs index](docs/index.md).
- **New here** — the [installation tutorial](docs/tutorials/installation.md) and
  [create a new project](docs/tutorials/create-new.md).
- **Already have a repo** — [adopt this template into it](docs/tutorials/adopt-existing.md), or
  [update an existing project](docs/how-to/update-template.md) that already uses it.
- **Template internals** — [authoring template sources](docs/explanations/template-dev.md),
  the [structure](docs/explanations/structure.md),
  [how a change is verified](docs/explanations/verification.md) and
  [how the template catches rot with no code changes](docs/explanations/drift-detection.md).

## License, contributing and releases

Licensed under [Apache-2.0](LICENSE). This repository is the template's own
source (not a generated project): [source](https://github.com/ConstitutiveTemplates/architekton-py) ·
[docs site](https://constitutivetemplates.github.io/architekton-py) ·
[releases](https://github.com/ConstitutiveTemplates/architekton-py/releases), whose
notes are generated by [git-cliff](https://git-cliff.org) from the tag's
conventional commits ([CHANGELOG.md](CHANGELOG.md)). Contributions are welcome
— see [CONTRIBUTING.md](.github/CONTRIBUTING.md), the
[contributing how-to](docs/how-to/contribute.md) and
[GOVERNANCE.md](GOVERNANCE.md); report vulnerabilities as described in
[SECURITY.md](SECURITY.md).
