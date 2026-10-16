# Contributing to architekton-py

Contributions and issues are welcome. This page gets you from "I want to
change X" to a pull request without first learning how the template is
built.

## Set up once

```shell
git clone https://github.com/politeuma/architekton-py.git && cd architekton-py
uv sync --locked --all-extras
task            # prints the everyday commands
```

You need [uv](https://docs.astral.sh/uv) and [Task](https://taskfile.dev).

## Change something in three steps

### 1. Find the files

Ask the repository. Name the setting (a question, or part of its name):

```console
$ task where -- task_runner
task_runner — question
  defined in  questions/06-toolchain.yml:39
  asks        Which task runner would you like to use to drive lint / type-check /
  feeds       task_runner_effective, runner_just, runner_task

Generated files that exist only depending on it (5)
  template/justfile.jinja
  ...
Snippets the generated files include (partials/) (3)
  partials/tasks.jinja
  ...
Then run:
  edited the question (questions/)?    task regen && task test-fast
  edited a generated file or partial?  task test-fast && task verify-delta
```

No setting in mind? The repository has four parts, and the change you want
lives in one of them:

| To change … | Edit |
| --- | --- |
| a question: its wording, default, choices, or when it is asked | `questions/NN-<area>.yml` (NN is the ask order) |
| what a generated file contains | the file under `template/`, or the snippet in `partials/` it includes |
| whether a generated file exists | its row in `questions/99-files.yml` (`<path>: {{ <condition> }}`) |
| a ready-made answer set | `presets/<name>.yml` |
| the text of a field rule (licenses, personal data, ...) | not here: [law-map](https://github.com/politeuma/law-map/tree/main/guidance/sections) (see [Field rules](#field-rules)) |
| the docs | `docs/`; blocks marked `GENERATED` are rewritten by `task regen`, so edit their source instead |

Data files say at the top who reads them and what happens next, so you can
follow the flow from any of them; `copier.yml` draws the whole render flow
in its first lines.

`architekton/` holds the CLI and the checks. You only need to open it to
change the tooling itself; [its map](architekton/README.md) says which
module does what.

### 2. Edit

Template files are Jinja: `{{ package_name }}` inserts an answer, and
`{% if docs %} ... {% endif %}` includes a block only for some answers.
Derived values (the rows of `questions/90-derived.yml`, such as `docs` or
`is_uv`, grouped by feature) combine several answers; prefer them over
repeating the condition. A question may only read answers asked *before* it, which is
why the file names are numbered.

### 3. Prove it

Run the cheapest check that covers what you touched:

| You changed | Run |
| --- | --- |
| docs only (`README.md`, `docs/`) | `task lint type-check` |
| `template/`, `partials/` | `task test-fast` and `task verify-delta`: it works out which answer combinations your edit can affect, re-renders only those, and shows what changed |
| `questions/` or `copier.yml` | `task regen`, then `task test-fast`: regen re-enumerates the answer combinations, re-judges them and refreshes the generated docs |
| `architekton/`, `tests/`, `.github/workflows/`, `Taskfile.yml` | `task check` |

Whatever you changed, `task hygiene` (merge markers, trailing newlines,
YAML, file sizes) must pass; CI runs it too. Run `task fix` before
committing.

## Adding a question, an opt-in layer or a preset

`architekton-py scaffold question|layer|preset <name>` writes the skeleton
in the right files and prints the remaining steps. The checklist behind it,
and what catches each omission, is
[Extending the questionnaire](docs/explanations/extending.md).

## When a check fails and you want to know why

The checks are explained in
[What each check can and cannot prove](docs/explanations/verification.md)
and [Authoring template sources](docs/explanations/template-dev.md). You do
not need either page until a check fails.

## Field rules

The rule texts (licensing drift, personal data, EU CRA, ...) live in
[law-map's guidance tree](https://github.com/politeuma/law-map/tree/main/guidance/sections)
under CC BY 4.0; fixes and new rules are pull requests there. This
repository only decides which conditions a project declares
(`partials/daimonion-when.jinja`), under [GOVERNANCE.md](.github/GOVERNANCE.md).

## Showing a change in a real project

Tests render projects but do not run their CI or publish their docs. For a
change that affects those, push a branch and update a demonstration repo
from it, then link that repo in the pull request:

```shell
uvx copier update --trust --vcs-ref=<your-branch>
```

## Pull requests, issues and security

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, ...); release notes are generated from them.
- For a large change, open an issue first so you do not spend time on
  something outside the project's scope. Open-ended ideas go to
  [Discussions](https://github.com/politeuma/architekton-py/discussions).
- Report vulnerabilities privately through a
  [security advisory](https://github.com/politeuma/architekton-py/security/advisories/new),
  never a public issue ([SECURITY.md](SECURITY.md)).
