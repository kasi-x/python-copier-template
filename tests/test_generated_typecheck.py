"""Type-check rendered output with the generated project's own toolchain.

basedpyright / pyrefly cannot produce meaningful results without the
project's dependencies resolved (reportMissingImports floods otherwise), so
unlike test_generated_lint.py this module runs `uv sync` per rendered path.
It stops short of test_example.py's heavy tail: no pytest run, no
build/twine, no docs build -- the type checkers are the only goal.

Path selection: test_example.py already type-checks most project types, but
through example-answers.yml's explicit overrides (every use_recommended_*
gate false), so the *recommended* answer combinations -- the ones real users
take -- were never type-checked with deps installed. TYPECHECK_PATHS picks
fast paths whose generated stacks differ meaningfully (library = minimal,
web_api = FastAPI/SQLAlchemy/Alembic, script = flat stdlib-ish, cli+mcp =
the MCP SDK, cli+ctf = the ctf extra, oj_atcoder = bare stdlib) while
skipping the multi-minute torch syncs (data_science / kaggle), whose fast
path differs from test_example.py's coverage only in answer gates.
"""

import os
import shlex
import subprocess
from pathlib import Path

import pytest
from copier import run_copy

from test_recommended_path import BASE

TOP = Path(__file__).absolute().parent.parent

TYPECHECK_PATHS: list[dict[str, object]] = [
    {"project_type": "library"},
    {"project_type": "web_api"},
    {"project_type": "script"},
    {"project_type": "cli", "include_mcp": True},
    {"project_type": "cli", "include_ctf": True},
    {"project_type": "online_judge", "oj_category": "competitive_coding", "oj_kind": "atcoder"},
]


def _id(answers: dict[str, object]) -> str:
    return "-".join(f"{k}={v}" for k, v in answers.items())


def _run(cmd: str, cwd: Path) -> str:
    sp = subprocess.run(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        # Unset the root repo's env so uv creates the *generated* project's
        # own .venv instead of syncing into the template's environment.
        env=dict(os.environ, UV_PROJECT_ENVIRONMENT="", VIRTUAL_ENV=""),
    )
    output = sp.stdout.decode()
    assert sp.returncode == 0, output
    return output


@pytest.mark.timeout(550)
@pytest.mark.parametrize("answers", TYPECHECK_PATHS, ids=[_id(a) for a in TYPECHECK_PATHS])
def test_generated_project_typechecks_with_own_toolchain(
    tmp_path: Path, answers: dict[str, object]
):
    run_copy(
        src_path=str(TOP),
        dst_path=tmp_path,
        data={**BASE, **answers},
        vcs_ref="HEAD",
        defaults=True,
        unsafe=True,
        overwrite=True,
        skip_tasks=True,
    )
    # setuptools-scm needs a git repo to compute the project version.
    _run("git init -q", tmp_path)
    _run("uv sync", tmp_path)
    _run("uv run --locked basedpyright", tmp_path)
    _run("uv run --locked pyrefly check", tmp_path)
