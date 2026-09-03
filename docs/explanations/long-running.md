# Long-running executables: the layer model

Some projects need a process that does not exit: a chat bot, an MCP server,
a long-lived worker. This page explains how the template models that kind of
code — and why it is **not** another `project_type`.

## The design question

A bot and an MCP server are "event-loop processes started with a token from
the environment". That sounds different from an HTTP server (`web_api`) or a
`cli` that prints and exits — different enough that one might ask: why isn't
there a `bot` or `daemon` project type?

The answer comes from the template's design principle for `project_type`:

> `project_type` = things whose **execution environment / build is
> fundamentally different**, or which carry a distinct competition-rules
> axis. Same-base flavours do not get their own type.

Bot / MCP / worker code runs on the **same CPython + uv environment** as a
`library`, `cli` or `web_api` project. Nothing about the interpreter, the
package build, or the dev toolchain changes — unlike MicroPython (runs on a
device, deployed with mpremote) or ROS 2 (colcon + rosdep). So by that rule
they are not new project types; they are **layers on top of an existing
type**.

## The layer model

A long-running executable is a **module with its own entry point**, generated
onto a normal project:

- the project is still a `library` / `cli` / `web_api` (its layout, packaging
  and toolchain are unchanged);
- the daemon-like code lives in its **own module** (e.g. `mcp_server.py`) with
  a **`main()` that starts the event loop**;
- it is started through its **own invocation** — `python -m <pkg>.mcp_server`
  or a dedicated `[project.scripts]` entry — never through the package's
  `__main__.py` CLI.

This keeps the two execution shapes structurally separate:

| Shape | Module | Started with | Exits |
|---|---|---|---|
| CLI | `__main__.py` | `python -m <pkg>` / `scripts.<name>` | after the command |
| Long-running | e.g. `mcp_server.py` | `python -m <pkg>.mcp_server` | when signalled |

Why not put a "daemon branch" inside `__main__.py`? Because `__main__.py`
already has owners: the Docker `ENTRYPOINT` runs the `scripts.<name>` console
script, and the generated tests run `python -m <pkg> --version`. Mixing a
token-required, never-exiting mode into that CLI would collide with both.
A separate module keeps the CLI fast to start and trivially testable, and
gives the long-running process its own argument surface (`--transport`).

## The first implementation: MCP

The template's existing `include_mcp` option is the first concrete instance
of this layer: it generates an `mcp_server.py` onto a `cli` / `web_api`
project, adds the `mcp` SDK dependency plus a `mcp-server-<name>` console
script, and starts the server with stdio (the default, driven by an MCP host
or the console script) or `--transport streamable-http` for the HTTP
transport. See the [MCP how-to](../how-to/mcp.md) for the concrete workflow.

Future platforms — Discord / Slack bots and similar — are expected to follow
the same recipe rather than grow the questionnaire:

1. an **opt-in question** under the integrations gate (like `include_mcp`),
   which adds the platform SDK and the module;
2. the bot module keeps its **own `main()`** and is started directly (and,
   for a publishable server, gets its own `[project.scripts]` entry), so the
   CLI / Docker `ENTRYPOINT` contract is untouched;
3. the token is read from the **environment** (`.env.example` documents it,
   never committed), matching how `SENTRY_DSN` / `DATABASE_URL` are handled;
4. logging goes through the generated `logging_setup.py`, so `structlog` /
   `loguru` / ... and `LOG_FORMAT=json` work unchanged inside the loop.

Keeping this out of `project_type` means the questionnaire does not multiply:
a bot that also wants the agent scaffold, Docker, or docs still gets them by
answering the same gates.
