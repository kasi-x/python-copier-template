[![CI](https://github.com/politeuma/architekton-py/actions/workflows/ci.yml/badge.svg)](https://github.com/politeuma/architekton-py/actions/workflows/ci.yml) [![Update rehearsal](https://github.com/politeuma/architekton-py/actions/workflows/update-rehearsal.yml/badge.svg)](https://github.com/politeuma/architekton-py/actions/workflows/update-rehearsal.yml) [![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/politeuma/architekton-py/badge)](https://scorecard.dev/viewer/?uri=github.com/politeuma/architekton-py) [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# architekton-py

A [copier](https://copier.readthedocs.io) template for Python projects. Answer
a few questions (or pick a preset) and get a project that starts with an
`AGENTS.md` for coding agents, strict CI, and the field rules that match its
kind. Later template releases reach the project through `copier update`.

```shell
uvx --from git+https://github.com/politeuma/architekton-py.git architekton-py new my-project --preset library
```

Needs [uv](https://docs.astral.sh/uv) and [git](https://git-scm.com); no clone of this repository.

![demo: render the cli preset, then run the generated project's checks](docs/assets/demo.gif)

## Start here

| I want to … | Go to |
| --- | --- |
| create a project | [Create a project](#create-a-project) below, then [the tutorial](docs/tutorials/create-new.md) |
| add CI, quality tooling and `AGENTS.md` to a repo I already have | [Adopt this template](docs/tutorials/adopt-existing.md) |
| change what the template generates | [CONTRIBUTING.md](CONTRIBUTING.md), which starts with `task where -- <setting>` |
| know what is guaranteed, and how | [What each check can and cannot prove](docs/explanations/verification.md) |

## What you get

- **Eight project types**: `library`, `web_api`, `cli`, `data_science`,
  `online_judge`, `script`, `ros2`, `micropython`, each with its own
  layout, CI and docs.
- **One recommended path**: uv + just + zensical. Each area of the
  questionnaire first asks "use the recommended settings?" (default: yes),
  so this path is mostly one keystroke per area, and it is the only
  combination CI runs end to end (`uv sync`, the generated tests,
  basedpyright, the docs build). The other choices (pixi / poetry; Task /
  poe / invoke / duty / make; Sphinx / great-docs; ty; loguru /
  picologging; ros2; non-AtCoder judges) still render and pass ruff in CI,
  but install-or-run breakage is not caught. See the
  [support tiers](docs/reference/support.md).
- **Quality gates**: ruff (ALL rules), basedpyright + pyrefly, typos,
  vulture, deptry, pip-audit, pytest + coverage + hypothesis, CI with pinned
  actions, `SECURITY.md` and OpenSSF Scorecard.
- **Opt-in layers**: the data-science layout, a FastAPI service, MCP
  servers, chat bots (Discord / Slack / LINE / Gmail), polite web scraping,
  CTF tooling, cloud providers and Sentry.
- **Field rules for coding agents**: the generated `AGENTS.md` gets the
  rules that match the project (dependency licenses, personal data, EU CRA,
  ML fairness, LLM/MCP security, ...), with their sources, rendered by
  [daimonion](https://github.com/politeuma/daimonion) from the
  [law-map](https://github.com/politeuma/law-map) rulebook. Not legal advice.

Every answer combination is enumerated (Z3) and each one's render is
checked; [verification.md](docs/explanations/verification.md) says exactly
what that proves and what it does not. The
[feature catalogue](docs/reference/features.md) and the
[questionnaire reference](docs/reference/questionnaire.md) list everything;
the [example project](https://github.com/politeuma/architekton-py-example)
shows a real render.

## Create a project

`--preset` answers the question that defines the project family:
`library`, `cli`, `web-api`, `data-science`, `ros2`, `micropython`,
`online-judge-atcoder`, `mcp-server`, `bot`, or `bare` (`library` without
the optional extras such as the devcontainer, `.vscode` and renovate);
`architekton-py new --list-presets` shows them all. Leave it out and
copier asks the [whole questionnaire](docs/reference/questionnaire.md) in a
terminal.

The CLI only wraps copier, so you can also call copier directly.
`--trust` is required because the template runs post-generation tasks;
without it copier exits with status 4:

```shell
git init --initial-branch=main my-project
uvx copier copy --trust https://github.com/politeuma/architekton-py.git my-project
```

Both paths use the newest release tag. Pointing `new` at an existing
project switches to adopt mode: it adds the missing infrastructure and
checks that your own files stay byte-identical:

```shell
cd existing-project
uvx --from git+https://github.com/politeuma/architekton-py.git architekton-py new .
```

More: [flags, presets and pinning a release](docs/tutorials/create-new.md),
[non-interactive runs with an answers file](docs/reference/non-interactive.md),
and `architekton-py explain --preset <name>` for why a preset answers what
it does.

## Inside a generated project

The recommended path uses `just`; the other runners expose the same task
names. CI calls the same tasks, so local runs and CI cannot drift:

```shell
just fix         # ruff --fix + format
just check       # lint + type-check + test
just test        # pytest with coverage
just docs        # build the documentation site
```

`just audit` and `just license-check` need the network and stay out of
`check`.

## How this repository is laid out

```text
copier.yml     the questionnaire's table of contents (includes questions/ in order)
questions/     the questions, one file per area; the NN- prefix is the ask order;
               99-files.yml says which generated files exist for which answers
template/      the generated project, file for file
partials/      snippets that template files include
presets/       ready-made answer sets for --preset
architekton/   the CLI and the checks that prove every combination renders (map: architekton/README.md)
tests/         tests, plus the verification matrix under tests/matrix/
docs/          the documentation site
```

To change something, ask the repository where it lives:
`task where -- docs_type` lists the question's file, the generated files
that depend on it, and what to run afterwards. [CONTRIBUTING.md](CONTRIBUTING.md)
has the rest.

## License, contributing and releases

Licensed under [Apache-2.0](LICENSE). Release notes are generated by
[git-cliff](https://git-cliff.org) from conventional commits
([CHANGELOG.md](CHANGELOG.md)). Contributions:
[CONTRIBUTING.md](CONTRIBUTING.md) and [GOVERNANCE.md](.github/GOVERNANCE.md);
vulnerabilities: [SECURITY.md](SECURITY.md). Docs site:
[politeuma.github.io/architekton-py](https://politeuma.github.io/architekton-py).
