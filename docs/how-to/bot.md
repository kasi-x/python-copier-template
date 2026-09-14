# Chat bot layer (Discord / Slack)

The template can layer a **long-running chat bot** onto a `cli` or `web_api`
project. It is the second implementation of the
[long-running-executables layer model](../explanations/long-running.md)
(the first is the [MCP server](mcp.md)): an opt-in question that generates a
bot module with its own entry point onto an otherwise ordinary project —
never a new project type.

Answering **Yes** to `include_bot` (asked for the `cli` / `web_api` bases)
generates the **discord** scaffold, the recommended platform. Answer **No**
to `use_recommended_bot` to pick from `bot_platform`, whose second choice is
**slack**:

| `bot_platform` | Module | Runtime dependency | Tokens |
|---|---|---|---|
| `discord` (recommended) | `bot_discord.py` | `discord.py>=2,<3` | `DISCORD_BOT_TOKEN` |
| `slack` | `bot_slack.py` | `slack-bolt>=1.21,<2` | `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` |

Whichever platform is selected, the layer ships:

- `<pkg>/bot_<platform>.py` (or `app/bot_<platform>.py` on a `web_api` base) —
  the platform's client configured in `build_*()`, a listener that answers
  `pong` (the liveness example every platform starts with), and a `main()`
  split so tests drive the listener without connecting. Adds the platform's
  runtime dependency.
- a `bot-<platform>-<name>` console script — the dedicated entry point for
  the long-running process (`python -m <pkg>.bot_<platform>` works too). The
  CLI's `__main__.py`, the Docker `ENTRYPOINT` and their tests are untouched.
- `tests/test_bot_<platform>.py` — in-process tests: the listener is driven
  with a fake client (no connection, no token, no network), and the startup
  refusal is asserted.
- the token variable(s) in `.env.example`, plus a `bot-serve` task (`docker
  and include_bot`) that builds the image and runs the bot with the tokens
  passed through from the host environment. The task follows the selected
  platform: one entry point, one token set.

Both generated platforms reach their service over an **outbound** connection,
so neither needs a public endpoint: Discord over the Gateway, Slack over
Socket Mode. That is the property the MCP stdio transport has too, and the
reason the layer works on a laptop and behind NAT.

## Discord

### Getting a Discord token

1. Create an application at <https://discord.com/developers/applications>
   (New Application).
2. Open the **Bot** tab and copy the token (**Reset Token** to see it once).
3. Copy `.env.example` to `.env` and set `DISCORD_BOT_TOKEN=<the token>`.
   `.env` is git-ignored and loaded by direnv — never commit the token.
4. Invite the bot to a server: **OAuth2 → URL Generator**, scopes
   `bot` + `applications.commands`, then open the generated URL.

### Run it

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

### Privileged intents and scaling

The scaffold subscribes to `discord.Intents.default()` only: **no privileged
intent** is requested, so a default bot token works with no Developer-portal
toggles and no verification friction. Turn on `members` /
`message_content` in both the portal and `_intents()` only when you actually
read member lists or message bodies.

## Slack

### Getting the two Slack tokens

Slack splits the credential in two: a **bot token** authorizes the Web API
calls the listeners make (`say()` posts a message), and an **app-level token**
opens the Socket Mode connection. The scaffold refuses to start without either
and names the missing one.

1. Create the app at <https://api.slack.com/apps> → **Create New App** →
   **From scratch** (pick the workspace).
2. **Socket Mode** → toggle it on. Slack offers to generate an **app-level
   token** for you; it needs the `connections:write` scope. That `xapp-…`
   value is `SLACK_APP_TOKEN`.
3. **OAuth & Permissions** → **Scopes → Bot Token Scopes** → add
   `app_mentions:read` (receive `@mentions`) and `chat:write` (post the
   reply). Then **Install to Workspace** and copy the **Bot User OAuth
   Token** `xoxb-…` as `SLACK_BOT_TOKEN`.
4. **Event Subscriptions** → toggle it on → **Subscribe to bot events** →
   add `app_mention`. Socket Mode delivers these over the socket, so no
   Request URL is involved (and no request signing secret to configure).
5. Copy `.env.example` to `.env` and set both variables. `.env` is
   git-ignored and loaded by direnv — never commit either token. Both are
   secrets: a leaked `xoxb-` posts as your bot, a leaked `xapp-` opens your
   socket.
6. Invite the bot to a channel you will use: `/invite @your-bot`. A bot only
   receives mentions in channels it is a member of.

### Run it

```sh
uv run bot-slack-<name>
```

Socket Mode connects out to Slack, so nothing listens on a port and there is
nothing to expose (the generated Dockerfile therefore adds no `EXPOSE` for
it). Mention the bot — `@your-bot ping` — in a channel it is in, and it
replies `pong`. Logging goes through the generated `logging_setup`, so
`LOG_FORMAT=json` gives the socket process the same structured logs as the
CLI; Bolt keeps its own stdlib loggers, the way the Discord module leaves
discord.py's alone. With Docker: `task bot-serve` / `just bot-serve` (needs
both `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in the environment).

`register_listeners()` is split from `build_app()` and `main()`:
`tests/test_bot_slack.py` registers the listeners on a recording stand-in for
`slack_bolt.App` and calls the mention listener with a fake `say` — no token,
no `WebClient`, no socket. `build_app(token=...)` passes
`token_verification_enabled=False`, because `App` would otherwise call
`auth.test` while the app is being built.

## Non-goals

The generated bots are working starting points, not frameworks: no moderation
tooling, no databases/persistence, no scheduled tasks, no voice, no i18n, no
command catalogue. Platform-specific operational concerns (rate-limit handling
and reconnection backoff are discord.py's / Bolt's own, on by default) are not
re-implemented. Add the web_api layer (or any other) on top by answering the
same gates.

LINE (`line-bot-sdk`, Webhook signature verification) and Gmail
(`google-api-python-client` + OAuth) are **planned platforms, not offered
yet**: they will join `bot_platform` as new choices with their own shared
bodies — no new project type, no new question axis.
