# Web API projects

The template can generate a `web_api` project: a <lt-m v="**"/>working FastAPI scaffold<lt-m v="**"/>
with an async SQLAlchemy 2.0 + Alembic + Postgres stack, a demo CRUD router,
request-id logging, and optional Prometheus metrics, rate limiting and CORS —
all verified by generated tests.

## Why not Django?

The template deliberately does <lt-m v="**"/>not<lt-m v="**"/> maintain a Django variant. Django is a
large framework with its own ecosystem (ORM, migrations, admin, auth, Celery,
mail handling, ...) that would be a second project to maintain on top of this
one — the template's questionnaire and generated files would roughly double.

Django is not one of the `project_type` choices at all: `copier` rejects it
before anything is written (`Invalid choice for 'project_type'`), and this
template's web work is API-only. For a Django project, use
<lt-m v="["/>upstream cookiecutter-django<lt-m v="](https://github.com/cookiecutter/cookiecutter-django)"/>;
for a Python API, use this template's `web_api` type, or FastAPI / Litestar /
Flask on a `library` scaffold.

## What a web_api project includes

The recommended stack (`use_recommended_web_api` = Yes) generates:

- <lt-m v="**"/>FastAPI + uvicorn + pydantic-settings<lt-m v="**"/>. The app lives in the top-level
  `app/` package — `main.py` has a `create_app()` factory and a module-level
  `app` for uvicorn; `settings.py` reads `DATABASE_URL`, `HOST`, `PORT` and
  `CORS_ORIGINS` from the environment / `.env`.
- <lt-m v="**"/>async SQLAlchemy 2.0 + Alembic + Postgres<lt-m v="**"/>. `db.py` builds an async
  engine and session dependency; `models.py` ships a demo `Item` model;
  `alembic/` is pre-wired (async env.py reading the same settings). The demo
  CRUD router (`/api/v1/items`) shows the patterns: async session, pydantic
  schemas, `BackgroundTasks`, `GET /health`.
- <lt-m v="**"/>Request-id logging<lt-m v="**"/> (asgi-correlation-id, always on). Every request gets
  an `X-Request-ID`; `logging_setup.py` attaches it to log records.
- <lt-m v="**"/>Endpoints<lt-m v="**"/>: Swagger UI at `/docs`, OpenAPI at `/openapi.json`, health at
  `/health`. Optional: Prometheus `/metrics` (prometheus-client), slowapi rate
  limiting, CORS.
- <lt-m v="**"/>Tests<lt-m v="**"/> (`tests/test_app.py`): hit every endpoint through httpx's
  ASGITransport (no starlette TestClient, so no dependency-version warnings).
  Locally they run against a throwaway SQLite file; in CI (which starts a
  Postgres service container) they exercise the real database.
- A multi-stage <lt-m v="**"/>Dockerfile<lt-m v="**"/> whose runtime image runs
  `uvicorn app.main:app` with a `/health` HEALTHCHECK, plus
  `compose.local.yml` (API + Postgres 17) for local development.
- `.env.example` — copy to `.env` and adjust; `.env` is git-ignored and loaded
  by direnv and the compose stack.

## Running it

```sh
uv run uvicorn app.main:app --reload
# Swagger UI: http://localhost:8000/docs
```

With Docker:

```sh
docker compose -f compose.local.yml up --build   # API + Postgres
```

## Database migrations

Schema changes go through Alembic. The first migration for the demo model:

```sh
uv run alembic revision --autogenerate -m "initial"
uv run alembic upgrade head
```

After that, change `models.py` and repeat `revision --autogenerate` for each
change. Tests create tables with `Base.metadata.create_all` directly — they do
not need migrations.

## Answering No to use_recommended_web_api

The recommended stack above is fixed (FastAPI + async SQLAlchemy 2.0 +
Postgres + demo CRUD + request-id + BackgroundTasks — deliberately not a
catalogue). Answering <lt-m v="**"/>No<lt-m v="**"/> reveals three independent switches, all defaulting
to on:

- <lt-m v="**"/>Prometheus<lt-m v="**"/>: expose `/metrics` (a ~20-line prometheus-client middleware,
  not prometheus-fastapi-instrumentator — that library has repeatedly lagged
  FastAPI's routing internals, while prometheus-client itself stays stable).
- <lt-m v="**"/>Rate limiting<lt-m v="**"/>: slowapi, with a 5/minute demo limit on the list endpoint.
- <lt-m v="**"/>CORS<lt-m v="**"/>: CORSMiddleware driven by the `CORS_ORIGINS` env var
  (comma-separated). Empty means no cross-origin requests are allowed.

## Things deliberately left out (add later)

The template keeps the questionnaire minimal; the following are documented
here rather than offered as options. Each is easy to add to the generated
scaffold.

- <lt-m v="**"/>Authentication / users<lt-m v="**"/>. No auth is scaffolded. fastapi-users is in
  maintenance mode (security fixes only, no new features; its successor is in
  development), so it is not a good default to bake in. If you need auth, add
  an OIDC / SSO provider integration, or a JWT library, deliberately.
- <lt-m v="**"/>Other ORMs<lt-m v="**"/> (SQLModel, piccolo, Tortoise, ...). SQLAlchemy 2.0 + Alembic
  is the fixed default; a second ORM would double the scaffold's maintenance
  surface. The demo model is small enough to port by hand.
- <lt-m v="**"/>Admin UI<lt-m v="**"/> (SQLAdmin / FastCRUD). The demo CRUD is plain SQLAlchemy —
  ~30 lines. Add SQLAdmin when you need a human-facing admin panel, or FastCRUD
  when your CRUD endpoints multiply.
- <lt-m v="**"/>Background task queues<lt-m v="**"/> (taskiq / arq / Celery + Redis). The scaffold
  demonstrates FastAPI's built-in `BackgroundTasks` (no extra dependency, runs
  in-process after the response). Outgrow it → add a real queue.
- <lt-m v="**"/>Serverless deployment<lt-m v="**"/> (AWS Lambda / Cloud Functions). The `aws`
  answer adds boto3 and the service-specific dependencies, nothing more —
  no Lambda handler, no function memory/timeout settings, no SAM/CDK
  template. FastAPI's ASGI app is not a Lambda function handler; add an
  adapter (e.g. Mangum) and a deployment definition when you actually want
  serverless.
- <lt-m v="**"/>Caching<lt-m v="**"/> (Redis / memcached), <lt-m v="**"/>gunicorn<lt-m v="**"/> (uvicorn is fine for most
  deployments; put gunicorn in front only when you need process management),
  <lt-m v="**"/>GraphQL<lt-m v="**"/>, <lt-m v="**"/>Kafka / RabbitMQ<lt-m v="**"/>, <lt-m v="**"/>self-hosted Swagger<lt-m v="**"/> (FastAPI serves
  `/docs` itself).
