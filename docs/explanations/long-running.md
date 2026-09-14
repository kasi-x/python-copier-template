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

## The second implementation: the chat bot (Discord / Slack)

`include_bot` (on the same `cli` / `web_api` bases) is the layer's second
implementation, and the first with its own platform axis: a
`use_recommended_bot` gate (design principle 5 — one recommendation,
No for custom) reveals `bot_platform`, whose choices are **discord**
(`discord.py`, the recommendation) and **slack** (`slack-bolt`; LINE / Gmail
are planned choices, not new questions). The generated `bot_discord.py` /
`bot_slack.py` follows the same recipe as the MCP server, point by point:

1. an **opt-in layer question** (`include_bot`) adds the platform SDK
   (`discord.py` / `slack-bolt`) and the module — one module, the platform
   the answers selected;
2. the bot module keeps its **own `main()`** and is started directly through
   its own `[project.scripts]` entry (`bot-discord-<name>` /
   `bot-slack-<name>`, `python -m <pkg>.bot_<platform>`), so the CLI / Docker
   `ENTRYPOINT` contract is untouched;
3. the token(s) are read from the **environment** (`DISCORD_BOT_TOKEN`; the
   Slack pair `SLACK_BOT_TOKEN` (xoxb-) + `SLACK_APP_TOKEN` (xapp-) —
   `.env.example` documents them, never committed) and a startup check
   refuses to start without them, naming the missing variable — the same
   refusal `mcp_server.py` makes for a public bind without
   `MCP_ALLOWED_HOSTS`;
4. logging goes through the generated `logging_setup.py`, so `structlog` /
   `loguru` / ... and `LOG_FORMAT=json` work unchanged inside the event loop;
5. a **`build_bot()` / `build_app()` + `main()` split** extends the recipe
   with a testability seam the MCP layer gets for free from its in-process
   client: the generated tests call the `/ping` callback with a fake
   interaction (Discord) or the `/app_mention` listener with a fake `say`
   (Slack) — the real object, no connection, no token.

Both platforms connect **outbound** — Discord's Gateway, Slack's Socket Mode
WebSocket — so neither publishes an inbound port, the property that makes the
layer runnable on a laptop and behind NAT. Docker (`bot-serve`, the
`mcp-serve` twin, following the selected platform's entry point and tokens)
and the token variables in `.env.example` complete the mirror. See the
[bot how-to](../how-to/bot.md) for the concrete workflow.

Further platforms — LINE / Gmail bots — are expected to follow the same
recipe rather than grow the questionnaire:

1. an **opt-in layer question**, which adds the platform SDK and the module;
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
