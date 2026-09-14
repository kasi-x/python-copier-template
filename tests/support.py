"""Shared helpers for this repo's own test suite: the render fixtures and the process helpers.

A test module is not a library: these lived in test_example.py and sibling
modules imported them from there (`from test_example import run_pipe`), which
couples modules that only share plumbing and puts helpers on the import surface
of a test module. Splitting test_example.py by topic (TODO.md §27.7-4) made that
acute -- every split module renders the example project, so `copy_project`,
`copy_project_recommended`, `ci_requested_tasks` and `TOP` moved here with
`run_pipe`/`make_venv` instead of one of the ten modules owning them.

This deliberately does not live in conftest.py: the template renders the repo's
conftest.py into every generated project (the ``template/.../tests/conftest.py``
symlink points at it and copier resolves it), and a generated project has
neither copier nor fcntl to import -- the same reason tests/render_cache.py
exists.

The cost-tier scanner in tests/test_marker_drift.py follows
``from <module> import <name>`` edges into this module, so a helper moved here
stays visible to the heavy/network marker guard.
"""

import contextlib
import functools
import io
import os
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import yaml
from copier import run_copy

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_batch.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools.answers import BASE  # noqa: E402


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


def copy_project(project_path: Path, **kwargs: object):
    with Path(TOP / "example-answers.yml").open() as f:
        answers = yaml.safe_load(f)
    answers.update(kwargs)
    run_pipe(f"git init {project_path}")
    run_copy(
        src_path=str(TOP),
        dst_path=project_path,
        data=answers,
        vcs_ref="HEAD",
        unsafe=True,
        defaults=True,
    )
    run_pipe("git add .", cwd=str(project_path))


def copy_project_capturing_stderr(project_path: Path, **kwargs: object) -> str:
    """copy_project, returning everything the render wrote to stderr.

    The generation-time warnings (copier.yml's `_tasks_pre`: the answers
    copier overrides silently) are how an override becomes visible, so the
    tests that pin an override pin its warning too.
    """
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        copy_project(project_path, **kwargs)
    return stderr.getvalue()


def copy_project_recommended(project_path: Path, **kwargs: object):
    """Like copy_project, but without example-answers.yml's explicit overrides.

    example-answers.yml sets every option (docker, license, fair, ...) sets
    an explicit value so it never exercises the `use_recommended_*` gates'
    own defaults -- copier uses a `data`-supplied value even for a question
    whose `when` is false. This starts from only the required "Project
    Details" answers (tools/answers.py BASE), so `use_recommended_*` (true by
    default) actually drives the rest of the answer set via each question's
    own `default:`.
    """
    answers: dict[str, object] = {**BASE, "package_name": "recommended_example"}
    answers.update(kwargs)
    run_pipe(f"git init {project_path}")
    run_copy(
        src_path=str(TOP),
        dst_path=project_path,
        data=answers,
        vcs_ref="HEAD",
        unsafe=True,
        defaults=True,
    )
    run_pipe("git add .", cwd=str(project_path))


def ci_requested_tasks(ci_path: Path) -> list[str]:
    """The task names the generated lint job hands to the reusable _tasks workflow."""
    ci = yaml.safe_load(ci_path.read_text())
    requested = ci["jobs"]["lint"]["with"]["task"]
    return [name.strip() for name in str(requested).split(",") if name.strip()]
