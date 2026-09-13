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

<!-- BEGIN GENERATED: project-types (tools/gen_docs.py --write) -->
- **library** — a Python library/package.
- **web_api** — a web API service (Docker included).
- **cli** — a command-line tool.
- **data_science** — a data science project with notebooks, data/, models/, reports/ and experiment
  extras. GPU Dockerfile and Quarto paper are included.
- **online_judge** — a competitive-programming / Kaggle project. The rules for AI coding agents
  differ per judge, which decides whether an AGENTS.md file is generated.
  Questions asked when this is the base type:
  - **`oj_category`** (str; default `data_science`) — Which competition category is this project
    for?
    - **`data_science`** — Kaggle-style data competitions (GPU competition layout).
    - **`competitive_coding`** — code-submission judges (AtCoder / LeetCode / yukicoder / AOJ). A
      bare workspace driven with oj / acc / aoj-cli.
    - **`ctf`** — CTF competitions (participant workspace with challenges/ and a solve.py starter,
      plus pwntools / z3-solver).
  - **`oj_kind`** (str; default `'ctf' if oj_category == 'ctf' else ('atcoder' if oj_category ==
    'competitive_coding' else 'kaggle')`) — Which online judge is this project for?
    - **`kaggle`** — Kaggle competitions. GPU work is the norm and the competition layout
      (src/utils, src/input, src/output) is generated.
    - **`atcoder`** — AtCoder (Japanese competitive programming). A bare workspace driven with oj +
      acc (atcoder-cli).
    - **`leetcode`** — LeetCode-style problems. A bare workspace (LeetCode's editor is the judge; oj
      does not support it).
    - **`yukicoder`** — yukicoder (Japanese practice site). A bare workspace driven with oj
      (download / test / submit all work).
    - **`aoj`** — Aizu Online Judge (Japanese beginner courses). A bare workspace driven with
      aoj-cli (oj can download samples but not submit).
    - **`ctf`** — CTF competitions. A participant workspace (challenges/ with a solve.py starter,
      pwntools / z3-solver via the ctf extra).
  - **`oj_allow_ai`** (bool; default no) — Is AI assistance (coding agents, code completion) allowed
    for this judge?
- **script** — a minimal script, no package layout.
- **ros2** — a ROS 2 package (ament_python or ament_cmake). Built with colcon + rosdep; not a
  uv/pixi/poetry project.
  Questions asked when this is the base type:
  - **`pkg_language`** (str; default `python`) — Which language for the ROS 2 package?
    - **`python`** — ament_python (rclpy) — setup.py + package.xml + resource/.
    - **`cpp`** — ament_cmake — CMakeLists.txt + src/*.cpp + include/.
  - **`ros_distro`** (str; default `humble`) — ROS 2 distribution. Humble (Ubuntu 22.04, Python
    3.10) is the most widely deployed; Jazzy (Ubuntu 24.04, Python 3.12) is the current LTS.
    One of: `humble` (Humble (22.04 / Python 3.10)) · `jazzy` (Jazzy (24.04 / Python 3.12)).
  - **`ros2_package_manager`** (str; default `apt`) — How should the ROS 2 environment be
    provisioned?
    - **`apt`** — the classic ROS 2 way — Ubuntu + apt (ros-{{ ros_distro }}-*) + colcon + rosdep.
      Docker base image ros:{{ ros_distro }}-ros-base.
    - **`pixi`** — RoboStack conda-forge packages via pixi, using the distro channel
      (https://prefix.dev/robostack-{{ ros_distro }}). No sudo/apt needed. See
      https://pixi.prefix.dev/latest/robotics/.
- **micropython** — MicroPython firmware for a microcontroller (esp32, rp2, ...). Deployed with
  mpremote; the CPython dev toolchain (uv/ruff/pytest/basedpyright) coexists for testing and
  type-checking against micropython-<port>-stubs.
  Questions asked when this is the base type:
  - **`micropython_port`** (str; default `esp32`) — Which MicroPython port are you targeting? This
    picks the micropython-<port>-stubs package used for type-checking.
    - **`esp32`** — ESP32 family (most common; default)
    - **`esp8266`** — ESP8266 (legacy, low memory)
    - **`rp2`** — Raspberry Pi Pico / RP2040 / RP2350
    - **`stm32`** — STM32 family (Pyboard etc.)
    - **`samd`** — Microchip SAMD21 / SAMD51
    - **`unix`** — Unix port (runs on your computer — handy for testing)
    - **`windows`** — Windows port
    - **`mimxrt`** — NXP i.MX RT family (Teensy 4.x etc.)
<!-- END GENERATED: project-types -->

## Not project types (by design)

`project_type` only grows for a fundamentally different execution environment
or a distinct competition-rules axis. Everything else is a layer on an
existing type, or out of scope:

- **CTF** — same CPython environment as `library` / `cli`, so no new type.
  Two entry paths share one shape: `include_ctf` (asked for the `library` /
  `cli` bases) and `oj_category=ctf` under `online_judge`.
  Organiser scaffolds (Docker + socat + gdb) are out of scope — a
  separate-repo concern.
- **Ansible / Terraform / Kubernetes** — separate-repo concerns, not Python
  projects. IaC lives beside the app, not in this template.
- **Django** — no `project_type` of its own: `web_api` (FastAPI / Litestar /
  Flask) is the Python API type, and Django itself belongs to
  [upstream cookiecutter-django](https://github.com/cookiecutter/cookiecutter-django)
  — see [the web-api how-to](../how-to/web-api.md).
- **SRE** — scoped to `web_api` hardening: non-root runtime user,
  read-only root filesystem, resource limits, `/health` probes. No
  separate observability questionnaire (metrics are the three web_api
  switches).

## Combining bases and layers

`project_type` picks the **base**; the `include_*` questions can layer another
element on top of it (same idea as the MCP layer on `cli`). The layer list,
its conditions and the recommended defaults are generated below; two things
that list cannot show:

- The added content is the same whether the matching layer comes from the base
  or from the opt-in: the `data_science` and `web_api` detail questions are
  asked whenever that layer is present.
- Answering No to `use_recommended_scraping` reveals `scraping_engine`
  (`httpx` / `scrapy` / `memorious` / `playwright` / `all`); `memorious` forces
  the project license to AGPL-3.0. See [the scraping how-to](../how-to/scraping.md)
  and [the Good-future charter](../explanations/good-future.md).

`ros2` / `micropython` / code-submission judges / `script` stay single-type:
their build or execution shape cannot be combined.

## Areas and their recommended defaults

<!-- BEGIN GENERATED: areas (tools/gen_docs.py --write) -->
Each area asks one gate question first: answering **Yes** configures it from the recommendation below, answering **No** reveals that area's detailed questions.

| Area gate | Recommended default | Asked when |
|---|---|---|
| `use_recommended_agent` | yes — a plain library / CLI without agent tooling. | library / cli |
| `use_recommended_toolchain` | uv (package manager) + just (task runner). | not ros2 + pixi |
| `use_recommended_data_science` | GPU workloads enabled (NVIDIA CUDA Dockerfile + devcontainer). | the data_science layer is present |
| `use_recommended_polish` | src/ layout (library/cli), no Japanese (multibyte) characters in comments/docstrings. | all |
| `use_recommended_docs` | zensical (Zensical, an MkDocs fork with mkdocstrings). | all |
| `use_recommended_quality` | basedpyright (primary) + pyrefly (additional static analysis), strictness "recommended" (ruff ALL rules, typos/vulture/deptry/pip-audit). | all |
| `use_recommended_license` | MIT license, no FAIR research-software metadata (CITATION.cff / REUSE). | all |
| `use_recommended_integrations` | no Docker container, no PyPI auto-publish, no cloud provider, no Sentry, no MCP support, GitHub Actions for CI, structlog for logging. | all |
| `use_recommended_web_api` | a FastAPI app in a top-level `app/` package (no library <pkg>): async SQLAlchemy 2.0 + Alembic + Postgres, a demo CRUD router, request-id logging (asgi-correlation-id), a BackgroundTasks example, and /health + /docs endpoints. | the web_api layer is present |
| `use_recommended_security` | minimal CI permissions, GitHub Actions pinned to commit SHAs (renovate keeps them up to date), zizmor + actionlint checks, a SECURITY.md vulnerability-reporting policy, a test_qa.py that verifies dependency integrity and the public API at runtime, and a license-check task (pip-licenses --fail-on with the project's copyleft policy) that runs inside type-check. | all |

An opt-in layer adds its area to a combinable base:

- **`include_data_science`** (asked when library / cli / web_api; default no) — Add the data_science
  analysis layout (notebooks/, data/, models/, reports/, Quarto paper) on top of this project?
- **`include_web_api`** (asked when library / cli / data_science / kaggle; default no) — Add the
  FastAPI scaffold (top-level app/ package) on top of this project? The web_api detail questions
  follow when answered Yes.
- **`include_ctf`** (asked when library / cli; default no) — Add a CTF participant workspace
  (challenges/<category>/<problem>/ with a solve.py exploit starter, plus pwntools and z3-solver)?
- **`include_scraping`** (asked when cli; default no) — Add a polite web-fetching layer (robots.txt
  + rate limit + cache)?

An opt-in layer asks its own gate on top:

- **`use_recommended_scraping`** (asked when a `cli` base answers Yes to `include_scraping`): httpx
  — a polite stdlib-robots fetcher (contactable User-Agent, robots.txt check, per-host rate
  limiting, on-disk cache) with offline tests.
<!-- END GENERATED: areas -->

## The detailed questions

<!-- BEGIN GENERATED: detailed-questions (tools/gen_docs.py --write) -->
Answering **No** to a gate reveals that area's detailed questions:

### `use_recommended_agent`

Use the recommended agent setup (no agent tooling)? Recommended: yes — a plain library / CLI without agent tooling.

Answer **No** to add a runnable pydantic-ai example: a prompts/ directory, a typed tools/ package and an agent module wired with @agent.tool, tested offline with pydantic-ai's TestModel.

### `use_recommended_toolchain`

Use the recommended package manager & task runner? Recommended: uv (package manager) + just (task runner).

Answer **No** to pick pixi/poetry, or a different task runner.

- **`package_manager`** (str; default `'pixi' if project_type == 'ros2' and ros2_package_manager ==
  'pixi' else 'uv'`) — Which package manager would you like to use?
  - **`uv`** — Fast, pure Python package manager with a pip-like workflow.
  - **`pixi`** — Conda-based package manager with cross-language support.
  - **`poetry`** — Dependency management and packaging with Poetry.
- **`task_runner`** (str; default `just`) — Which task runner would you like to use to drive lint /
  type-check / test / docs (and, for kaggle's pipeline, the ML shortcuts)?
  - **`just`** — Just. Simple justfile, external binary.
  - **`task`** — Task (go-task). YAML, external binary, used by CI too.
  - **`poe`** — poethepoet. Pure Python, lives in pyproject.toml, no extra binary to install (just a
    dev dependency).
  - **`make`** — GNU Make. Universally available, terse Makefile syntax.
  - **`invoke`** — pyinvoke. Pure Python, tasks.py with @task-decorated functions, no extra binary
    to install (just a dev dependency).
  - **`duty`** — duty (used by pawamoy's copier-uv). Pure Python, duties.py with @duty-decorated
    functions, no extra binary to install.
- **`task_runner_pixi`** (str; default `pixi`) — Which task runner would you like to use?
  (poethepoet doesn't work with pixi, so pixi's own native tasks take its place here.)
  - **`pixi`** — pixi's own native tasks (`pixi run <name>`). No extra tool.
  - **`task`** — Task (go-task). YAML, external binary, used by CI too.
  - **`just`** — Just. Simple justfile, external binary.
  - **`make`** — GNU Make. Universally available, terse Makefile syntax.

### `use_recommended_scraping`

Use the recommended web-fetching engine? Recommended: httpx — a polite stdlib-robots fetcher (contactable User-Agent, robots.txt check, per-host rate limiting, on-disk cache) with offline tests.

Answer **No** to pick scrapy / memorious / playwright instead (or all).

- **`scraping_engine`** (str; default `httpx`) — Which web-fetching engine should the fetcher layer
  prepare?
  - **`httpx`** — polite httpx fetcher (same as recommended).
  - **`scrapy`** — a Scrapy spider starter (ROBOTSTXT_OBEY + AUTOTHROTTLE + DOWNLOAD_DELAY enforced
    in settings, offline parse test).
  - **`memorious`** — a memorious crawler config (rate-limited, cached HTTP sessions). memorious4 is
    AGPL-3.0 — choosing it requires an AGPL-3.0 project license (enforced below).
  - **`playwright`** — a Playwright browser-fetch module (Chromium via `playwright install`; robots
    precheck + rate limit reused from the fetcher; no browser launch in tests).
  - **`all`** — prepare every engine above (all runtime dependencies).

### `use_recommended_data_science`

Use the recommended data_science options? Recommended: GPU workloads enabled (NVIDIA CUDA Dockerfile + devcontainer).

Answer **No** to change the GPU setting.

- **`use_gpu`** (bool; default yes) — Will you run GPU workloads?

### `use_recommended_polish`

Use the recommended layout & repo polish? Recommended: src/ layout (library/cli), no Japanese (multibyte) characters in comments/docstrings.

Answer **No** to change the layout or allow Japanese text.

- **`layout`** (str; default `src`) — Which layout would you like to use for the package?
  - **`src`** — package in a src/ directory (recommended, prevents accidental imports of an
    uninstalled package).
  - **`flat`** — package at the repository root.
- **`allow_japanese`** (bool; default no) — Allow Japanese (multibyte) characters in comments and
  docstrings?

### `use_recommended_docs`

Use the recommended documentation tool? Recommended: zensical (Zensical, an MkDocs fork with mkdocstrings).

Answer **No** to pick README-only, Sphinx or Great Docs instead.

- **`docs_type`** (str; default `zensical`) — Which documentation tool would you like to use?
  - **`README`** — just a README, no dedicated docs site.
  - **`zensical`** — Zensical, an MkDocs fork with mkdocstrings. Fast to set up.
  - **`sphinx`** — Sphinx with the pydata theme. More powerful, more config.
  - **`great-docs`** — Great Docs, a Quarto-based tool. Requires Quarto installed.

### `use_recommended_quality`

Use the recommended type checker & strictness level? Recommended: basedpyright (primary) + pyrefly (additional static analysis), strictness "recommended" (ruff ALL rules, typos/vulture/deptry/pip-audit).

Answer **No** to pick a different secondary checker or strictness level.

- **`type_checker`** (str; default `pyrefly`) — Which additional static-analysis checker should run
  alongside basedpyright? (basedpyright is always the primary type checker.)
  - **`pyrefly`** — Meta's lightweight type checker. Recommended: it has been used by this template
    longest and is stable in production.
  - **`ty`** — Astral's fast Rust type checker (complements basedpyright with a second, independent
    analysis pass; currently in beta).
- **`strictness`** (str; default `recommended`) — How strict should the toolchain be? One axis
  controls both the type-annotation requirements and the static-analysis toolchain.
  - **`none`** — pytest + ruff (minimal rules), no type checking.
  - **`basic`** — pytest + ruff, no type checking.
  - **`recommended`** — ruff (ALL rules), basedpyright + the secondary checker (pyrefly by default),
    typos/vulture/deptry/pip-audit, driven by your chosen task runner. Recommended default.
  - **`full`** — recommended + strict type checking (Any forbidden), minimized ruff ignores, full
    annotations required.

### `use_recommended_license`

Use the recommended license & metadata settings? Recommended: MIT license, no FAIR research-software metadata (CITATION.cff / REUSE).

Answer **No** to pick a different license or opt into FAIR metadata.

- **`license`** (str; default `MIT`) — Which license would you like to use? The full list from
  https://choosealicense.com, generated by tools/generate_license_template.py.
  One of: `AFL-3.0` · `Apache-2.0` · `Artistic-2.0` · `BSD-2-Clause` · `BSD-3-Clause` ·
  `BSD-3-Clause-Clear` · `BSD-4-Clause` · `0BSD` · `BSD-2-Clause-Patent` · `BlueOak-1.0.0` ·
  `BSL-1.0` · `CERN-OHL-P-2.0` · `CERN-OHL-S-2.0` · `CERN-OHL-W-2.0` · `CECILL-2.1` · `CC-BY-4.0` ·
  `CC-BY-SA-4.0` · `CC0-1.0` · `WTFPL` · `EPL-1.0` · `EPL-2.0` · `ECL-2.0` · `EUPL-1.1` · `EUPL-1.2`
  · `AGPL-3.0` · `GFDL-1.3` · `GPL-2.0` · `GPL-3.0` · `LGPL-2.1` · `LGPL-3.0` · `ISC` · `LPPL-1.3c`
  · `MIT` · `MIT-0` · `MS-PL` · `MS-RL` · `MPL-2.0` · `MulanPSL-2.0` · `ODbL-1.0` · `OSL-3.0` ·
  `PostgreSQL` · `OFL-1.1` · `Unlicense` · `UPL-1.0` · `NCSA` · `Vim` · `Zlib` · `Proprietary` ·
  `Confidential`.
- **`fair`** (bool; default no) — Add FAIR research-software metadata?
- **`author_orcid`** (str; default (empty)) — Your ORCID iD (e.g. 0000-0002-1825-0099), recorded in
  CITATION.cff so citation systems can attribute you correctly. Leave empty to skip.

### `use_recommended_integrations`

Use the recommended deployment & integration settings? Recommended: no Docker container, no PyPI auto-publish, no cloud provider, no Sentry, no MCP support, GitHub Actions for CI, structlog for logging.

Answer **No** to turn any of these on, switch the CI provider, or pick a different logging library.

- **`docker`** (bool; default no) — Would you like to publish your project in a Docker container?
  You should select this if you are making a service.
- **`pypi`** (bool; default no) — Would you like the wheel and source distribution to be
  automatically uploaded to PyPI when a release is made?
- **`cloud_provider`** (str; default `none`) — Which cloud provider will this project deploy to?
  - **`none`** — no cloud-specific code or dependencies.
  - **`aws`** — boto3 and service-specific dependencies are added.
  - **`gcp`** — google-cloud-storage is added.
  - **`azure`** — azure-identity is added.
- **`aws_services`** (str; default `essential`) — Which AWS services will you use?
  - **`essential`** — core services (S3, SQS, DynamoDB, Lambda types).
  - **`s3`** — just S3.
  - **`dynamodb`** — just DynamoDB.
  - **`sqs`** — just SQS.
  - **`lambda`** — just Lambda.
- **`include_sentry`** (bool; default no) — Would you like to include Sentry for error tracking?
- **`include_mcp`** (bool; default no) — Publish this project as an MCP (Model Context Protocol)
  server?
- **`ci_provider`** (str; default `github_actions`) — Which CI provider would you like to use?
  - **`github_actions`** — GitHub Actions workflows for lint, type-checking, tests and docs.
  - **`none`** — no CI workflows are generated.
- **`log_library`** (str; default `structlog`) — Which logging library should logging_setup.py use?
  - **`structlog`** — structured, contextvars-aware logging with console/JSON renderers. Recommended
    default.
  - **`loguru`** — batteries-included logger — no boilerplate configuration, built-in colours,
    exception-catching decorator.
  - **`picologging`** — a C-accelerated, drop-in-compatible reimplementation of the standard library
    logging module. Faster, same API.
  - **`logging`** — the standard library logging module. No extra dependency.

### `use_recommended_web_api`

Use the recommended web API stack? Recommended: a FastAPI app in a top-level `app/` package (no library <pkg>): async SQLAlchemy 2.0 + Alembic + Postgres, a demo CRUD router, request-id logging (asgi-correlation-id), a BackgroundTasks example, and /health + /docs endpoints.

Answer **No** to drop Prometheus metrics, rate limiting or CORS, or to switch the database/ORM (SQLAlchemy 2.0 + Postgres stays fixed).

- **`prometheus`** (bool; default yes) — Expose Prometheus metrics at /metrics?
- **`rate_limit`** (bool; default yes) — Apply rate limiting to the API?
- **`cors`** (bool; default yes) — Enable CORS for browser clients?

### `use_recommended_security`

Use the recommended security & compliance settings? Recommended: minimal CI permissions, GitHub Actions pinned to commit SHAs (renovate keeps them up to date), zizmor + actionlint checks, a SECURITY.md vulnerability-reporting policy, a test_qa.py that verifies dependency integrity and the public API at runtime, and a license-check task (pip-licenses --fail-on with the project's copyleft policy) that runs inside type-check.

Answer **No** to drop SECURITY.md, drop the license check, or add an OpenSSF Scorecard workflow (GitHub projects; public repos only for the badge).

- **`license_check`** (bool; default yes) — Keep the license-compliance check (pip-licenses
  --fail-on)?
- **`security_policy`** (bool; default yes) — Include a SECURITY.md vulnerability-reporting policy
  (GitHub Security Advisory workflow + response expectations)?
- **`scorecard`** (bool; default no) — Add the OpenSSF Scorecard workflow to measure supply-chain
  security and publish a badge?
<!-- END GENERATED: detailed-questions -->

## Project details

<!-- BEGIN GENERATED: project-details (tools/gen_docs.py --write) -->
| Question | Default | Asked when | Prompt |
|---|---|---|---|
| `package_name` | `my_package` | all | Name of the python import package. Must be a valid python identifier, i.e. my_package. ASCII characters only (a-z, A-Z, 0-9, _). |
| `description` | `A Python project generated from python-copier-template` | all | A short description of your project |
| `git_platform` | `github.com` | all | Git platform hosting the repository |
| `github_org` | `my-org` | `git_platform` = github.com | GitHub organisation or username that will contain this repo. Set to your GitHub username (e.g. kasi-x) for a personal repo, or the name of an… |
| `gitlab_group` | `my-group` | `git_platform` = gitlab.com | GitLab group (or username) that will contain this repo. |
| `repo_name` | `package_name \| replace('_', '-')` | all | Name of the repository. Generally the package name with underscores replaced by dashes. |
| `distribution_name` | `repo_name` | all | Name of the python distribution package that will be created. This is what people will `pip install`. |
| `author_name` | `Your Name` | all | Your full name |
| `author_email` | `you@example.com` | all | Your email address |
<!-- END GENERATED: project-details -->

The author name/email and the GitHub org have plain placeholder defaults —
answer each prompt with your own values (or pass them via `--data-file` for
non-interactive generation).
