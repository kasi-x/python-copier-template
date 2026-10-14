# The questionnaire

When you run `copier copy` (or `copier update`), the template asks a small
number of questions and generates a project tailored to your answers.

Each customisable area asks a single <lt-m v="**"/>"use the recommended settings?"<lt-m v="**"/>
question first (default: yes), with the recommendation spelled out in its help
text. Answer <lt-m v="**"/>yes<lt-m v="**"/> and that area is configured from its recommended defaults
without asking anything else; answer <lt-m v="**"/>no<lt-m v="**"/> and the detailed question(s) for
that area are asked.

Every answer can also come from a file instead of the prompt —
<lt-m v="["/>Non-interactive Generation<lt-m v="](non-interactive.md)"/> covers the flags — and
<lt-m v="["/>`example-answers.yml`<lt-m v="](https://github.com/politeuma/architekton-py/blob/main/example-answers.yml)"/>
at the template root is a ready-made starting point: it turns every area gate
off, so it spells out each detailed question that the recommended path would
otherwise leave at its default.

## Project type (`project_type`)

Asked first, ahead of every area, because the toolchain and several later
questions depend on it.

<!-- BEGIN GENERATED: project-types (architekton/gen_docs.py --write) -->
- <lt-m v="**"/>library<lt-m v="**"/> — a Python library/package.
- <lt-m v="**"/>web_api<lt-m v="**"/> — a web API service (Docker included).
- <lt-m v="**"/>cli<lt-m v="**"/> — a command-line tool.
- <lt-m v="**"/>data_science<lt-m v="**"/> — a data science project with notebooks, data/, models/, reports/ and experiment
  extras. GPU Dockerfile and Quarto paper are included.
- <lt-m v="**"/>online_judge<lt-m v="**"/> — a competitive-programming / Kaggle project. The rules for AI coding agents
  differ per judge, and the agent guide's wording defers to them.
  Questions asked when this is the base type:
  - <lt-m v="**"/>`oj_category`<lt-m v="**"/> (str; default `data_science`) — Which competition category is this project
    for?
    - <lt-m v="**"/>`data_science`<lt-m v="**"/> — Kaggle-style data competitions (GPU competition layout).
    - <lt-m v="**"/>`competitive_coding`<lt-m v="**"/> — code-submission judges (AtCoder / LeetCode / yukicoder / AOJ /
      Codeforces / Kattis / other). A bare workspace driven with oj / acc / aoj-cli / submit.py.
    - <lt-m v="**"/>`ctf`<lt-m v="**"/> — CTF competitions (participant workspace with challenges/ and a solve.py starter,
      plus pwntools / z3-solver).
  - <lt-m v="**"/>`oj_kind`<lt-m v="**"/> (str; default `'ctf' if oj_category == 'ctf' else ('atcoder' if oj_category ==
    'competitive_coding' else 'kaggle')`) — Which online judge is this project for?
    - <lt-m v="**"/>`kaggle`<lt-m v="**"/> — Kaggle competitions. GPU work is the norm and the competition layout
      (src/utils, src/input, src/output) is generated.
    - <lt-m v="**"/>`atcoder`<lt-m v="**"/> — AtCoder (Japanese competitive programming). A bare workspace driven with oj +
      acc (atcoder-cli).
    - <lt-m v="**"/>`leetcode`<lt-m v="**"/> — LeetCode-style problems. A bare workspace (LeetCode's editor is the judge; oj
      does not support it).
    - <lt-m v="**"/>`yukicoder`<lt-m v="**"/> — yukicoder (Japanese practice site). A bare workspace driven with oj
      (download / test / submit all work).
    - <lt-m v="**"/>`aoj`<lt-m v="**"/> — Aizu Online Judge (Japanese beginner courses). A bare workspace driven with
      aoj-cli (oj can download samples but not submit).
    - <lt-m v="**"/>`codeforces`<lt-m v="**"/> — Codeforces (world-scale contests). A bare workspace driven with oj
      (download / test work; submit via `oj submit` where the service allows, else the browser).
    - <lt-m v="**"/>`kattis`<lt-m v="**"/> — Kattis (open problem archive, university courses). A bare workspace driven with
      the Kattis submit client (`submit.py` with a personal `.kattisrc`; `oj download` also reads
      samples).
    - <lt-m v="**"/>`other`<lt-m v="**"/> — any other stdin/stdout judge. A bare workspace with no site-specific tooling —
      oj download/test where the service allows, else the judge's own editor.
    - <lt-m v="**"/>`ctf`<lt-m v="**"/> — CTF competitions. A participant workspace (challenges/ with a solve.py starter,
      pwntools / z3-solver via the ctf extra).
  - <lt-m v="**"/>`oj_allow_ai`<lt-m v="**"/> (bool; default no) — Is AI assistance (coding agents, code completion) allowed
    for this judge?
- <lt-m v="**"/>script<lt-m v="**"/> — a minimal script, no package layout.
- <lt-m v="**"/>ros2<lt-m v="**"/> — a ROS 2 package (ament_python or ament_cmake). Built with colcon + rosdep; not a
  uv/pixi/poetry project.
  Questions asked when this is the base type:
  - <lt-m v="**"/>`pkg_language`<lt-m v="**"/> (str; default `python`) — Which language for the ROS 2 package?
    - <lt-m v="**"/>`python`<lt-m v="**"/> — ament_python (rclpy) — setup.py + package.xml + resource/.
    - <lt-m v="**"/>`cpp`<lt-m v="**"/> — ament_cmake — CMakeLists.txt + src/*.cpp + include/.
  - <lt-m v="**"/>`ros_distro`<lt-m v="**"/> (str; default `humble`) — ROS 2 distribution. Humble (Ubuntu 22.04, Python
    3.10) is the most widely deployed; Jazzy (Ubuntu 24.04, Python 3.12) is the current LTS.
    One of: `humble` (Humble (22.04 / Python 3.10)) · `jazzy` (Jazzy (24.04 / Python 3.12)).
  - <lt-m v="**"/>`ros2_package_manager`<lt-m v="**"/> (str; default `apt`) — How should the ROS 2 environment be
    provisioned?
    - <lt-m v="**"/>`apt`<lt-m v="**"/> — the classic ROS 2 way — Ubuntu + apt (ros-{{ ros_distro }}-*) + colcon + rosdep.
      Docker base image ros:{{ ros_distro }}-ros-base.
    - <lt-m v="**"/>`pixi`<lt-m v="**"/> — RoboStack conda-forge packages via pixi, using the robostack-<distro> channel on
      prefix.dev. No sudo/apt needed. See https://pixi.prefix.dev/latest/robotics/.
- <lt-m v="**"/>micropython<lt-m v="**"/> — MicroPython firmware for a microcontroller (esp32, rp2, ...). Deployed with
  mpremote; the CPython dev toolchain (uv/ruff/pytest/basedpyright) coexists for testing and
  type-checking against micropython-<port>-stubs.
  Questions asked when this is the base type:
  - <lt-m v="**"/>`micropython_port`<lt-m v="**"/> (str; default `esp32`) — Which MicroPython port are you targeting? This
    picks the micropython-<port>-stubs package used for type-checking.
    - <lt-m v="**"/>`esp32`<lt-m v="**"/> — ESP32 family (most common; default)
    - <lt-m v="**"/>`esp8266`<lt-m v="**"/> — ESP8266 (legacy, low memory)
    - <lt-m v="**"/>`rp2`<lt-m v="**"/> — Raspberry Pi Pico / RP2040 / RP2350
    - <lt-m v="**"/>`stm32`<lt-m v="**"/> — STM32 family (Pyboard etc.)
    - <lt-m v="**"/>`samd`<lt-m v="**"/> — Microchip SAMD21 / SAMD51
    - <lt-m v="**"/>`unix`<lt-m v="**"/> — Unix port (runs on your computer — handy for testing)
    - <lt-m v="**"/>`windows`<lt-m v="**"/> — Windows port
    - <lt-m v="**"/>`mimxrt`<lt-m v="**"/> — NXP i.MX RT family (Teensy 4.x etc.)
<!-- END GENERATED: project-types -->

## Not project types (by design)

`project_type` only grows for a fundamentally different execution environment
or a distinct competition-rules axis. Everything else is a layer on an
existing type, or out of scope:

- <lt-m v="**"/>CTF<lt-m v="**"/> — same CPython environment as `library` / `cli`, so no new type.
  Two entry paths share one shape: `include_ctf` (asked for the `library` /
  `cli` bases) and `oj_category=ctf` under `online_judge`.
  Organiser scaffolds (Docker + socat + gdb) are out of scope — a
  separate-repo concern.
- <lt-m v="**"/>Ansible / Terraform / Kubernetes<lt-m v="**"/> — separate-repo concerns, not Python
  projects. IaC lives beside the app, not in this template.
- <lt-m v="**"/>Django<lt-m v="**"/> — no `project_type` of its own: `web_api` (FastAPI / Litestar /
  Flask) is the Python API type, and Django itself belongs to
  <lt-m v="["/>upstream cookiecutter-django<lt-m v="](https://github.com/cookiecutter/cookiecutter-django)"/>
  — see <lt-m v="["/>the web-api how-to<lt-m v="](../how-to/web-api.md)"/>.
- <lt-m v="**"/>SRE<lt-m v="**"/> — scoped to `web_api` hardening: non-root runtime user,
  read-only root filesystem, resource limits, `/health` probes. No
  separate observability questionnaire (metrics are the three web_api
  switches).

## Combining bases and layers

`project_type` picks the <lt-m v="**"/>base<lt-m v="**"/>; the `include_*` questions can layer another
element on top of it (same idea as the MCP layer on `cli`). The layer list,
its conditions and the recommended defaults are generated below; two things
that list cannot show:

- The added content is the same whether the matching layer comes from the base
  or from the opt-in: the `data_science` and `web_api` detail questions are
  asked whenever that layer is present.
- Answering No to `use_recommended_scraping` reveals `scraping_engine`
  (`httpx` / `scrapy` / `memorious` / `playwright` / `all`); `memorious` forces
  the project license to AGPL-3.0. See <lt-m v="["/>the scraping how-to<lt-m v="](../how-to/scraping.md)"/>
  and <lt-m v="["/>the Good-future charter<lt-m v="](../explanations/good-future.md)"/>.

`ros2` / `micropython` / code-submission judges / `script` stay single-type:
their build or execution shape cannot be combined.

## Areas and their recommended defaults

<!-- BEGIN GENERATED: areas (architekton/gen_docs.py --write) -->
Each area asks one gate question first: answering <lt-m v="**"/>Yes<lt-m v="**"/> configures it from the recommendation below, answering <lt-m v="**"/>No<lt-m v="**"/> reveals that area's detailed questions.

| Area gate | Recommended default | Asked when |
|---|---|---|
| `use_recommended_agent` | yes — a plain library / CLI without agent tooling. | library / cli |
| `use_recommended_toolchain` | uv (package manager) + just (task runner). | not ros2 + `ros2_package_manager` = pixi |
| `use_recommended_data_science` | GPU workloads enabled (NVIDIA CUDA Dockerfile + devcontainer). | the data_science layer is present |
| `use_recommended_polish` | src/ layout (library/cli), no Japanese (multibyte) characters in comments/docstrings, English AGENTS.md rule summaries. | all |
| `use_recommended_docs` | zensical (Zensical, an MkDocs fork with mkdocstrings). | all |
| `use_recommended_quality` | basedpyright (primary) + pyrefly (additional static analysis), strictness "recommended" (ruff ALL rules, typos/vulture/deptry/pip-audit). | all |
| `use_recommended_license` | MIT license, no FAIR research-software metadata (CITATION.cff / REUSE). | all |
| `use_recommended_integrations` | no Docker container, no PyPI auto-publish, no cloud provider, no Sentry, no MCP support, GitHub Actions for CI, structlog for logging. | all |
| `use_recommended_web_api` | a FastAPI app in a top-level `app/` package (no library <pkg>): async SQLAlchemy 2.0 + Alembic + Postgres, a demo CRUD router, request-id logging (asgi-correlation-id), a BackgroundTasks example, and /health + /docs endpoints. | the web_api layer is present |
| `use_recommended_security` | minimal CI permissions, GitHub Actions pinned to commit SHAs (renovate keeps them up to date), zizmor + actionlint checks, a SECURITY.md vulnerability-reporting policy, a test_qa.py that verifies dependency integrity and the public API at runtime, and a license-check task (pip-licenses --fail-on with the project's copyleft policy) that CI runs alongside type-check. | all |

An opt-in layer adds its area to a combinable base:

- <lt-m v="**"/>`include_data_science`<lt-m v="**"/> (asked when library / cli / web_api; default no) — Add the data_science
  analysis layout (notebooks/, data/, models/, reports/, Quarto paper) on top of this project?
- <lt-m v="**"/>`include_web_api`<lt-m v="**"/> (asked when library / cli / data_science / kaggle; default no) — Add the
  FastAPI scaffold (top-level app/ package) on top of this project? The web_api detail questions
  follow when answered Yes.
- <lt-m v="**"/>`include_ctf`<lt-m v="**"/> (asked when library / cli; default no) — Add a CTF participant workspace
  (challenges/<category>/<problem>/ with a solve.py exploit starter, plus pwntools and z3-solver)?
- <lt-m v="**"/>`include_scraping`<lt-m v="**"/> (asked when cli; default no) — Add a polite web-fetching layer (robots.txt
  + rate limit + cache)?
- <lt-m v="**"/>`include_bot`<lt-m v="**"/> (asked when cli / web_api / library + the web_api layer; default no) — Add a
  long-running chat bot on top of this project (the long-running layer's second platform after the
  MCP server)?

An opt-in layer asks its own gate on top:

- <lt-m v="**"/>`use_recommended_scraping`<lt-m v="**"/> (asked when a `cli` base answers Yes to `include_scraping`): httpx
  — a polite stdlib-robots fetcher (contactable User-Agent, robots.txt check, per-host rate
  limiting, on-disk cache) with offline tests.
- <lt-m v="**"/>`use_recommended_bot`<lt-m v="**"/> (asked when a `cli` / `web_api` base answers Yes to `include_bot`):
  discord = discord.py — the de-facto Discord library (async, typed, slash commands via
  app_commands, actively maintained, unlike the py-cord / nextcord forks).
<!-- END GENERATED: areas -->

## The detailed questions

<!-- BEGIN GENERATED: detailed-questions (architekton/gen_docs.py --write) -->
Answering <lt-m v="**"/>No<lt-m v="**"/> to a gate reveals that area's detailed questions:

### `use_recommended_agent`

Use the recommended agent setup (no agent tooling)? Recommended: yes — a plain library / CLI without agent tooling.

Answer <lt-m v="**"/>No<lt-m v="**"/> to add a runnable pydantic-ai example: a prompts/ directory, a typed tools/ package and an agent module wired with @agent.tool, tested offline with pydantic-ai's TestModel.

### `use_recommended_toolchain`

Use the recommended package manager & task runner? Recommended: uv (package manager) + just (task runner).

Answer <lt-m v="**"/>No<lt-m v="**"/> to pick pixi/poetry, or a different task runner.

- <lt-m v="**"/>`package_manager`<lt-m v="**"/> (str; default `'pixi' if project_type == 'ros2' and ros2_package_manager ==
  'pixi' else 'uv'`) — Which package manager would you like to use?
  - <lt-m v="**"/>`uv`<lt-m v="**"/> — Fast, pure Python package manager with a pip-like workflow.
  - <lt-m v="**"/>`pixi`<lt-m v="**"/> — Conda-based package manager with cross-language support.
  - <lt-m v="**"/>`poetry`<lt-m v="**"/> — Dependency management and packaging with Poetry.
- <lt-m v="**"/>`task_runner`<lt-m v="**"/> (str; default `just`) — Which task runner would you like to use to drive lint /
  type-check / test / docs (and, for kaggle's pipeline, the ML shortcuts)?
  - <lt-m v="**"/>`just`<lt-m v="**"/> — Just. Simple justfile, external binary.
  - <lt-m v="**"/>`task`<lt-m v="**"/> — Task (go-task). YAML, external binary, used by CI too.
  - <lt-m v="**"/>`poe`<lt-m v="**"/> — poethepoet. Pure Python, lives in pyproject.toml, no extra binary to install (just a
    dev dependency).
  - <lt-m v="**"/>`make`<lt-m v="**"/> — GNU Make. Universally available, terse Makefile syntax.
  - <lt-m v="**"/>`invoke`<lt-m v="**"/> — pyinvoke. Pure Python, tasks.py with @task-decorated functions, no extra binary
    to install (just a dev dependency).
  - <lt-m v="**"/>`duty`<lt-m v="**"/> — duty (used by pawamoy's copier-uv). Pure Python, duties.py with @duty-decorated
    functions, no extra binary to install.
- <lt-m v="**"/>`task_runner_pixi`<lt-m v="**"/> (str; default `pixi`) — Which task runner would you like to use?
  (poethepoet doesn't work with pixi, so pixi's own native tasks take its place here.)
  - <lt-m v="**"/>`pixi`<lt-m v="**"/> — pixi's own native tasks (`pixi run <name>`). No extra tool.
  - <lt-m v="**"/>`task`<lt-m v="**"/> — Task (go-task). YAML, external binary, used by CI too.
  - <lt-m v="**"/>`just`<lt-m v="**"/> — Just. Simple justfile, external binary.
  - <lt-m v="**"/>`make`<lt-m v="**"/> — GNU Make. Universally available, terse Makefile syntax.

### `use_recommended_scraping`

Use the recommended web-fetching engine? Recommended: httpx — a polite stdlib-robots fetcher (contactable User-Agent, robots.txt check, per-host rate limiting, on-disk cache) with offline tests.

Answer <lt-m v="**"/>No<lt-m v="**"/> to pick scrapy / memorious / playwright instead (or all).

- <lt-m v="**"/>`scraping_engine`<lt-m v="**"/> (str; default `httpx`) — Which web-fetching engine should the fetcher layer
  prepare?
  - <lt-m v="**"/>`httpx`<lt-m v="**"/> — polite httpx fetcher (same as recommended).
  - <lt-m v="**"/>`scrapy`<lt-m v="**"/> — a Scrapy spider starter (ROBOTSTXT_OBEY + AUTOTHROTTLE + DOWNLOAD_DELAY enforced
    in settings, offline parse test).
  - <lt-m v="**"/>`memorious`<lt-m v="**"/> — a memorious crawler config (rate-limited, cached HTTP sessions). memorious4 is
    AGPL-3.0 — choosing it requires an AGPL-3.0 project license (enforced below).
  - <lt-m v="**"/>`playwright`<lt-m v="**"/> — a Playwright browser-fetch module (Chromium via `playwright install`; robots
    precheck + rate limit reused from the fetcher; no browser launch in tests).
  - <lt-m v="**"/>`all`<lt-m v="**"/> — prepare every engine above (all runtime dependencies).

### `use_recommended_bot`

Use the recommended bot platform? Recommended: discord = discord.py — the de-facto Discord library (async, typed, slash commands via app_commands, actively maintained, unlike the py-cord / nextcord forks).

Answer <lt-m v="**"/>No<lt-m v="**"/> to pick a platform instead (discord, slack, line and gmail).

- <lt-m v="**"/>`bot_platform`<lt-m v="**"/> (str; default `discord`) — Which chat platform should the bot layer prepare?
  - <lt-m v="**"/>`discord`<lt-m v="**"/> — a discord.py bot (Gateway intents declared explicitly, a /ping app command,
    DISCORD_BOT_TOKEN from the environment with a startup check that refuses to start without it).
  - <lt-m v="**"/>`slack`<lt-m v="**"/> — a slack-bolt bot on Socket Mode (an outbound WebSocket, so there is no public
    endpoint to open or sign; an /app_mention listener that answers pong, and SLACK_BOT_TOKEN +
    SLACK_APP_TOKEN from the environment with a startup check that refuses to start without either).
  - <lt-m v="**"/>`line`<lt-m v="**"/> — a line-bot-sdk bot on the Messaging API (no long-polling and no socket, so the
    module serves LINE's webhook itself: a small FastAPI app whose POST /callback verifies the
    X-Line-Signature HMAC before answering a text ping with pong, and LINE_CHANNEL_SECRET +
    LINE_CHANNEL_ACCESS_TOKEN from the environment with a startup check that refuses to start
    without either). LINE listens on BOT_PORT (default 8000), unlike discord and slack, which only
    dial out.
  - <lt-m v="**"/>`gmail`<lt-m v="**"/> — a Gmail bot on google-api-python-client + google-auth (OAuth installed-app flow:
    the OAuth client downloaded from Google Cloud Console and the granted token are FILES, so
    GMAIL_CREDENTIALS_JSON + GMAIL_TOKEN_JSON name their paths in the environment with a startup
    check that refuses to start without either; the poll answers an unread INBOX message whose
    subject contains /ping with a pong reply on the same thread and marks it read — an outbound poll
    on GMAIL_POLL_SECONDS, so there is no Pub/Sub push endpoint to host and nothing listens, like
    discord and slack).

### `use_recommended_data_science`

Use the recommended data_science options? Recommended: GPU workloads enabled (NVIDIA CUDA Dockerfile + devcontainer).

Answer <lt-m v="**"/>No<lt-m v="**"/> to change the GPU setting.

- <lt-m v="**"/>`use_gpu`<lt-m v="**"/> (bool; default yes) — Will you run GPU workloads?

### `use_recommended_polish`

Use the recommended layout & repo polish? Recommended: src/ layout (library/cli), no Japanese (multibyte) characters in comments/docstrings, English AGENTS.md rule summaries.

Answer <lt-m v="**"/>No<lt-m v="**"/> to change the layout, allow Japanese text, or keep the AGENTS.md ethics rules Japanese-only.

- <lt-m v="**"/>`layout`<lt-m v="**"/> (str; default `src`) — Which layout would you like to use for the package?
  - <lt-m v="**"/>`src`<lt-m v="**"/> — package in a src/ directory (recommended, prevents accidental imports of an
    uninstalled package).
  - <lt-m v="**"/>`flat`<lt-m v="**"/> — package at the repository root.
- <lt-m v="**"/>`allow_japanese`<lt-m v="**"/> (bool; default no) — Allow Japanese (multibyte) characters in comments and
  docstrings?
- <lt-m v="**"/>`agents_md_language`<lt-m v="**"/> (str; default `en`) — Language of the AGENTS.md ethics rules.
  - <lt-m v="**"/>`en`<lt-m v="**"/> — an English summary of each selected guidance section sits above the ethics marker
    block; the full sections daimonion renders into the block stay Japanese (English lives in the
    sections' `en:` front matter).
  - <lt-m v="**"/>`ja`<lt-m v="**"/> — the Japanese marker block only.

### `use_recommended_docs`

Use the recommended documentation tool? Recommended: zensical (Zensical, an MkDocs fork with mkdocstrings).

Answer <lt-m v="**"/>No<lt-m v="**"/> to pick README-only, Sphinx or Great Docs instead.

- <lt-m v="**"/>`docs_type`<lt-m v="**"/> (str; default `zensical`) — Which documentation tool would you like to use?
  - <lt-m v="**"/>`README`<lt-m v="**"/> — just a README, no dedicated docs site.
  - <lt-m v="**"/>`zensical`<lt-m v="**"/> — Zensical, an MkDocs fork with mkdocstrings. Fast to set up.
  - <lt-m v="**"/>`sphinx`<lt-m v="**"/> — Sphinx with the pydata theme. More powerful, more config.
  - <lt-m v="**"/>`great-docs`<lt-m v="**"/> — Great Docs, a Quarto-based tool. Requires Quarto installed.

### `use_recommended_quality`

Use the recommended type checker & strictness level? Recommended: basedpyright (primary) + pyrefly (additional static analysis), strictness "recommended" (ruff ALL rules, typos/vulture/deptry/pip-audit).

Answer <lt-m v="**"/>No<lt-m v="**"/> to pick a different secondary checker or strictness level.

- <lt-m v="**"/>`type_checker`<lt-m v="**"/> (str; default `pyrefly`) — Which additional static-analysis checker should run
  alongside basedpyright? (basedpyright is always the primary type checker.)
  - <lt-m v="**"/>`pyrefly`<lt-m v="**"/> — Meta's lightweight type checker. Recommended: it has been used by this template
    longest and is stable in production.
  - <lt-m v="**"/>`ty`<lt-m v="**"/> — Astral's fast Rust type checker (complements basedpyright with a second, independent
    analysis pass; currently in beta).
- <lt-m v="**"/>`strictness`<lt-m v="**"/> (str; default `recommended`) — How strict should the toolchain be? One axis
  controls both the type-annotation requirements and the static-analysis toolchain.
  - <lt-m v="**"/>`none`<lt-m v="**"/> — pytest + ruff (minimal rules), no type checking.
  - <lt-m v="**"/>`basic`<lt-m v="**"/> — pytest + ruff, no type checking.
  - <lt-m v="**"/>`recommended`<lt-m v="**"/> — ruff (ALL rules), basedpyright + the secondary checker (pyrefly by default),
    typos/vulture/deptry/pip-audit, driven by your chosen task runner. Recommended default.
  - <lt-m v="**"/>`full`<lt-m v="**"/> — recommended + strict type checking (Any forbidden), minimized ruff ignores, full
    annotations required.

### `use_recommended_license`

Use the recommended license & metadata settings? Recommended: MIT license, no FAIR research-software metadata (CITATION.cff / REUSE).

Answer <lt-m v="**"/>No<lt-m v="**"/> to pick a different license or opt into FAIR metadata.

- <lt-m v="**"/>`license`<lt-m v="**"/> (str; default `MIT`) — Which license would you like to use? SPDX license
  identifiers, same set as https://choosealicense.com.
  One of: `AFL-3.0` · `Apache-2.0` · `Artistic-2.0` · `BSD-2-Clause` · `BSD-3-Clause` ·
  `BSD-3-Clause-Clear` · `BSD-4-Clause` · `0BSD` · `BSD-2-Clause-Patent` · `BlueOak-1.0.0` ·
  `BSL-1.0` · `CERN-OHL-P-2.0` · `CERN-OHL-S-2.0` · `CERN-OHL-W-2.0` · `CECILL-2.1` · `CC-BY-4.0` ·
  `CC-BY-SA-4.0` · `CC0-1.0` · `WTFPL` · `EPL-1.0` · `EPL-2.0` · `ECL-2.0` · `EUPL-1.1` · `EUPL-1.2`
  · `AGPL-3.0` · `GFDL-1.3` · `GPL-2.0` · `GPL-3.0` · `LGPL-2.1` · `LGPL-3.0` · `ISC` · `LPPL-1.3c`
  · `MIT` · `MIT-0` · `MS-PL` · `MS-RL` · `MPL-2.0` · `MulanPSL-2.0` · `ODbL-1.0` · `OSL-3.0` ·
  `PostgreSQL` · `OFL-1.1` · `Unlicense` · `UPL-1.0` · `NCSA` · `Vim` · `Zlib` · `Proprietary` ·
  `Confidential`.
- <lt-m v="**"/>`fair`<lt-m v="**"/> (bool; default no) — Add FAIR research-software metadata?
- <lt-m v="**"/>`author_orcid`<lt-m v="**"/> (str; default (empty)) — Your ORCID iD (e.g. 0000-0002-1825-0099), recorded in
  CITATION.cff so citation systems can attribute you correctly. Leave empty to skip.

### `use_recommended_integrations`

Use the recommended deployment & integration settings? Recommended: no Docker container, no PyPI auto-publish, no cloud provider, no Sentry, no MCP support, GitHub Actions for CI, structlog for logging.

Answer <lt-m v="**"/>No<lt-m v="**"/> to turn any of these on, switch the CI provider, or pick a different logging library.

- <lt-m v="**"/>`docker`<lt-m v="**"/> (bool; default no) — Would you like to publish your project in a Docker container?
  You should select this if you are making a service.
- <lt-m v="**"/>`pypi`<lt-m v="**"/> (bool; default no) — Would you like the wheel and source distribution to be
  automatically uploaded to PyPI when a release is made?
- <lt-m v="**"/>`cloud_provider`<lt-m v="**"/> (str; default `none`) — Which cloud provider will this project deploy to?
  - <lt-m v="**"/>`none`<lt-m v="**"/> — no cloud-specific code or dependencies.
  - <lt-m v="**"/>`aws`<lt-m v="**"/> — boto3 and service-specific dependencies are added.
  - <lt-m v="**"/>`gcp`<lt-m v="**"/> — google-cloud-storage is added.
  - <lt-m v="**"/>`azure`<lt-m v="**"/> — azure-identity is added.
- <lt-m v="**"/>`aws_services`<lt-m v="**"/> (str; default `essential`) — Which AWS services will you use?
  - <lt-m v="**"/>`essential`<lt-m v="**"/> — core services (S3, SQS, DynamoDB, Lambda types).
  - <lt-m v="**"/>`s3`<lt-m v="**"/> — just S3.
  - <lt-m v="**"/>`dynamodb`<lt-m v="**"/> — just DynamoDB.
  - <lt-m v="**"/>`sqs`<lt-m v="**"/> — just SQS.
  - <lt-m v="**"/>`lambda`<lt-m v="**"/> — just Lambda.
- <lt-m v="**"/>`include_sentry`<lt-m v="**"/> (bool; default no) — Would you like to include Sentry for error tracking?
- <lt-m v="**"/>`include_mcp`<lt-m v="**"/> (bool; default no) — Publish this project as an MCP (Model Context Protocol)
  server?
- <lt-m v="**"/>`ci_provider`<lt-m v="**"/> (str; default `github_actions`) — Which CI provider would you like to use?
  - <lt-m v="**"/>`github_actions`<lt-m v="**"/> — GitHub Actions workflows for lint, type-checking, tests and docs.
  - <lt-m v="**"/>`none`<lt-m v="**"/> — no CI workflows are generated.
- <lt-m v="**"/>`log_library`<lt-m v="**"/> (str; default `structlog`) — Which logging library should logging_setup.py use?
  - <lt-m v="**"/>`structlog`<lt-m v="**"/> — structured, contextvars-aware logging with console/JSON renderers. Recommended
    default.
  - <lt-m v="**"/>`loguru`<lt-m v="**"/> — batteries-included logger — no boilerplate configuration, built-in colours,
    exception-catching decorator.
  - <lt-m v="**"/>`picologging`<lt-m v="**"/> — a C-accelerated, drop-in-compatible reimplementation of the standard library
    logging module. Faster, same API.
  - <lt-m v="**"/>`logging`<lt-m v="**"/> — the standard library logging module. No extra dependency.
- <lt-m v="**"/>`cicd_extras`<lt-m v="**"/> (bool; default yes) — Include the optional project infrastructure extras? If no,
  the render stays minimal: no .devcontainer, .vscode, .envrc, renovate.json,…

### `use_recommended_web_api`

Use the recommended web API stack? Recommended: a FastAPI app in a top-level `app/` package (no library <pkg>): async SQLAlchemy 2.0 + Alembic + Postgres, a demo CRUD router, request-id logging (asgi-correlation-id), a BackgroundTasks example, and /health + /docs endpoints.

Answer <lt-m v="**"/>No<lt-m v="**"/> to drop Prometheus metrics, rate limiting or CORS, or to switch the database/ORM (SQLAlchemy 2.0 + Postgres stays fixed).

- <lt-m v="**"/>`prometheus`<lt-m v="**"/> (bool; default yes) — Expose Prometheus metrics at /metrics?
- <lt-m v="**"/>`rate_limit`<lt-m v="**"/> (bool; default yes) — Apply rate limiting to the API?
- <lt-m v="**"/>`cors`<lt-m v="**"/> (bool; default yes) — Enable CORS for browser clients?

### `use_recommended_security`

Use the recommended security & compliance settings? Recommended: minimal CI permissions, GitHub Actions pinned to commit SHAs (renovate keeps them up to date), zizmor + actionlint checks, a SECURITY.md vulnerability-reporting policy, a test_qa.py that verifies dependency integrity and the public API at runtime, and a license-check task (pip-licenses --fail-on with the project's copyleft policy) that CI runs alongside type-check.

Answer <lt-m v="**"/>No<lt-m v="**"/> to drop SECURITY.md, drop the license check, or add an OpenSSF Scorecard workflow (GitHub projects; public repos only for the badge).

- <lt-m v="**"/>`license_check`<lt-m v="**"/> (bool; default yes) — Keep the license-compliance check (pip-licenses
  --fail-on)?
- <lt-m v="**"/>`security_policy`<lt-m v="**"/> (bool; default yes) — Include a SECURITY.md vulnerability-reporting policy
  (GitHub Security Advisory workflow + response expectations)?
- <lt-m v="**"/>`scorecard`<lt-m v="**"/> (bool; default no) — Add the OpenSSF Scorecard workflow to measure supply-chain
  security and publish a badge?
<!-- END GENERATED: detailed-questions -->

## Project details

<!-- BEGIN GENERATED: project-details (architekton/gen_docs.py --write) -->
| Question | Default | Asked when | Prompt |
|---|---|---|---|
| `package_name` | `my_package` | all | Name of the python import package. Must be a valid python identifier, i.e. my_package. ASCII characters only (a-z, A-Z, 0-9, _). |
| `description` | `A Python project generated from architekton-py` | all | A short description of your project |
| `git_platform` | `github.com` | all | Git platform hosting the repository |
| `github_org` | `my-org` | `git_platform` = github.com | GitHub organisation or username that will contain this repo. Set to your GitHub username (e.g. kasi-x) for a personal repo, or the name of an… |
| `gitlab_group` | `my-group` | `git_platform` = gitlab.com | GitLab group (or username) that will contain this repo. |
| `repo_name` | `package_name \| replace('_', '-')` | all | Name of the repository. Generally the package name with underscores replaced by dashes. |
| `distribution_name` | `repo_name` | all | Name of the python distribution package that will be created. This is what people will `pip install`. |
| `author_name` | `Your Name` | all | Your full name |
| `author_email` | `you@example.com` | all | Your email address |
| `dependencies` | `derived_dependencies` | all | Runtime dependencies, as a YAML list. |
| `src_dirs` | `derived_src_dirs` | all | Directories to create under `src/`, as a YAML list. |
<!-- END GENERATED: project-details -->

The author name/email and the GitHub org have plain placeholder defaults —
answer each prompt with your own values (or pass them via `--data-file` for
non-interactive generation).

`dependencies` and `src_dirs` are <lt-m v="*"/>lists<lt-m v="*"/> whose defaults are derived from your
other answers; they are recorded in `.copier-answers.yml`, so you can edit
either one after generation instead of re-answering the questionnaire. See
<lt-m v="["/>the answers file<lt-m v="](answers-file.md#structured-answers)"/> for the workflow and
for which copier command picks an edit up.
