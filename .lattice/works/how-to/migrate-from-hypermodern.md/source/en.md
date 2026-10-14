# Migrate from Cookiecutter Hypermodern Python

<lt-m v="["/>Cookiecutter Hypermodern Python<lt-m v="](https://github.com/cjolowicz/cookiecutter-hypermodern-python)"/>
shaped how a generation of Python projects are built: Poetry for
dependencies, nox to drive the sessions, flake8 + Black for lint and
format, mypy for types, and GitHub Actions for everything. It has had no
push since 2024-05, so its user base is effectively orphaned — the question
is no longer <lt-m v="*"/>whether<lt-m v="*"/> to move but <lt-m v="*"/>where<lt-m v="*"/>. This template descends from the
same lineage (strict quality gates, full CI, docs-as-code) updated for the
uv/copier/2026 toolchain, so the migration is mostly a tool swap, not a
change of philosophy. This page walks the concrete steps and names the real
gaps honestly.

There are two routes, and they fit different situations:

- <lt-m v="**"/>Fresh scaffold<lt-m v="**"/> — generate a new project from this template and port
  your code into it. Right for a young repo, or when you want the
  template's own README / CI / docs layout wholesale.
- <lt-m v="**"/>Adopt in place<lt-m v="**"/> — apply the template onto your existing repo,
  protecting your own files. Right for an established repo whose history,
  README, LICENSE and docs you want to keep.

Both are covered below; the <lt-m v="["/>adopt tutorial<lt-m v="](../tutorials/adopt-existing.md)"/>
is the full treatment of the second.

## Toolchain at a glance

| Cookiecutter Hypermodern | This template | Notes |
| --- | --- | --- |
| Cookiecutter | Copier | Cookiecutter expands once and then leaves you on your own. Copier records your answers in `.copier-answers.yml` and offers <lt-m v="**"/>`copier update --trust`<lt-m v="**"/> to merge later template changes into your project — the one-shot-vs-evergreen difference is the whole reason to move. |
| Poetry | uv (default) | uv is the recommended `package_manager`. Poetry is still offered as a choice if you want to keep it; the migration cost below is only real if you actually switch. |
| flake8 + Black | Ruff | One binary does both: `ruff check` (lint) and `ruff format` (Black-compatible formatting), driven by the `lint` and `fix` tasks. flake8 <lt-m v="*"/>plugins<lt-m v="*"/> (bugbear, docstrings, import order) map onto Ruff rule groups (`B`, `D`, `I`), plus typos / vulture / deptry for spelling, dead code and dependencies. |
| mypy | basedpyright + pyrefly | basedpyright is always the primary type checker; <lt-m v="["/>pyrefly<lt-m v="](static-analysis.md)"/> (default) or `ty` runs as a secondary pass. This is a different checker than mypy — see the caveat below. |
| pyup / dependabot | Renovate | `renovate.json` updates the lockfile and dependencies, automerging the uv lockfile when tests pass, and pins GitHub Actions to commit SHAs. See <lt-m v="["/>renovate<lt-m v="](renovate.md)"/>. |
| nox | the task runner | just (default), Task, poethepoet, Make, pyinvoke or duty drive `lint` / `type-check` / `test` / `docs` / `build` / `check`. No `noxfile.py` and no `tox.ini` are generated — see the caveat below. |
| Sphinx (furo) | zensical (default) | The default `docs_type` is zensical (an MkDocs fork with mkdocstrings). Sphinx is still an offered choice, but the config and build command differ. |

The `library` and `cli` <lt-m v="["/>presets<lt-m v="](../tutorials/create-new.md)"/> match the
library-shaped project hypermodern made, so a fresh scaffold with `--preset
library` lands you close to a like-for-like layout.

## Decide which route

| | Fresh scaffold | Adopt in place |
| --- | --- | --- |
| Git history | starts fresh | kept |
| Your README / LICENSE / docs | replaced by the template's | kept, protected |
| Your `pyproject.toml` | replaced; you re-enter metadata | kept; the template <lt-m v="*"/>adds<lt-m v="*"/> its dependencies and `[tool.*]` settings to it |
| Best when | young repo; you want the template's own layout and CI wholesale | established repo with history and prose you want to preserve |
| First update | N/A — you start current | `uvx copier update --trust` |

## Route A: fresh scaffold, then port

Generate a scratch project with the preset that matches hypermodern's
library shape:

```shell
uvx copier copy --trust --defaults \
    --data-file presets/library.yml \
    https://github.com/politeuma/architekton-py.git scratch/
```

(or the shipped CLI: `architekton-py new scratch --preset library`). This answers
every question with the preset plus the recommended defaults, so it never
prompts; drop `--preset` to answer the questionnaire yourself.

Then port your code over:

1. <lt-m v="**"/>Package code.<lt-m v="**"/> Hypermodern uses the same `src/` layout, so copy your
   `src/<package>/` tree as-is. Tests live in `tests/`; both templates run
   pytest, so hypermodern's hypothesis-based tests run unchanged.
2. <lt-m v="**"/>`pyproject.toml` metadata.<lt-m v="**"/> Move your name / version / description /
   authors / readme / URLs into the template's `[project]` table. Hypermodern
   stored these under `[tool.poetry]`; here they are standard `[project]`
   fields, versioned by setuptools-scm from git tags. Version constraints
   in Poetry's `dependencies` become `uv add <package>` calls (or the
   `dependencies` question at generation time).
3. <lt-m v="**"/>Dev dependencies.<lt-m v="**"/> Replace the nox-managed dev set (mypy, flake8,
   Black, ...) with the template's own: it ships ruff, basedpyright, pyrefly
   (or `ty`), typos, vulture, deptry and pip-audit. The dev-extra equivalents
   of what you had are one `uv add --dev` away.
4. <lt-m v="**"/>Docs.<lt-m v="**"/> If you chose Sphinx, move your `.rst` / `conf.py` in and adjust
   theme and build settings; the furo-specific bits don't transfer. If you
   took the zensical default, rewrite the pages as Markdown.
5. <lt-m v="**"/>CI.<lt-m v="**"/> Delete hypermodern's workflows; the template generates its own
   (lint, type-check, tests, docs, hygiene, and — if you answered yes —
   release / publish).

Commit the result, push, enable GitHub Pages / branch protection as the
first-run message suggests.

## Route B: adopt your existing repo in place

The <lt-m v="["/>adopt tutorial<lt-m v="](../tutorials/adopt-existing.md)"/> covers this in full;
the short version is that copier expands the template onto your repo while
protecting the files you already have:

```shell
uvx copier copy --trust \
    --data existing_project=true \
    --skip .github/workflows/ci.yml --skip renovate.json \
    https://github.com/politeuma/architekton-py.git .
git diff        # delete what you do not want, keep your files
git commit -m "chore: adopt architekton-py"
```

By default adoption protects your `README.md`, `LICENSE`, `pyproject.toml`,
`.gitignore`, `.python-version` and `src/` / `tests/` scaffolding — only
missing infrastructure (CI workflows, `.gitleaks.toml`, `renovate.json`,
`AGENTS.md`, hygiene checks) is added, and the template's <lt-m v="*"/>dependencies<lt-m v="*"/> are
merged into your `pyproject.toml` (never a requirement of yours). Task-runner
files and `CHANGELOG.md` are never written in adopt mode, so your recipes and
history stay put. The `architekton/adopt.py` driver does the plan / apply / rollback
for you:

```shell
uv run --locked python architekton/adopt.py . --dry-run
uv run --locked python architekton/adopt.py .
```

Run `architekton/detect.py` first — it reports which operation fits your repo and
prints the ready-to-run command. From then on, updates are the same
`uvx copier update --trust` any generated project uses.

## What you gain

- <lt-m v="**"/>An update path.<lt-m v="**"/> `copier update --trust` merges template changes into
  your project. This is the headline: Cookiecutter has no equivalent, and
  it is the reason an abandoned template strands its users.
- <lt-m v="**"/>A Z3-verified questionnaire.<lt-m v="**"/> Every `when:` condition in the
  questionnaire is checked for satisfiability with an SMT solver (Z3) — a
  dead branch or a typo'd variable name is a test failure, not a support
  ticket. The logic that decides what a project renders is proven, not just
  exercised.
- <lt-m v="**"/>`AGENTS.md`.<lt-m v="**"/> Each generated project ships an agent guide stating the
  exact commands (its task runner) and where edits belong — useful with or
  without an AI coding agent.
- <lt-m v="**"/>An ethics appendix.<lt-m v="**"/> Field rules matched to your project kind (license
  drift, scraping law, contest-integrity, and more) render into `AGENTS.md`,
  and `check_ethics` matches text against them. See
  <lt-m v="["/>ethics-section<lt-m v="](ethics-section.md)"/>.
- <lt-m v="**"/>Breadth.<lt-m v="**"/> Hypermodern only made libraries. Here `project_type` covers
  `library`, `cli`, `web_api`, `data_science`, `online_judge`, `script`,
  `ros2` and `micropython`, combinable via opt-in layers — your next project
  shape is covered by the same template.
- <lt-m v="**"/>Hardened CI.<lt-m v="**"/> Actions pinned to commit SHAs, zizmor + actionlint
  checks, gitleaks secret scanning, an optional OpenSSF Scorecard workflow,
  a `SECURITY.md` policy, conventional-commit enforcement, and a
  git-cliff-generated `CHANGELOG.md`.

## What you lose — the real gaps

- <lt-m v="**"/>No 1:1 equivalent for every nox session.<lt-m v="**"/> The template ships no
  `noxfile.py` and no `tox.ini`; the standard sessions (`lint`, `type-check`,
  `test`, `docs`) map onto task-runner recipes of the same names, but a
  <lt-m v="*"/>custom<lt-m v="*"/> session you wrote — a parameterized matrix, a session that
  installs extra dependencies before running, a bespoke `dev` bootstrap —
  has no generated counterpart. You re-express it as a task recipe or a CI
  job. If you specifically want tox or <lt-m v="["/>tox-uv<lt-m v="](https://github.com/tox-dev/tox-uv)"/>,
  nothing generates one; because uv is the package manager you can run
  `uvx tox-uv` and port your `noxfile.py` sessions, but that is a
  hand-written addition, not a template feature.
- <lt-m v="**"/>mypy config does not port.<lt-m v="**"/> basedpyright is a pyright fork, not mypy:
  `[tool.mypy]` settings, per-module overrides and `# type: ignore[mypy-...]`
  codes need translation to `[tool.pyright]` / `[tool.basedpyright]`. The
  strictness level the template applies is its own (`recommended` /
  `full`), not mypy's.
- <lt-m v="**"/>Docs tooling differs.<lt-m v="**"/> Hypermodern used Sphinx with the furo theme; the
  default here is zensical (MkDocs fork). Sphinx is still an offered
  `docs_type`, but the theme, `conf.py` and build command (`task docs`)
  differ from hypermodern's — so porting an existing Sphinx tree is a
  reconfiguration, not a copy.
- <lt-m v="**"/>Poetry specifics are gone (if you switch).<lt-m v="**"/> `[tool.poetry]`, the
  `poetry.lock` and any Poetry plugin you relied on (dynamic versioning,
  build backend hooks) are not read by uv. The template versions with
  setuptools-scm instead; if you keep Poetry as `package_manager`, none of
  this applies.
- <lt-m v="**"/>flake8 / Black plugins need re-mapping.<lt-m v="**"/> Ruff implements most of
  flake8's popular plugin behavior under different rule codes; the
  `# flake8: noqa` and `[tool.black]` markers are not read as-is. Run
  `task lint` (or `fix`) and work through the findings once, then carry the
  remaining selections over in `[tool.ruff.lint.select]` — that is the
  translation.
- <lt-m v="**"/>GitLab, not just GitHub.<lt-m v="**"/> Hypermodern was GitHub-only. Here
  `git_platform` also offers `gitlab.com`; some GitHub-only pieces
  (`SECURITY.md`, Scorecard) are deliberately skipped on GitLab.
- <lt-m v="**"/>A template, not a drop-in.<lt-m v="**"/> The template is its own project (forked
  from DiamondLightSource's copier template, sharing the strict-quality
  lineage with hypermodern), so adopt it for the <lt-m v="*"/>shape<lt-m v="*"/> of the toolchain,
  not as a byte-for-byte continuation.

None of these are blockers — they are the same cost any migration between
two maintained stacks incurs, and the update path this template adds is the
thing hypermodern could not give you.
