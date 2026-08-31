# Web API projects

The template can generate a `web_api` project: a Python web service with a
Dockerfile, a local Docker Compose stack (API + Postgres), a `.env.example`
for environment variables, and a CI job that runs the test suite against a
Postgres service container.

## Why not Django?

The template deliberately does **not** maintain a Django variant. Django is a
large framework with its own ecosystem (ORM, migrations, admin, auth, Celery,
mail handling, ...) that would be a second project to maintain on top of this
one — the template's questionnaire and generated files would roughly double.

If you select the `web_django` project type, generation **aborts** with a
message pointing you to the alternatives below.

## What to use instead

- **FastAPI** — async-first, great docs, first-class OpenAPI support, and the
  most direct fit for the `web_api` scaffold this template generates. Add
  `fastapi` + `uvicorn` to the project's dependencies and expose an `app`
  object.
- **Litestar** — a modern, async, opinionated framework with built-in
  validation, DI and OpenAPI.
- **Flask** — minimal and synchronous, good for small services and
  prototyping.
- If you really need Django's batteries (admin, ORM, migrations), use the
  upstream [cookiecutter-django](https://github.com/cookiecutter/cookiecutter-django)
  template, which is actively maintained and covers all of that.

## What a web_api project includes

- A `src/` layout with a CLI entry point (`python -m {{package_name}}`).
- A multi-stage `Dockerfile` (uv or pixi based) producing a runtime image.
- `compose.local.yml` — `docker compose -f compose.local.yml up --build`
  starts the API on `http://localhost:8000` with a Postgres 17 service.
- `.env.example` — copy to `.env` and adjust (`DATABASE_URL`, ...); `.env` is
  git-ignored and loaded by direnv and the compose stack.
- CI runs the same `test` task against a Postgres service container, so
  database-backed tests work on GitHub Actions without Docker.
