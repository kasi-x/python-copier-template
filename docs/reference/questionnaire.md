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
- **online_judge** — a competitive-programming / CTF project. `oj_category`
  asks first (data_science / competitive_coding / ctf), then `oj_kind` lists
  only that category's judges: Kaggle (competition layout
  `src/{configs,data,input,output,...}` with `src/utils` as the installable
  package); AtCoder / LeetCode / yukicoder / AOJ (bare code-submission
  workspace whose per-problem folders and `test/` samples are created by a
  CLI tool: `oj` / `acc` / `aoj-cli`); CTF (participant workspace
  `challenges/<category>/<problem>/solve.py` plus `pwntools` / `z3-solver`).
- **script** — a minimal script, flat package at the repo root
- **web_django** — *not supported*: selecting it aborts generation
- **ros2** — a ROS 2 package (ament_python or ament_cmake), with follow-up
  questions for language, distro and environment provisioning
- **micropython** — MicroPython firmware, with a follow-up question for the
  target port

## Not project types (by design)

`project_type` only grows for a fundamentally different execution environment
or a distinct competition-rules axis. Everything else is a layer on an
existing type, or out of scope:
- **CTF** — same CPython environment as `library` / `cli`, so no new type.
  Two entry paths share one shape: `include_ctf` (asked for the `library` /
  `cli` bases) and `oj_category=ctf` under `online_judge` (see above).
  Organiser scaffolds (Docker + socat + gdb) are out of scope — a
  separate-repo concern.
- **Ansible / Terraform / Kubernetes** — separate-repo concerns, not Python
  projects. IaC lives beside the app, not in this template.
- **Django** — see `web_django` above and [the web-api
  how-to](../how-to/web-api.md): FastAPI / Litestar / Flask, or upstream
  cookiecutter-django.
- **SRE** — scoped to `web_api` hardening: non-root runtime user,
  read-only root filesystem, resource limits, `/health` probes. No
  separate observability questionnaire (metrics are the three web_api
  switches).

## Combining bases and layers

`project_type` picks the **base**; two opt-in questions can layer another
element on top of it (same idea as the MCP layer on `cli`):

- **include_data_science** (asked for the `library` / `cli` / `web_api`
  bases) — adds the data_science analysis layout (`notebooks/`, `data/`,
  `models/`, `reports/`, Quarto paper) alongside the base
- **include_ctf** (asked for the `library` / `cli` bases) — adds the CTF
  participant workspace (`challenges/`, `solve.py` starter, `ctf` extra)
  alongside the base
- **include_scraping** (asked for the `cli` base) — adds the polite
  web-fetching layer (`CHARTER.md`, `fetcher.py` + offline test, ruff
  `banned-api` on direct HTTP calls). Answering No to
  `use_recommended_scraping` reveals `scraping_engine` (`httpx` /
  `scrapy` / `memorious` / `playwright` / `all`); `memorious` forces the
  project license to AGPL-3.0. See [the scraping how-to](../how-to/scraping.md)
  and [the Good-future charter](../explanations/good-future.md)

`ros2` / `micropython` / code-submission judges / `script` stay single-type:
their build or execution shape cannot be combined. The `data_science` and
`web_api` detail questions below are asked whenever the matching layer is
present — whether from the base or from the opt-in.

## Areas and their recommended defaults

| Area gate | Recommended default | Asked when |
|---|---|---|
| `use_recommended_agent` | no agent scaffold | library / cli |
| `use_recommended_toolchain` | uv + just | not ros2+pixi |
| `use_recommended_data_science` | GPU yes; DUO/CARE asked separately | data_science layer present |
| `use_recommended_polish` | src layout, English docstrings | all |
| `use_recommended_docs` | zensical | all |
| `use_recommended_quality` | basedpyright + pyrefly, strictness "recommended" | all |
| `use_recommended_license` | MIT, no FAIR metadata | all |
| `use_recommended_integrations` | no Docker/PyPI/cloud/Sentry/MCP, GitHub Actions, structlog | all |
| `use_recommended_web_api` | FastAPI + async SQLAlchemy + Alembic + Postgres, Prometheus, rate limit, CORS | web_api layer present |
| `use_recommended_security` | minimal CI permissions, SHA-pinned actions, zizmor, SECURITY.md, test_qa.py | all |

## The detailed questions

Answering **No** to an area gate reveals its detailed questions:

- **AI agent** (library / cli): scaffold a runnable pydantic-ai example —
  `prompts/agent.md`, a typed `tools/` package, and an `agent` module wired
  with `@agent.tool`, tested offline with `TestModel`
- **Toolchain**: package manager (uv / pixi / poetry) and task runner
  (just / task / poe / make / invoke / duty, or pixi's native tasks)
- **Data science**: GPU, then data reuse (DUO sheet) and data ethics (CARE
  statement) — asked on every data_science path, independent of the
  recommended gate. The GPU question shows a one-line hint from your local
  `nvidia-smi` (GPU name + driver CUDA vs the template's pinned CUDA 12.6)
  when a GPU is present.
- **Online judge** (`oj_category` + `oj_kind`): data_science → kaggle /
  competitive_coding → atcoder / leetcode / yukicoder / aoj / ctf → ctf.
  Kaggle and CTF always ship an `AGENTS.md` agent guide; AtCoder / LeetCode
  ask `oj_allow_ai` (default: no) which decides whether `AGENTS.md` is
  generated; yukicoder / AOJ omit it.
- **Polish**: layout (src / flat), Japanese text allowed (`allow_japanese`
  relaxes line-length 88 → 120 and max-doc-length 150 → 200 so wide multibyte
  text does not trigger E501/D rules)
- **Docs**: README-only / zensical / sphinx / great-docs. For micropython,
  sphinx is not offered — answering it falls back to zensical (the firmware
  is not a CPython-importable package, so autodoc has nothing to document)
- **Quality**: secondary checker (pyrefly / ty) and strictness
  (none / basic / recommended / full)
- **License**: the full choosealicense.com list plus Proprietary/Confidential,
  FAIR metadata (CITATION.cff / REUSE), author ORCID
- **Integrations**: Docker, PyPI publishing, cloud provider (aws / gcp /
  azure), Sentry, MCP (cli and web_api bases, plus the include_web_api layer —
  scaffolds an MCP server module with typed tools, a `mcp-server-<name>`
  console script and an in-process client test; the module lives in
  `app/mcp_server.py` when the web_api layer is present, otherwise in
  `<pkg>/mcp_server.py`; see [the MCP how-to](../how-to/mcp.md) and
  [the layer model](../explanations/long-running.md)), CI provider, logging
  library
- **Web API** (web_api layer present — base or opt-in): Prometheus metrics at
  `/metrics`, slowapi rate limiting, and CORS — all three default to on; the recommended stack itself
  (FastAPI + async SQLAlchemy 2.0 + Alembic + Postgres in a top-level `app/`
  package, demo CRUD, request-id logging, BackgroundTasks example) is not
  optional. Deliberately an API-only scaffold: full-stack needs (frontend,
  auth, ...) point to the upstream full-stack-fastapi-template instead.
- **Security** (GitHub projects): SECURITY.md vulnerability policy, OpenSSF
  Scorecard workflow, and the `license_check` compliance gate
  (`pip-licenses --fail-on`, on by default — fails on copyleft the project
  license cannot absorb). It runs as a standalone `license-check` task,
  called from the CI lint job alongside `type-check` (never inside local
  `check`, which stays offline). GitLab projects skip SECURITY.md and
  Scorecard (no private-advisory / Scorecard-badge support there) but keep
  the license check. `author_orcid` is validated as an ORCID iD when given.

## Project details

Finally the project details are asked: package name, description, git
platform, and author. The author name/email and GitHub org default from your
local `git config` / `gh` where available, and can be overridden at any prompt.
