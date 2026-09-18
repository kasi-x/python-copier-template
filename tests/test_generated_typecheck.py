"""Type-check rendered output with the generated project's own toolchain.

basedpyright / pyrefly cannot produce meaningful results without the
project's dependencies resolved (reportMissingImports floods otherwise), so
unlike test_generated_lint.py this module runs `uv sync` per rendered path.
It stops short of the test_example_* heavy tail: no pytest run, no
build/twine, no docs build -- the type checkers are the only goal.

Path selection: tests/test_example_*.py already type-check most project types, but
through example-answers.yml's explicit overrides (every use_recommended_*
gate false), so the *recommended* answer combinations -- the ones real users
take -- were never type-checked with deps installed. TYPECHECK_PATHS picks
fast paths whose generated stacks differ meaningfully (library = minimal,
web_api = FastAPI/SQLAlchemy/Alembic, script = flat stdlib-ish, cli+mcp =
the MCP SDK, cli+bot = discord.py, cli+ctf = the ctf extra,
oj_atcoder = bare stdlib).

Exclusions are declared here because this list is their single site:

- data_science needs no entry: the analysis render carries no torch (the
  torch/torchvision deps gate on the kaggle internal in
  _shared/pyproject-deps.toml.jinja; only the cu126 index pin additionally
  gates on gpu x uv), and its recommended leaf is already executed nightly
  by the witness full tier (`project_type=data_science/gate=recommended` in
  FULL_SAMPLE, tests/test_witness_matrix.py: uv sync + basedpyright + the
  generated pytest + docs build).

- kaggle -- the one torch render -- stays out for two recorded reasons.
  Weight: `uv sync` resolves the cu126 torch/torchvision wheels (minutes of
  download, a multi-GB venv), which is exactly why this module is
  heavy+network and nightly-only (ci.yml's test-heavy job), never the edit
  loop. Warning debt (measured 2026-09-18): the recommended kaggle render
  must reach ZERO findings to pass -- basedpyright enables `failOnWarnings`
  by default -- and under its full strictness it carries 31 reportAny-family
  warnings (structlog.get_logger() is Any and the FilteringBoundLogger
  protocol lacks `.success`, DictConfig attribute access is Any, the hydra
  decorator obscures `train`'s type). The error-level blocker from that
  measurement -- `objective(optuna.trial.FixedTrial(cfg.params), cfg)`
  passing a FixedTrial into `objective(trial: optuna.Trial, ...)` -- is
  fixed in the scaffold (the annotation now accepts both); clearing the
  warning debt (a typed logging wrapper + typed config access) is what
  unblocks adding the oj data_science/kaggle answers to TYPECHECK_PATHS,
  which the existing nightly job then picks up with no workflow change.

- ros2 is out entirely: the python flavour's generated nodes import rclpy,
  which exists only in the ROS distribution, not on PyPI (package.xml owns
  the ROS deps), so `uv sync` succeeds but basedpyright floods
  reportMissingImports over the node sources; the cpp flavour ships no
  pyproject.toml at all (its ament_cmake build is authoritative -- see
  test_example_ros2.py). The same distribution reason keeps ros2 out of the
  witness full sample (FULL_SAMPLE's comment in tests/test_witness_matrix.py);
  its renders stay covered by the render tiers and, for the python flavour,
  by test_generated_lint.py.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from render_cache import RenderCache
from render_cache import render_cache as render_cache  # noqa: PLC0414  # the session fixture, made visible here

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/support.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools.answers import BASE  # noqa: E402

# Every test here renders a project and runs `uv sync` in it: a venv build
# against PyPI (the type checkers need the generated project's dependencies).
pytestmark = [pytest.mark.heavy, pytest.mark.network]

TYPECHECK_PATHS: list[dict[str, object]] = [
    {"project_type": "library"},
    {"project_type": "web_api"},
    {"project_type": "script"},
    {"project_type": "cli", "include_mcp": True},
    {"project_type": "cli", "include_bot": True},
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
    tmp_path: Path, render_cache: RenderCache, answers: dict[str, object]
):
    render_cache.render(tmp_path, {**BASE, **answers})
    # setuptools-scm needs a git repo to compute the project version.
    _run("git init -q", tmp_path)
    _run("uv sync", tmp_path)
    _run("uv run --locked basedpyright", tmp_path)
    _run("uv run --locked pyrefly check", tmp_path)
