[![CI](https://github.com/politeuma/architekton-py/actions/workflows/ci.yml/badge.svg)](https://github.com/politeuma/architekton-py/actions/workflows/ci.yml) [![Update rehearsal](https://github.com/politeuma/architekton-py/actions/workflows/update-rehearsal.yml/badge.svg)](https://github.com/politeuma/architekton-py/actions/workflows/update-rehearsal.yml) [![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/politeuma/architekton-py/badge)](https://scorecard.dev/viewer/?uri=github.com/politeuma/architekton-py) [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# architekton-py

## TL;DR
Prerequisites: [uv](https://docs.astral.sh/uv) (its `uvx` shim runs everything below) and [git](https://git-scm.com). No clone of this repository is needed; every command expands this fork's **newest release tag**:
```shell
uvx --from git+https://github.com/politeuma/architekton-py.git architekton-py new my-project --preset library   # shipped CLI: picks the release, renders, records the answers (clones+caches the template on first use)
uvx copier copy --trust https://github.com/politeuma/architekton-py.git my-project   # or drive copier directly
```

**architekton-py** is an opinionated
[copier](https://copier.readthedocs.io) template for Python projects: create a
new project from it, update existing projects in line with it, and keep them
in sync as it changes. One questionnaire covers libraries,
web APIs, CLIs, data-science pipelines, competitive programming, ROS 2 packages
and MicroPython firmware. Its question logic is machine-checked (Z3 shows every
`when` condition is satisfiable and enumerates the answer leaves), every leaf's
render is checked against declared file-set and content invariants, and a
sample of leaves is executed for real; see
[what each layer can and cannot prove](docs/explanations/verification.md).

## What you get

Each area of the questionnaire first asks "use the recommended settings?"
(default: yes), so the recommended path is usually a single keystroke:

- **Eight project types** — `library`, `web_api`, `cli`, `data_science`,
  `online_judge`, `script`, `ros2`, `micropython`, each with its own layout,
  CI and docs.
- **The recommended path: uv + just + zensical.** Answering "yes" to every
  "use the recommended …?" gate renders this toolchain, and it is the only
  combination CI executes end to end (`uv sync`, the generated pytest,
  basedpyright, the docs build — the `full` tier in
  [docs/reference/support.md](docs/reference/support.md)). Everything else
  the questionnaire offers (pixi / poetry; Task / poe / invoke / duty / make
  / pixi tasks; Sphinx / great-docs; ty; loguru / picologging; ros2; the
  non-AtCoder judges) keeps rendering and is ruff-checked in the fast tier,
  but is community-supported: regressions that only break install or run are
  not caught by CI. Nothing is removed — pick what fits, knowing the
  guarantee level.
- **Quality gates** — ruff (ALL rules), basedpyright + pyrefly, typos, vulture,
  deptry, pip-audit, pytest + coverage + hypothesis, hardened CI with pinned
  actions, SECURITY.md and OpenSSF Scorecard.
- **Opt-in layers** — the data-science layout, a FastAPI service, MCP servers,
  chat bots (Discord / Slack / LINE / Gmail), polite web scraping, CTF
  tooling, cloud providers and Sentry.
- **Field rules, not vibes** — every generated project ships an `AGENTS.md`
  agent guide plus a `.daimonion.yml` declaring the kanon conditions matched
  to the project kind: dependency-license drift, post-quantum crypto
  standards, AI-and-copyright, PKI trust chains, personal data, EU CRA
  duties, medical-device software, face recognition, ML fairness and LLM/MCP
  security. The `daimonion` linter renders the matching sections into the
  guide's marker block (`daimonion agents-md --write`); the emitted `when`
  list is held to the renders by invariants.

The [feature catalogue](docs/reference/features.md) walks through all of it,
[the questionnaire reference](docs/reference/questionnaire.md) lists every
question, and the [support tiers reference](docs/reference/support.md) says
which combinations CI executes end to end. For the comparison with the upstream
template and the alternatives, see
[Vision & Positioning](docs/explanations/vision.md); the template in action is
the [example project](https://github.com/politeuma/architekton-py-example).
Fifteen seconds of it, end to end:

![demo: render the cli preset, then run the generated project's checks](docs/assets/demo.gif)

## Create a new project

The shipped CLI is the recommended path. It picks the release to expand,
decides between creating a project and adopting an existing one, and reports
the files the target already has. Installed via `uvx` it clones and caches
the template repo on first use, so no checkout of this repository is needed:

```shell
uvx --from git+https://github.com/politeuma/architekton-py.git \
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
uvx copier copy --trust https://github.com/politeuma/architekton-py.git /path/to/my-project
```

Both paths expand this fork's newest release tag. Pointing `new` at an
*existing* project runs the same one-liner in adopt mode instead — it adds
the missing infrastructure (CI, quality tooling, `AGENTS.md`) and verifies
the files you already have stay byte-identical
([adopt this template](docs/tutorials/adopt-existing.md)):

```shell
cd /path/to/existing-project
uvx --from git+https://github.com/politeuma/architekton-py.git architekton-py new .
```

[Create a new project](docs/tutorials/create-new.md) covers the flags, the
presets, adoption and pinning an exact release, and
[generating a project non-interactively](docs/reference/non-interactive.md)
covers `--defaults` with an answers file for CI. For the inverse question —
you know the features you want, not the answers that produce them —
`task answers-for -- --require <name>=<value>` searches the verified answer
space (the same page's *Tell the template what you want*).

## Everyday commands

The recommended path renders `just` as the task runner; the commands below
use it. Every other runner the questionnaire offers (`task`, `poe`,
`invoke`, `duty`, `make`, pixi's native tasks) exposes the same task names —
swap the runner word, nothing else — but those runners are
community-supported (see [the recommended path](#what-you-get)).
The generated project drives lint, type-check, test and docs through that
runner (CI calls the same tasks, so local and CI cannot drift):

```shell
just lint        # ruff format --check + ruff check (check-only)
just fix         # ruff --fix + format (typos stays report-only in type-check)
just type-check  # basedpyright + pyrefly, vulture, deptry, typos
just test        # pytest, with coverage at the recommended strictness
just docs        # build the documentation site
just check       # lint + type-check + test
```

`just audit` and `just license-check` need the network and so stay out of
`check`.

## Where to go next

- **[Documentation site](https://politeuma.github.io/architekton-py)** — the full docs:
  [tutorials](docs/tutorials.md) to start, [reference](docs/reference.md)
  for the questionnaire and guarantees, [explanations](docs/explanations.md)
  for why it works this way — starting from the [docs index](docs/index.md).
- **New here** — the [installation tutorial](docs/tutorials/installation.md) and
  [create a new project](docs/tutorials/create-new.md).
- **Already have a repo** — [adopt this template into it](docs/tutorials/adopt-existing.md), or
  [update an existing project](docs/how-to/update-template.md) that already uses it.
- **Changing the template itself** — [the shortest path](docs/how-to/change-template.md):
  one page, three change shapes, one proving command each. The meta-tooling
  (`tools/`, the workflow fleet, the Quint specs) is deliberately not linked
  here — it holds the render contract and you only meet it through that page.

## License, contributing and releases

Licensed under [Apache-2.0](LICENSE). This repository is the template's own
source (not a generated project): [source](https://github.com/politeuma/architekton-py) ·
[docs site](https://politeuma.github.io/architekton-py) ·
[releases](https://github.com/politeuma/architekton-py/releases), whose
notes are generated by [git-cliff](https://git-cliff.org) from the tag's
conventional commits ([CHANGELOG.md](CHANGELOG.md)). Contributions are welcome
— see [CONTRIBUTING.md](.github/CONTRIBUTING.md), the
[contributing how-to](docs/how-to/contribute.md) and
[GOVERNANCE.md](GOVERNANCE.md); report vulnerabilities as described in
[SECURITY.md](SECURITY.md).
