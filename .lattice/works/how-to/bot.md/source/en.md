# Chat bot layer (Discord / Slack / LINE / Gmail)

The template can layer a <lt-m v="**"/>long-running chat bot<lt-m v="**"/> onto a `cli` or `web_api`
project. It is the second implementation of the
<lt-m v="["/>long-running-executables layer model<lt-m v="](../explanations/long-running.md)"/>
(the first is the <lt-m v="["/>MCP server<lt-m v="](mcp.md)"/>): an opt-in question that generates a
bot module with its own entry point onto an otherwise ordinary project —
never a new project type.

Answering <lt-m v="**"/>Yes<lt-m v="**"/> to `include_bot` (asked for the `cli` / `web_api` bases)
generates the <lt-m v="**"/>discord<lt-m v="**"/> scaffold, the recommended platform. Answer <lt-m v="**"/>No<lt-m v="**"/>
to `use_recommended_bot` to pick from `bot_platform`, whose other choices are
<lt-m v="**"/>slack<lt-m v="**"/>, <lt-m v="**"/>line<lt-m v="**"/> and <lt-m v="**"/>gmail<lt-m v="**"/>:

| `bot_platform` | Module | Runtime dependency | Credentials |
|---|---|---|---|
| `discord` (recommended) | `bot_discord.py` | `discord.py>=2,<3` | `DISCORD_BOT_TOKEN` |
| `slack` | `bot_slack.py` | `slack-bolt>=1.21,<2` | `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` |
| `line` | `bot_line.py` | `line-bot-sdk>=3,<4` + `fastapi` / `uvicorn[standard]` | `LINE_CHANNEL_SECRET` + `LINE_CHANNEL_ACCESS_TOKEN` |
| `gmail` | `bot_gmail.py` | `google-api-python-client` + `google-auth` + `google-auth-oauthlib` | `GMAIL_CREDENTIALS_JSON` + `GMAIL_TOKEN_JSON` (paths to the two OAuth JSON files) |

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

Three of the four generated platforms reach their service over an
<lt-m v="**"/>outbound<lt-m v="**"/> connection, so none needs a public endpoint: Discord over the
Gateway, Slack over Socket Mode, Gmail by polling the INBOX. That is the
property the MCP stdio transport has too, and the reason those three work on
a laptop and behind NAT. LINE is the exception — the Messaging API can only
push, so its bot serves a webhook.

## Discord

### Getting a Discord token

1. Create an application at <https://discord.com/developers/applications>
   (New Application).
2. Open the <lt-m v="**"/>Bot<lt-m v="**"/> tab and copy the token (<lt-m v="**"/>Reset Token<lt-m v="**"/> to see it once).
3. Copy `.env.example` to `.env` and set `DISCORD_BOT_TOKEN=<the token>`.
   `.env` is git-ignored and loaded by direnv — never commit the token.
4. Invite the bot to a server: <lt-m v="**"/>OAuth2 → URL Generator<lt-m v="**"/>, scopes
   `bot` + `applications.commands`, then open the generated URL.

### Run it

```sh
uv run bot-discord-<name>
```

Slash commands are registered on login by `setup_hook`: <lt-m v="**"/>globally<lt-m v="**"/> by
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

Slack splits the credential in two: a <lt-m v="**"/>bot token<lt-m v="**"/> authorizes the Web API
calls the listeners make (`say()` posts a message), and an <lt-m v="**"/>app-level token<lt-m v="**"/>
opens the Socket Mode connection. The scaffold refuses to start without either
and names the missing one.

1. Create the app at <https://api.slack.com/apps> → <lt-m v="**"/>Create New App<lt-m v="**"/> →
   <lt-m v="**"/>From scratch<lt-m v="**"/> (pick the workspace).
2. <lt-m v="**"/>Socket Mode<lt-m v="**"/> → toggle it on. Slack offers to generate an **app-level
   token** for you; it needs the `connections:write` scope. That `xapp-…`
   value is `SLACK_APP_TOKEN`.
3. <lt-m v="**"/>OAuth & Permissions<lt-m v="**"/> → <lt-m v="**"/>Scopes → Bot Token Scopes<lt-m v="**"/> → add
   `app_mentions:read` (receive `@mentions`) and `chat:write` (post the
   reply). Then <lt-m v="**"/>Install to Workspace<lt-m v="**"/> and copy the **Bot User OAuth
   Token** `xoxb-…` as `SLACK_BOT_TOKEN`.
4. <lt-m v="**"/>Event Subscriptions<lt-m v="**"/> → toggle it on → <lt-m v="**"/>Subscribe to bot events<lt-m v="**"/> →
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

## LINE

### Getting the two LINE credentials

LINE splits the credential the same way Slack does, but along a different
axis: a <lt-m v="**"/>channel secret<lt-m v="**"/> verifies the webhook, and a **channel access
token** authorizes the Messaging API calls the bot makes when it replies. The
scaffold refuses to start without either and names the missing one.

1. Create a provider and a <lt-m v="**"/>Messaging API<lt-m v="**"/> channel at
   <https://developers.line.biz/console/>.
2. <lt-m v="**"/>Messaging API<lt-m v="**"/> tab → <lt-m v="**"/>Channel access token (long-lived)<lt-m v="**"/> → issue one.
   That value is `LINE_CHANNEL_ACCESS_TOKEN`.
3. <lt-m v="**"/>Basic settings<lt-m v="**"/> tab → <lt-m v="**"/>Channel secret<lt-m v="**"/>. That value is
   `LINE_CHANNEL_SECRET`; it is what LINE signs every webhook body with.
4. Copy `.env.example` to `.env` and set both variables. `.env` is
   git-ignored and loaded by direnv — never commit either value. A leaked
   access token sends messages as your channel; a leaked channel secret lets
   anyone forge a webhook.
5. Add the bot as a friend (the channel's QR code is on the <lt-m v="**"/>Messaging API<lt-m v="**"/>
   tab). A LINE user can only message a bot they added.

### Run it

```sh
uv run bot-line-<name>
```

Unlike the other two platforms this one listens: the bot serves
`POST /callback` on `BOT_PORT` (default 8000, all interfaces), so it needs an
HTTPS URL LINE can reach. Deploy it behind a reverse proxy, or tunnel to it
while developing:

```sh
cloudflared tunnel --url http://localhost:8000   # or: ngrok http 8000
```

Then, on the <lt-m v="**"/>Messaging API<lt-m v="**"/> tab:

1. <lt-m v="**"/>Webhook settings<lt-m v="**"/> → <lt-m v="**"/>Webhook URL<lt-m v="**"/>:
   `https://<that host>/callback` → <lt-m v="**"/>Verify<lt-m v="**"/> (LINE sends a signed test
   request; the scaffold answers it, so the check passes).
2. <lt-m v="**"/>Use webhook<lt-m v="**"/> → on, and turn <lt-m v="**"/>Auto-reply messages<lt-m v="**"/> off so the
   channel's canned replies do not answer first.
3. Send the bot `ping` in the chat — it replies `pong`.

Logging goes through the generated `logging_setup`, so `LOG_FORMAT=json`
gives the webhook process the same structured logs as the CLI. With Docker:
`task bot-serve` / `just bot-serve` (needs both credentials in the
environment; this is the one bot container that publishes a port — `8000`).

### Why the signature check is what makes a public URL safe

The webhook URL is public by design: LINE has to reach it, so anyone who
learns it can POST to `/callback`. What separates LINE from a forger is the
channel secret, which never travels over the wire. LINE sends the base64
HMAC-SHA256 of the raw request body in the `X-Line-Signature` header, and the
scaffold's `WebhookParser` recomputes it over the exact bytes received and
rejects the request — `400`, no reply, no event parsed — when it does not
match. An unsigned body and a body signed with the wrong secret are both that
same 400.

`tests/test_bot_line.py` asserts exactly that, plus the happy path: a
correctly signed `ping` gets the `pong` reply, the two forged bodies get
rejected without a single reply call, and the startup refusal names the
missing credential. `build_app()` is split from `main()` and takes the reply
call as a parameter, so the whole route — signature check included — runs
in-process over httpx's `ASGITransport` with a recording reply: no token, no
client, no network. (The transport is httpx's rather than starlette's
`TestClient` for the reason `tests/test_app.py` documents: the generated
project sets `filterwarnings = error`, and starlette 1.x deprecates httpx
inside `TestClient`.)

## Gmail

### Getting the two Gmail credential files

Gmail splits the credential like Slack and LINE do, but into <lt-m v="**"/>files<lt-m v="**"/>
instead of environment strings: the OAuth <lt-m v="*"/>client<lt-m v="*"/> identifies the
application, and the granted <lt-m v="*"/>token<lt-m v="*"/> is the inbox itself. The scaffold
refuses to start without either path in the environment and names the
missing one.

1. In Google Cloud Console (<https://console.cloud.google.com/>), create a
   project and enable the <lt-m v="**"/>Gmail API<lt-m v="**"/> (APIs & Services → Library). While
   the app is unpublished, add your own account as a <lt-m v="**"/>test user<lt-m v="**"/> on the
   OAuth consent screen.
2. **APIs & Services → Credentials → Create credentials → OAuth client ID →
   Desktop app**, download the JSON, and keep it as `credentials.json` (the
   repo root is the convention; both names are git-ignored). That path is
   `GMAIL_CREDENTIALS_JSON`.
3. Copy `.env.example` to `.env` and set `GMAIL_TOKEN_JSON=token.json` — the
   file does not exist yet; the first run writes it. Never commit either
   file: the token IS the inbox. The generated `.gitignore` covers both the
   way it covers CTF `flag*` files.
4. Scope: the scaffold asks for `gmail.modify` only — read, send and label
   edit, everything the poll needs, nothing more.

### Run it

```sh
uv run bot-gmail-<name>
```

The first run opens a browser once for consent and writes `token.json`;
every later run refreshes the stored grant, so nothing sits between `uv
run` and the mailbox. The bot then polls every `GMAIL_POLL_SECONDS`
(default 60): each unread INBOX message whose subject contains `/ping`
gets a `pong` reply on its own thread and is marked read — which is what
makes the poll answer each ping exactly once. Mail that never says `/ping`
is left unread: the bot never hides a human's mail. Logging goes through
the generated `logging_setup`, so `LOG_FORMAT=json` gives the poll loop
the same structured logs as the CLI. With Docker: `task bot-serve` /
`just bot-serve` (the credential files are mounted read-only into the
container; consent once on the host first).

Why polling and not Pub/Sub push? Push would need a public HTTPS endpoint
to receive at — infrastructure to host and verify. Polling is an outbound
call, the same self-contained property the other dial-out platforms have,
at the cost of the interval's latency instead of push immediacy.

`poll_once()` takes the API client as a parameter, the seam the tests
fake: `tests/test_bot_gmail.py` hands it a recording stand-in for the
discovery client and asserts the exact call set — `list`, `get`, `send`,
`modify` — decoding the RFC 2822 reply bytes right in the test.
`build_service()` is split from `main()` like every platform's
`build_*()`; the OAuth dance is the only part that cannot run offline,
and it is the only part the tests skip.

## Non-goals

The generated bots are working starting points, not frameworks: no moderation
tooling, no databases/persistence, no scheduled tasks, no voice, no i18n, no
command catalogue. Platform-specific operational concerns (rate-limit handling
and reconnection backoff are discord.py's / Bolt's / line-bot-sdk's own, on by
default; the Gmail poller simply retries on the next tick) are not
re-implemented. Add the web_api layer (or any other) on top by answering the
same gates.
