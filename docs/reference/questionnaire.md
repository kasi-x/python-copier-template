# The questionnaire

When you run `copier copy` (or `copier update`), the template asks a small
number of questions and generates a project tailored to your answers.

Each customisable area asks a single **"use the recommended settings?"**
question first (default: yes), with the recommendation spelled out in its help
text. Answer **yes** and that area is configured from its recommended defaults
without asking anything else; answer **no** and the detailed question(s) for
that area are asked.

## Project type (`project_type`)

Asked first, ahead of every area, because the toolchain and several later
questions depend on it.

- **library** — a Python library/package
- **web_api** — an API-only FastAPI service in a top-level `app/` package
  (Docker included; no library `<pkg>`; run with `uvicorn app.main:app`)
- **cli** — a command-line tool
- **data_science** — notebooks, `data/`, `models/`, `reports/` and a `src/`
  pipeline layout; GPU Dockerfile and Quarto paper always included
- **online_judge** — a competitive-programming / Kaggle project, with a
  follow-up question for the judge (`oj_kind`: Kaggle / AtCoder / LeetCode /
  yukicoder / AOJ). Kaggle gets the competition layout
  (`src/{configs,data,input,output,...}` with `src/utils` as the installable
  package); AtCoder / LeetCode / yukicoder / AOJ get a bare code-submission
  workspace whose per-problem folders and `test/` samples are created by a
  CLI tool (`oj` / `acc` / `aoj-cli`)
- **script** — a minimal script, flat package at the repo root
- **web_django** — *not supported*: selecting it aborts generation
- **ros2** — a ROS 2 package (ament_python or ament_cmake), with follow-up
  questions for language, distro and environment provisioning
- **micropython** — MicroPython firmware, with a follow-up question for the
  target port

## Areas and their recommended defaults

| Area gate | Recommended default | Asked when |
|---|---|---|
| `use_recommended_agent` | no agent scaffold | library / cli |
| `use_recommended_toolchain` | uv + just | not ros2+pixi |
| `use_recommended_data_science` | GPU yes, no DUO/CARE | data_science |
| `use_recommended_polish` | src layout, English docstrings | all |
| `use_recommended_docs` | zensical | all |
| `use_recommended_quality` | basedpyright + pyrefly, strictness "recommended" | all |
| `use_recommended_license` | MIT, no FAIR metadata | all |
| `use_recommended_integrations` | no Docker/PyPI/cloud/Sentry/MCP, GitHub Actions, structlog | all |
| `use_recommended_web_api` | FastAPI + async SQLAlchemy + Alembic + Postgres, Prometheus, rate limit, CORS | web_api |
| `use_recommended_security` | minimal CI permissions, SHA-pinned actions, zizmor, SECURITY.md, test_qa.py | all |

## The detailed questions

Answering **No** to an area gate reveals its detailed questions:

- **AI agent** (library / cli): scaffold a runnable pydantic-ai example —
  `prompts/agent.md`, a typed `tools/` package, and an `agent` module wired
  with `@agent.tool`, tested offline with `TestModel`
- **Toolchain**: package manager (uv / pixi / poetry) and task runner
  (just / task / poe / make / invoke / duty, or pixi's native tasks)
- **Data science**: GPU, data reuse (DUO sheet), data ethics (CARE statement)
- **Online judge** (`oj_kind`): kaggle / atcoder / leetcode / yukicoder / aoj
- **Polish**: layout (src / flat), Japanese text allowed
- **Docs**: README-only / zensical / sphinx / great-docs
- **Quality**: secondary checker (pyrefly / ty) and strictness
  (none / basic / recommended / full)
- **License**: the full choosealicense.com list plus Proprietary/Confidential,
  FAIR metadata (CITATION.cff / REUSE), author ORCID
- **Integrations**: Docker, PyPI publishing, cloud provider (aws / gcp /
  azure), Sentry, MCP (cli only — scaffolds an MCP server module
  with typed tools, a `mcp-server-<name>` console script and an in-process
  client test; see [the MCP how-to](../how-to/mcp.md) and
  [the layer model](../explanations/long-running.md)), CI provider, logging
  library
- **Web API** (web_api only): Prometheus metrics at `/metrics`, slowapi rate
  limiting, and CORS — all three default to on; the recommended stack itself
  (FastAPI + async SQLAlchemy 2.0 + Alembic + Postgres in a top-level `app/`
  package, demo CRUD, request-id logging, BackgroundTasks example) is not
  optional. Deliberately an API-only scaffold: full-stack needs (frontend,
  auth, ...) point to the upstream full-stack-fastapi-template instead.
- **Security** (GitHub projects): SECURITY.md vulnerability policy, OpenSSF
  Scorecard workflow. GitLab projects skip both (no private-advisory /
  Scorecard-badge support there)

## Project details

Finally the project details are asked: package name, description, git
platform, and author. The author name/email and GitHub org default from your
local `git config` / `gh` where available, and can be overridden at any prompt.
