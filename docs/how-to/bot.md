# Discord bot layer

The template can layer a **long-running Discord bot** onto a `cli` or
`web_api` project. It is the second implementation of the
[long-running-executables layer model](../explanations/long-running.md)
(the first is the [MCP server](mcp.md)): an opt-in question that generates a
bot module with its own entry point onto an otherwise ordinary project —
never a new project type.

Answering **Yes** to `include_bot` (asked for the `cli` / `web_api` bases;
answer **No** to `use_recommended_bot` to pick the platform) generates the
[discord.py](https://discordpy.readthedocs.io) scaffold:

- `<pkg>/bot_discord.py` (or `app/bot_discord.py` on a `web_api` base) —
  a `Bot` subclass with default Gateway intents, a `/ping` slash command
  (the liveness example every platform starts with), command-tree sync on
  login, and a `build_bot()` / `main()` split so tests drive the commands
  without connecting to the Gateway. Adds the `discord.py>=2,<3` runtime
  dependency.
- a `bot-discord-<name>` console script — the dedicated entry point for the
  long-running process (`python -m <pkg>.bot_discord` works too). The CLI's
  `__main__.py`, the Docker `ENTRYPOINT` and their tests are untouched.
- `tests/test_bot_discord.py` — in-process tests: the `/ping` callback is
  driven with a fake interaction (no Gateway connection, no token), and the
  startup refusal is asserted.
- the `DISCORD_BOT_TOKEN` variable in `.env.example`, plus a `bot-serve`
  task (`docker and include_bot`) that builds the image and runs the bot
  with the token passed through from the host environment.

## Getting a Discord token

1. Create an application at <https://discord.com/developers/applications>
   (New Application).
2. Open the **Bot** tab and copy the token (**Reset Token** to see it once).
3. Copy `.env.example` to `.env` and set `DISCORD_BOT_TOKEN=<the token>`.
   `.env` is git-ignored and loaded by direnv — never commit the token.
4. Invite the bot to a server: **OAuth2 → URL Generator**, scopes
   `bot` + `applications.commands`, then open the generated URL.

## Run it

```sh
uv run bot-discord-<name>
```

Slash commands are registered on login by `setup_hook`: **globally** by
default (Discord caches global commands for up to an hour), or instantly
inside one guild for development:

```sh
uv run bot-discord-<name> --sync-guild <guild id>
```

Then type `/ping` in any channel the bot can see — it replies `pong`
(ephemerally). Logging goes through the generated `logging_setup`, so
`LOG_FORMAT=json` gives the Gateway process the same structured logs as the
CLI. With Docker: `task bot-serve` / `just bot-serve` (needs
`DISCORD_BOT_TOKEN` in the environment).

## Privileged intents and scaling

The scaffold subscribes to `discord.Intents.default()` only: **no privileged
intent** is requested, so a default bot token works with no Developer-portal
toggles and no verification friction. Turn on `members` /
`message_content` in both the portal and `_intents()` only when you actually
read member lists or message bodies.

## Non-goals

The generated bot is a working starting point, not a framework: no
moderation tooling, no databases/persistence, no scheduled tasks, no
voice, no i18n, no command catalogue. Discord-specific operational concerns
(rate-limit handling and reconnection backoff are discord.py's own, on by
default) are not re-implemented. Add the web_api layer (or any other) on
top by answering the same gates.

Slack (`slack-bolt`), LINE (`line-bot-sdk`) and Gmail
(`google-api-python-client`) are **planned platforms, not offered yet**:
they will join `bot_platform` as new choices with their own shared bodies —
no new project type, no new question axis.
