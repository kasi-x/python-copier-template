# Security-sensitive defaults inventory

The scaffold ships development-friendly defaults. They are safe on a
laptop and wrong in production. This page lists every security-sensitive
default by project type, the file that carries it, and what to change
before shipping. Generated projects carry the short version of the same
checklist in `AGENTS.md` ("Production security defaults").

Scope: security-sensitive *rendered defaults* (credentials, network
binds, open endpoints, permissive middleware). CI hardening (workflow
permissions, SHA pins, zizmor) lives in
[Security & compliance posture](security.md).

## How to use this page

- Before first deploy, walk the rows for your project type and confirm
  each "Change for production" cell.
- The scaffold fails closed where forgetting is likely (bot tokens, the
  MCP host allowlist): those rows say "refuses to start".
- Nothing here is a `SECRET_KEY`: the template ships no session-secret /
  JWT-secret default (there is no auth/session middleware to configure),
  so there is no signing key to rotate — the secrets below are the whole
  list.

## All project types

| Default | File | Change for production |
|---|---|---|
| `.env.example` carries only placeholders / commented values | `template/.env.example.jinja` | Copy to `.env`, fill real values there; never commit `.env` |
| `.env`, `.envs/`, `*.pem` git-ignored | `template/.gitignore.jinja`, `template/.dockerignore.jinja` | Keep ignoring them; inject prod secrets from the environment or a secret manager |
| `SENTRY_DSN` unset; `sentry_sdk.init(..., traces_sample_rate=1.0)` when `include_sentry` is on | `template/.env.example.jinja`, `template/{% if pkg_scaffold %}{{ pkg_dir }}{% endif %}/__main__.py.jinja` | Set the DSN from the environment, lower the sample rate, scrub PII before enabling |
| LLM demo keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) commented out; the offline demo needs no key | `template/.env.example.jinja` | Fill them only where the agent scaffold runs, via the environment |

## web_api

| Default | File | Change for production |
|---|---|---|
| `DATABASE_URL` points at local Postgres with `postgres:postgres` | `template/app/settings.py.jinja`, `template/.env.example.jinja` | Rotate the credential; inject the real URL from the environment / secret manager |
| `POSTGRES_PASSWORD: postgres` in the local stack and CI service | `template/compose.local.yml.jinja`, `template/.github/workflows/ci.yml.jinja` | Local/CI only — never reuse for production data |
| `alembic.ini` carries no URL; `env.py` reads app settings | `template/alembic/alembic.ini.jinja`, `template/alembic/env.py.jinja` | Rotating `DATABASE_URL` covers migrations too |
| Binds `0.0.0.0:8000` (settings default, Dockerfile `ENV`, compose `command`) | `template/app/settings.py.jinja`, `template/Dockerfile.jinja`, `template/compose.local.yml.jinja` | Keep behind TLS termination + firewall; do not publish beyond the reverse proxy |
| CORS deny-by-default (`cors_origins: []`, no middleware) when `cors` is on | `template/app/settings.py.jinja`, `template/app/main.py.jinja` | Set `CORS_ORIGINS` to exact origins, never `*` (`allow_credentials` is on) |
| `GET /docs`, `GET /openapi.json` served by default | `template/app/main.py.jinja` (`FastAPI(...)`) | Restrict or disable in production |
| `GET /health` unauthenticated, DB-independent | `template/app/routers/health.py.jinja` | Keep it (orchestrator probe); keep sensitive data out of it |
| `GET /metrics` unauthenticated when `prometheus` is on | `template/app/metrics.py.jinja` | Scrape on a private interface or protect it |
| Demo list endpoint `5/minute` per IP (`slowapi`, `get_remote_address`); nothing when `rate_limit` is off | `template/app/routers/items.py.jinja`, `template/app/rate_limit.py.jinja` | Set per-endpoint limits; behind a proxy, forward the client IP so the key is the caller |
| `uvicorn ... --reload` in the guide/README is the dev loop | `template/AGENTS.md.jinja`, `template/README.md.jinja` | Run production uvicorn without `--reload` (the Dockerfile/ compose `ENTRYPOINT` already does) |
| Runtime image runs as non-root `appuser`, read-only root FS in compose | `template/Dockerfile.jinja`, `template/compose.local.yml.jinja` | Keep; add dropped capabilities / seccomp where your platform supports it |

## MCP (`include_mcp` on cli / web_api)

| Default | File | Change for production |
|---|---|---|
| stdio transport, localhost-only HTTP bind | `partials/mcp_server.py.jinja` | Keep stdio unless you need HTTP |
| Non-local `--host` (e.g. `0.0.0.0` in Docker) requires `MCP_ALLOWED_HOSTS` — refuses to start without it | `partials/mcp_server.py.jinja`, `template/Dockerfile.jinja` | Set the exact host allowlist + `MCP_ALLOWED_ORIGINS` |
| `GET /health` unauthenticated | `partials/mcp_server.py.jinja` | Keep it (orchestrator probe); keep sensitive data out of it |

## Bots (`include_bot` on cli / web_api)

| Default | File | Change for production |
|---|---|---|
| `DISCORD_BOT_TOKEN` required — refuses to start without it | `partials/bot-discord.py.jinja` | Inject from the environment; never bake into the image |
| `SLACK_BOT_TOKEN` (xoxb-) + `SLACK_APP_TOKEN` (xapp-) required — refuses to start without either | `partials/bot-slack.py.jinja` | Same; Socket Mode is an outbound WebSocket (no listening port) |
| `LINE_CHANNEL_SECRET` + `LINE_CHANNEL_ACCESS_TOKEN` required — refuses to start without either; missing secret fails webhooks closed (HTTP 500, no reply) | `partials/bot-line.py.jinja` | Same; webhook listens on all interfaces (`BOT_PORT`, default 8000) — expose over HTTPS only |
| `GMAIL_CREDENTIALS_JSON` / `GMAIL_TOKEN_JSON` required file paths — refuses to start without either | `partials/bot-gmail.py.jinja` | Mount read-only (e.g. `/run/secrets/`); the token file IS the inbox; both git-ignored (`partials/gitignore-gmail.jinja`) |

## Scraping (`include_scraping` on cli)

| Default | File | Change for production |
|---|---|---|
| `FETCHER_CONTACT` placeholder (`contact@example.com`) in the User-Agent | `partials/fetcher-httpx.py.jinja`, `template/.env.example.jinja` | Set a reachable address before any real crawl |
| 1 req/s per host floor, robots.txt, disk cache | `partials/fetcher-httpx.py.jinja`, `template/CHARTER.md.jinja` | Keep; confirm per-source (see `LEGAL.md`) |
| Cache / browser profiles git-ignored (`.cache/fetcher/`, `.cache/ms-playwright/`) | `partials/gitignore-scraping.jinja` | Keep harvests out of git |

## MicroPython

| Default | File | Change for production |
|---|---|---|
| `boot.py` shows a `wlan.connect("SSID", "password")` placeholder | `template/firmware/boot.py.jinja` | Never commit real Wi-Fi credentials; provision per device |

## Online judge / CTF

| Default | File | Change for production |
|---|---|---|
| `.kattisrc` + downloaded `test/` cases git-ignored | `partials/gitignore-oj.jinja` | Never commit submission tokens or harvested cases |
| `challenges/**/vuln`, `challenges/**/flag*` git-ignored | `partials/gitignore-ctf.jinja` | Never commit targets or flags |
