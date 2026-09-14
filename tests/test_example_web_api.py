"""web_api: the FastAPI scaffold, its docker/compose/env plumbing, the
cloud-provider dependency sets, and the guards that keep app/ out of the other
project types."""

import tomllib
from pathlib import Path

import pytest

from support import copy_project
from support import make_venv


def test_template_web_api_sphinx_docs(tmp_path: Path):
    """web_api has no <pkg> library: the Sphinx docs and the dist CI check
    must target the app import root, not the (unused) package_name."""
    copy_project(
        tmp_path,
        project_type="web_api",
        use_recommended_docs=False,
        docs_type="sphinx",
    )
    conf = (tmp_path / "docs" / "conf.py").read_text()
    assert "import app" in conf
    assert "release = app.__version__" in conf
    assert "import python_copier_template_example" not in conf
    # The switcher probe must not break offline docs builds
    assert "except requests.RequestException" in conf
    api_rst = (tmp_path / "docs" / "_api.rst").read_text()
    assert "\n    app\n" in api_rst
    assert "<_api/app>" in (tmp_path / "docs" / "reference.md").read_text()
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert 'version-command: python -c "import app; print(app.__version__)"' in ci


def test_template_cloud_provider_aws(tmp_path: Path):
    copy_project(tmp_path, project_type="web_api", cloud_provider="aws", aws_services="s3")
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert any(d.startswith("boto3") for d in deps)
    assert any(d.startswith("botocore") for d in deps)
    dev = pyproject_toml["dependency-groups"]["dev"]
    assert any("boto3-stubs[s3]" in d for d in dev)


def test_template_cloud_provider_gcp(tmp_path: Path):
    copy_project(tmp_path, project_type="web_api", cloud_provider="gcp")
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert any(d.startswith("google-cloud-storage") for d in deps)


def test_template_cloud_provider_azure(tmp_path: Path):
    copy_project(tmp_path, project_type="web_api", cloud_provider="azure")
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert any(d.startswith("azure-identity") for d in deps)


def test_template_no_docker_has_no_docs_and_works(tmp_path: Path):
    copy_project(tmp_path, docker=False)
    # The devcontainer-only Dockerfile is always shipped, but with docker off
    # it has no build/runtime stages and no container how-to in the docs.
    container_doc = tmp_path / "docs" / "how-to" / "run-container.md"
    assert not container_doc.exists()
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "AS build" not in dockerfile
    assert "AS runtime" not in dockerfile
    assert "docker run" not in (tmp_path / "README.md").read_text()


@pytest.mark.parametrize("package_manager", ["uv", "pixi"])
def test_web_api_ships_env_and_compose(tmp_path: Path, package_manager: str):
    copy_project(tmp_path, project_type="web_api", docker=True, package_manager=package_manager)
    # cookiecutter-django style additions
    assert (tmp_path / ".editorconfig").exists()
    assert (tmp_path / ".env.example").exists()
    assert (tmp_path / ".dockerignore").exists()
    assert (tmp_path / "compose.local.yml").exists()
    # The compose file wires up the API + postgres
    compose = (tmp_path / "compose.local.yml").read_text()
    assert "postgres" in compose
    assert "8000:8000" in compose
    # least privilege: read-only rootfs (writable /tmp + $HOME cache tmpfs)
    # with real local-dev caps (plain `compose up` ignores `deploy`)
    assert "read_only: true" in compose
    assert "- /tmp" in compose
    assert ".cache" in compose
    assert "mem_limit: 512M" in compose
    assert "deploy:" not in compose
    # the runtime image runs as a non-root user owning its workdir
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "USER appuser" in dockerfile
    assert "chown appuser" in dockerfile
    assert "PYTHONDONTWRITEBYTECODE" in dockerfile
    # USER comes after the runtime COPY/WORKDIR it locks down
    assert dockerfile.index("COPY --from=build") < dockerfile.index("USER appuser")
    # .env is git-ignored
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".env" in gitignore


def test_web_api_recommended_fastapi_stack(tmp_path: Path):
    """The recommended web_api path ships a working FastAPI scaffold.

    example-answers.yml sets use_recommended_web_api=false, so the detailed
    questions (prometheus / rate_limit / cors) all default to true — this is
    the full-stack render.
    """
    copy_project(tmp_path, project_type="web_api", docker=True)
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    for expected in ("fastapi", "uvicorn", "sqlalchemy", "alembic", "asyncpg", "asgi-correlation-id"):
        assert any(expected in d for d in deps), f"{expected} missing from {deps}"
    # optional observability / protection deps (all default on)
    assert any("prometheus-client" in d for d in deps)
    assert any("slowapi" in d for d in deps)

    pkg = tmp_path / "app"
    # app factory + settings + db + demo model/schemas/router live in the
    # top-level app/ package (web_api has no <pkg> library).
    for rel in (
        "main.py",
        "settings.py",
        "db.py",
        "models.py",
        "schemas.py",
        "router.py",
        "routers/health.py",
        "routers/items.py",
    ):
        assert (pkg / rel).exists(), f"{rel} not generated"
    main = (pkg / "main.py").read_text()
    assert "create_app" in main
    assert "CorrelationIdMiddleware" in main
    assert "app = create_app()" in main
    # uvicorn entrypoint + healthcheck in the Dockerfile
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "uvicorn" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    # alembic pre-wired at the repo root
    assert (tmp_path / "alembic" / "env.py").exists()
    assert (tmp_path / "alembic" / "alembic.ini").exists()
    # generated HTTP tests exercise the endpoints
    test_app = (tmp_path / "tests" / "test_app.py").read_text()
    assert "ASGITransport" in test_app
    assert "/health" in test_app


def test_web_api_detail_options_off(tmp_path: Path):
    """use_recommended_web_api=false + all three switches off: minimal stack.

    FastAPI itself stays (it is the recommended base), but no /metrics,
    no slowapi, no CORS middleware, and the conditional modules are absent.
    """
    copy_project(
        tmp_path,
        project_type="web_api",
        docker=True,
        use_recommended_web_api=False,
        prometheus=False,
        rate_limit=False,
        cors=False,
    )
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert any("fastapi" in d for d in deps)
    assert not any("prometheus" in d for d in deps)
    assert not any("slowapi" in d for d in deps)

    pkg = tmp_path / "app"
    assert (pkg / "main.py").exists()
    main = (pkg / "main.py").read_text()
    assert "metrics" not in main
    assert "slowapi" not in main
    assert "CORS" not in main
    # conditional modules are not generated
    assert not (pkg / "metrics.py").exists()
    assert not (pkg / "rate_limit.py").exists()


def test_web_api_not_offered_to_other_types(tmp_path: Path):
    """FastAPI deps and app/ code must not leak into other project types.

    Force the detail answers on a library without the combo opt-in — the
    *_effective variables must keep them out.
    """
    copy_project(
        tmp_path,
        project_type="library",
        docker=True,
        use_recommended_web_api=False,
        prometheus=True,
        rate_limit=True,
        cors=True,
    )
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert not any("fastapi" in d for d in deps)
    assert not any("slowapi" in d for d in deps)
    assert not any("prometheus" in d for d in deps)
    assert not (tmp_path / "src" / "python_copier_template_example" / "app").exists()
    assert not (tmp_path / "alembic").exists()
    assert not (tmp_path / "tests" / "test_app.py").exists()


@pytest.mark.heavy
@pytest.mark.network
def test_template_web_api_runs_in_process(tmp_path: Path):
    """The generated FastAPI scaffold must actually work: sync the project,
    run the HTTP tests (SQLite fallback), and keep it ruff/basedpyright-clean
    — the same gates the generated project's own CI applies."""
    copy_project(tmp_path, project_type="web_api", docker=True)
    run = make_venv(tmp_path)
    run("uv run --locked pytest -q")
    run("uv run --locked ruff check .")
    run("uv run --locked basedpyright")


def test_web_api_ci_postgres_service(tmp_path: Path):
    # Without docker, the CI test job gets a postgres service container
    copy_project(tmp_path, project_type="web_api", docker=False)
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "postgres" in ci
    assert "postgres-host: localhost" in ci
    assert "postgres:17-alpine" in ci
    # No compose file when docker is off
    assert not (tmp_path / "compose.local.yml").exists()
    assert not (tmp_path / ".dockerignore").exists()


def test_library_no_web_api_extras(tmp_path: Path):
    # A plain library should not get the web_api-only compose/env additions
    copy_project(tmp_path, project_type="library", docker=False)
    assert not (tmp_path / "compose.local.yml").exists()
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "postgres" not in ci
    # .editorconfig is always shipped; .env.example is gated on features
    # that consume env vars (web_api/mcp/scraping/sentry/agent) -- a plain
    # library with no env-var consumers gets no env scaffolding.
    assert not (tmp_path / ".env.example").exists()
    assert (tmp_path / ".editorconfig").exists()
