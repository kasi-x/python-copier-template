# Presets Reference

The template ships pre-configured preset files under `presets/*.yml` for use with the `architekton-py new <project> --preset <name>` CLI (or with Copier directly via `--data-file presets/<name>.yml`).

Presets define a project family by pinning only the answers essential to that family. Any question not specified in a preset takes Copier's default from `copier.yml`.

---

## Convention

- <lt-m v="**"/>Explicit answers<lt-m v="**"/>: The preset file specifies one or more answers (for example, `project_type: cli`).
- <lt-m v="**"/>Unset answers<lt-m v="**"/>: Any question omitted from the preset takes Copier's default value. When area gates (`use_recommended_*`) remain enabled (their default), recommended defaults apply across each area without additional prompts.
- <lt-m v="**"/>Update stability<lt-m v="**"/>: Recorded answers in `.copier-answers.yml` preserve these choices so that future `copier update` operations remain reproducible.

---

## Presets Comparison Table

The following table summarizes all 11 presets shipped with the template, derived directly from the files in `presets/`:

| Preset | File | Pinned Answers | Description |
| --- | --- | --- | --- |
| `library` | `presets/library.yml` | `project_type: library` | Reusable Python package (`src/` layout) with recommended defaults |
| `cli` | `presets/cli.yml` | `project_type: cli` | Command-line application with console scripts |
| `web-api` | `presets/web-api.yml` | `project_type: web_api` | FastAPI web service with PostgreSQL, Alembic, Prometheus, and rate limiting |
| `data-science` | `presets/data-science.yml` | `project_type: data_science` | Data science workspace with `notebooks/`, `data/`, `models/`, and `reports/` |
| `bare` | `presets/bare.yml` | `project_type: library`<br/>`use_recommended_integrations: false`<br/>`docker: false`<br/>`pypi: false`<br/>`cloud_provider: none`<br/>`include_sentry: false`<br/>`include_mcp: false`<br/>`ci_provider: github_actions`<br/>`log_library: structlog`<br/>`cicd_extras: false` | Minimal library: all optional infrastructure extras disabled (no devcontainer, `.vscode`, `.envrc`, renovate, or release extras) |
| `mcp-server` | `presets/mcp-server.yml` | `project_type: cli`<br/>`use_recommended_integrations: false`<br/>`docker: false`<br/>`pypi: false`<br/>`cloud_provider: none`<br/>`include_sentry: false`<br/>`include_mcp: true`<br/>`ci_provider: github_actions`<br/>`log_library: structlog`<br/>`cicd_extras: true` | Model Context Protocol server: `mcp[cli]` dependency, typed tools example at `<pkg>/mcp_server.py`, and `mcp-server-<name>` entrypoint |
| `ros2` | `presets/ros2.yml` | `project_type: ros2` | Robot Operating System 2 package (`ament_python`, `rclpy`, Humble, apt toolchain) |
| `micropython` | `presets/micropython.yml` | `project_type: micropython` | Embedded MicroPython firmware project alongside CPython tooling |
| `online-judge-atcoder` | `presets/online-judge-atcoder.yml` | `project_type: online_judge`<br/>`oj_category: competitive_coding`<br/>`oj_kind: atcoder` | Competitive programming workspace for AtCoder using `oj` + `acc` |
| `online-judge-codeforces` | `presets/online-judge-codeforces.yml` | `project_type: online_judge`<br/>`oj_category: competitive_coding`<br/>`oj_kind: codeforces` | Competitive programming workspace for Codeforces using `oj` |
| `online-judge-kattis` | `presets/online-judge-kattis.yml` | `project_type: online_judge`<br/>`oj_category: competitive_coding`<br/>`oj_kind: kattis` | Competitive programming workspace for Kattis using `submit.py` + `.kattisrc` |

---

## Preset Details

### `library`
- <lt-m v="**"/>File<lt-m v="**"/>: `presets/library.yml`
- <lt-m v="**"/>Pinned answers<lt-m v="**"/>:
  ```yaml
  project_type: library
  ```
- <lt-m v="**"/>Behavior<lt-m v="**"/>: Renders a standard Python library with a `src/` layout. All optional features take the template's recommended defaults.

### `cli`
- <lt-m v="**"/>File<lt-m v="**"/>: `presets/cli.yml`
- <lt-m v="**"/>Pinned answers<lt-m v="**"/>:
  ```yaml
  project_type: cli
  ```
- <lt-m v="**"/>Behavior<lt-m v="**"/>: Configures console script entry points and CLI argument parsing dependencies.

### `web-api`
- <lt-m v="**"/>File<lt-m v="**"/>: `presets/web-api.yml`
- <lt-m v="**"/>Pinned answers<lt-m v="**"/>:
  ```yaml
  project_type: web_api
  ```
- <lt-m v="**"/>Behavior<lt-m v="**"/>: Scaffolds a FastAPI application complete with routing, database models, migrations, and health check endpoints.

### `data-science`
- <lt-m v="**"/>File<lt-m v="**"/>: `presets/data-science.yml`
- <lt-m v="**"/>Pinned answers<lt-m v="**"/>:
  ```yaml
  project_type: data_science
  ```
- <lt-m v="**"/>Behavior<lt-m v="**"/>: Sets up an analysis and modeling directory hierarchy (`data/`, `notebooks/`, `models/`, `reports/`) alongside exploratory tools.

### `bare`
- <lt-m v="**"/>File<lt-m v="**"/>: `presets/bare.yml`
- <lt-m v="**"/>Pinned answers<lt-m v="**"/>:
  ```yaml
  project_type: library
  use_recommended_integrations: false
  docker: false
  pypi: false
  cloud_provider: none
  include_sentry: false
  include_mcp: false
  ci_provider: github_actions
  log_library: structlog
  cicd_extras: false
  ```
- <lt-m v="**"/>Behavior<lt-m v="**"/>: Minimal Python library footprint. Declines `use_recommended_integrations` and explicitly turns off CI/CD extras and integrations.
- <lt-m v="**"/>Why explicit answers are needed<lt-m v="**"/>: `cicd_extras` is only prompted when `use_recommended_integrations: false`. Answering each gated question explicitly ensures that `--defaults` does not alter the output on subsequent `copier update` passes.

### `mcp-server`
- <lt-m v="**"/>File<lt-m v="**"/>: `presets/mcp-server.yml`
- <lt-m v="**"/>Pinned answers<lt-m v="**"/>:
  ```yaml
  project_type: cli
  use_recommended_integrations: false
  docker: false
  pypi: false
  cloud_provider: none
  include_sentry: false
  include_mcp: true
  ci_provider: github_actions
  log_library: structlog
  cicd_extras: true
  ```
- <lt-m v="**"/>Behavior<lt-m v="**"/>: Generates an MCP server with `mcp[cli]` support, example tools, and executable script definitions.
- <lt-m v="**"/>Why explicit answers are needed<lt-m v="**"/>: `include_mcp` is gated behind `use_recommended_integrations`. Declining the gate and providing explicit answers ensures `include_mcp: true` is permanently recorded in `.copier-answers.yml` so that `mcp_server.py` remains active across updates.

### `ros2`
- <lt-m v="**"/>File<lt-m v="**"/>: `presets/ros2.yml`
- <lt-m v="**"/>Pinned answers<lt-m v="**"/>:
  ```yaml
  project_type: ros2
  ```
- <lt-m v="**"/>Behavior<lt-m v="**"/>: Prepares a ROS 2 package layout with `package.xml`, launch files, and setup instructions for sourcing the ROS distribution.

### `micropython`
- <lt-m v="**"/>File<lt-m v="**"/>: `presets/micropython.yml`
- <lt-m v="**"/>Pinned answers<lt-m v="**"/>:
  ```yaml
  project_type: micropython
  ```
- <lt-m v="**"/>Behavior<lt-m v="**"/>: Sets up board configurations, flashing tools, and linting rules adapted for embedded MicroPython targets.

### `online-judge-*`
- <lt-m v="**"/>Files<lt-m v="**"/>:
  - `presets/online-judge-atcoder.yml`
  - `presets/online-judge-codeforces.yml`
  - `presets/online-judge-kattis.yml`
- <lt-m v="**"/>Pinned answers<lt-m v="**"/>:
  ```yaml
  project_type: online_judge
  oj_category: competitive_coding
  oj_kind: atcoder # or codeforces, kattis
  ```
- <lt-m v="**"/>Behavior<lt-m v="**"/>: Installs platform-specific CLI harnesses and submission scaffolding for competitive programming workflows.

---

## Creating Custom Presets

To create a custom preset for your organization or team:

1. Create a YAML file (for example, `presets/my-preset.yml`).
2. Specify only the questions you want to lock in:
   ```yaml
   project_type: cli
   package_manager: uv
   ```
3. Use your preset when rendering:
   ```shell
   uvx copier copy --data-file presets/my-preset.yml \
       https://github.com/politeuma/architekton-py.git my-app
   ```
