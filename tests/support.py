"""Shared helpers for this repo's own test suite: `run_pipe` and `make_venv`.

A test module is not a library: these lived in test_example.py and sibling
modules imported them from there (`from test_example import run_pipe`), which
couples modules that only share plumbing and puts helpers on the import surface
of a test module. This deliberately does not live in conftest.py: the template
renders the repo's conftest.py into every generated project (the
``template/.../tests/conftest.py`` symlink points at it and copier resolves it),
and a generated project has neither copier nor fcntl to import -- the same
reason tests/render_cache.py exists.

The cost-tier scanner in tests/test_marker_drift.py follows
``from <module> import <name>`` edges into this module, so a helper moved here
stays visible to the heavy/network marker guard.
"""

import functools
import os
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path


def run_pipe(cmd: str, cwd: str | Path | None = None, venv: str | Path = "") -> str:
    sp = subprocess.run(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        env=dict(os.environ, UV_PROJECT_ENVIRONMENT="", VIRTUAL_ENV=str(venv)),
    )
    output = sp.stdout.decode()
    assert sp.returncode == 0, output
    return output


def make_venv(project_path: Path) -> Callable[[str], str]:
    venv_path = project_path / ".venv"
    run = functools.partial(run_pipe, cwd=str(project_path), venv=venv_path)
    run("uv sync")  # Create a lockfile and install packages

    exe_path = venv_path / "bin" / "python"
    assert exe_path.exists(), f"UV created a venv but did not install {exe_path}"

    # Commit the freshly created lockfile: `uv run --locked` (used by the
    # generated tasks and CI) requires it to match the environment.
    run("git config user.email 'you@example.com'")
    run("git config user.name 'Your Name'")
    run("git add -A")
    run("git commit -qm 'Initial sync'")

    return run
