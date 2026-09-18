"""Shared helpers for this repo's own test suite: the render fixtures and the process helpers.

A test module is not a library: these lived in test_example.py and sibling
modules imported them from there (`from test_example import run_pipe`), which
couples modules that only share plumbing and puts helpers on the import surface
of a test module. Splitting test_example.py by topic (TODO.md §27.7-4) made that
acute -- every split module renders the example project, so `copy_project`,
`copy_project_recommended`, `ci_requested_tasks` and `TOP` moved here with
`run_pipe`/`make_venv` instead of one of the ten modules owning them.

**Render semantics (TODO.md §28.2-2f/§28.6-D5): one entry point, explicit tasks.**
Every render a test asks for goes through the render cache (tests/render_cache.py),
which stores pure renders (`skip_tasks=True`). Whether copier's `_tasks` run is
the explicit `run_tasks` argument of each helper below, and the default is the
historical behaviour: `copy_project`/`copy_project_recommended` are "the render
that runs tasks" -- the cached pure render is copied into the destination and the
template's `_tasks` are replayed on top of it (copier's own `_execute_tasks`, see
`_run_copier_tasks`), so their file side effects (the REUSE LICENSES/ copy) and
their stderr lines appear on every call, warm cache hit or not. Nothing task-made
is ever cached. A test module reading this only needs to know: these helpers
produce exactly what a direct `run_copy` with tasks produced, they just no longer
pay for the render twice.

This deliberately does not live in conftest.py: the template renders the repo's
conftest.py into every generated project (the ``template/.../tests/conftest.py``
symlink points at it and copier resolves it), and a generated project has
neither copier nor fcntl to import -- the same reason tests/render_cache.py
exists (tests/test_render_cache.py guards this mechanically).

The cost-tier scanner in tests/test_marker_drift.py follows
``from <module> import <name>`` edges into this module, so a helper moved here
stays visible to the heavy/network marker guard.
"""

import atexit
import contextlib
import functools
import io
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from copier._main import Worker
from copier._main import as_operation
from copier._types import Phase

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_batch.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools.answers import BASE  # noqa: E402

import render_cache  # noqa: E402  # the tests/ dir is on sys.path (pytest's rootless imports)


def run_pipe(cmd: str, cwd: str | Path | None = None, venv: str | Path = "", env: dict[str, str] | None = None) -> str:
    sp = subprocess.run(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        env=dict(os.environ, UV_PROJECT_ENVIRONMENT="", VIRTUAL_ENV=str(venv), **(env or {})),
    )
    output = sp.stdout.decode()
    assert sp.returncode == 0, output
    return output


def make_venv(project_path: Path) -> Callable[..., str]:
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


def copy_project(project_path: Path, *, run_tasks: bool = True, **kwargs: Any) -> None:
    """Render example-answers.yml (+ `kwargs`) into `project_path`, with `_tasks`.

    "The render that runs tasks": the render cache serves the pure render and
    this helper replays copier's `_tasks` on top (`run_tasks=True`, the
    historical behaviour -- see the module docstring). `run_tasks=False`
    serves the pure render only, for a caller that deliberately does not want
    task side effects. The destination is `git init`-ed and the result
    `git add`-ed, as tests relying on the staged state expect.
    """
    with Path(TOP / "example-answers.yml").open() as f:
        answers = yaml.safe_load(f)
    answers.update(kwargs)
    render_answers(project_path, answers, run_tasks=run_tasks)


def copy_project_capturing_stderr(project_path: Path, *, run_tasks: bool = True, **kwargs: Any) -> str:
    """copy_project, returning everything the generation wrote to stderr.

    The generation-time warnings (copier.yml's `_tasks`: the answers copier
    overrides silently) are how an override becomes visible, so the tests
    that pin an override pin its warning too. Replaying `_tasks` (the
    default) restates them on every call, warm cache hit or not: the warning
    travels with the task's own stderr line, and tasks are never cached.
    """
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        copy_project(project_path, run_tasks=run_tasks, **kwargs)
    return stderr.getvalue()


def copy_project_recommended(project_path: Path, *, run_tasks: bool = True, **kwargs: Any) -> None:
    """Like copy_project, but without example-answers.yml's explicit overrides.

    example-answers.yml sets every option (docker, license, fair, ...) sets
    an explicit value so it never exercises the `use_recommended_*` gates'
    own defaults -- copier uses a `data`-supplied value even for a question
    whose `when` is false. This starts from only the required "Project
    Details" answers (tools/answers.py BASE), so `use_recommended_*` (true by
    default) actually drives the rest of the answer set via each question's
    own `default:`. Same render semantics as copy_project (tasks replayed
    unless `run_tasks=False`).
    """
    answers: dict[str, object] = {**BASE, "package_name": "recommended_example"}
    answers.update(kwargs)
    render_answers(project_path, answers, run_tasks=run_tasks)


def render_answers(project_path: Path, answers: dict[str, object], *, run_tasks: bool = True) -> None:
    """Render an explicit answer set into `project_path` -- the generic copy_project.

    The one render entry point (TODO.md §28.6-D5): the cache serves the pure
    render, and `_tasks` are replayed unless `run_tasks=False`; the
    destination is git-inited and the result git-added, exactly as in
    `copy_project`. The answers are the caller's instead of
    example-answers.yml's, which is what a witness-leaf render
    (tests/test_witness_matrix.py) needs.
    """
    run_pipe(f"git init {project_path}")
    render_cache.shared_cache().render(project_path, answers)
    if run_tasks:
        _run_copier_tasks(answers, project_path)
    run_pipe("git add .", cwd=str(project_path))


# copier runs its questionnaire pass and task execution through private API
# (Worker._ask / _execute_tasks) with no public alternative -- the
# tools/predicates.py `leaf_contexts` oracle precedent in this repo.


@functools.cache
def _task_context_dir() -> Path:
    """The pristine scratch destination the replay Worker probes.

    Never rendered into, so it has no `.copier-answers.yml` for `_ask` to
    read back as `last` answers -- the empty state a fresh `run_copy` sees.
    """
    scratch = Path(tempfile.mkdtemp(prefix="copier-task-context-"))
    atexit.register(shutil.rmtree, scratch, ignore_errors=True)
    return scratch


@functools.cache
def _task_worker() -> Worker:
    """The per-process Worker for task replay: it owns the cloned template.

    The template clone + jinja env it carries are built once and reused by
    every replay (each Worker pays its own template checkout, so a Worker per
    call would pay it per test).
    """
    return Worker(
        src_path=str(TOP),
        dst_path=_task_context_dir(),
        defaults=True,
        unsafe=True,
        quiet=True,
        vcs_ref="HEAD",
    )


def _resolved_answers(answers: dict[str, object]) -> Any:
    """copier's resolved answer set for `answers`: the replay's render context.

    Steady state pays nothing: the render itself already ran copier's
    questionnaire pass (`Worker._ask`), and the cache persists its result
    next to the entry (`render_cache.RenderCache.stored_answers`). Only an
    entry without that record falls back to running the pass here -- on the
    pristine scratch destination, the empty `last`-answers state a fresh
    `run_copy` sees -- and re-persists the result for the next process.
    """
    stored = render_cache.shared_cache().stored_answers(answers)
    if stored is not None:
        return render_cache.answers_map_from_payload(stored)
    worker = _task_worker()
    worker.data = dict(answers)
    worker.dst_path = _task_context_dir()
    worker.__dict__.pop("subproject", None)  # cached_property: rebind to the pristine dir
    worker._ask()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  WHYNOT: copier's own pass, tools/predicates.py precedent.
    render_cache.shared_cache().store_answers(answers, worker.answers)
    return worker.answers


@as_operation("copy")
def _run_copier_tasks(answers: dict[str, object], project_path: Path) -> None:
    """Replay the template's `_tasks` into `project_path` as run_copy would.

    This *is* copier's own `_execute_tasks` (the task runner inside
    `run_copy`), driven where run_copy drives it: after the copy, in the
    TASKS phase, in declaration order, each task's `when` rendered and
    truthed copier's way, its command rendered with the full render context,
    and the subprocess run in the destination -- including copier's
    " > Running task i of n:" line on stderr. The stderr-pinning tests
    (tests/test_example_micropython.py, tests/test_example_layers.py) are the
    guard: replay output is asserted on every call, warm or cold. `dst_path`
    and the cached `subproject` are rebound per call so task working
    directories and `{{ _folder_name }}` resolve against this destination.
    """
    worker = _task_worker()
    worker.answers = _resolved_answers(answers)
    worker.data = dict(answers)
    worker.dst_path = project_path
    worker.__dict__.pop("subproject", None)
    worker.quiet = False  # a direct run announces each task on stderr; so does the replay
    with Phase.use(Phase.TASKS):
        worker._execute_tasks(worker.template.tasks)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  WHYNOT: replay must be copier's own runner, not a re-implementation of it.


def ci_requested_tasks(ci_path: Path) -> list[str]:
    """The task names the generated lint job hands to the reusable _tasks workflow."""
    ci = yaml.safe_load(ci_path.read_text())
    requested = ci["jobs"]["lint"]["with"]["task"]
    return [name.strip() for name in str(requested).split(",") if name.strip()]


# Zensical drives its one-shot `build` from a file watcher, and a watcher it
# cannot start is silent: the monitor thread panics, the build's input channel
# disconnects, and the command prints "Build finished" and exits 0 with the
# empty `site/` directory it created -- the build never ran (TODO §27.7-8). The
# trigger reproduced here is the machine's per-user inotify instance budget
# (`fs.inotify.max_user_instances`, 128, shared with every other process on the
# box) being exhausted, which a dev box running this suite next to anything
# else reaches. `ZENSICAL_POLL_WATCHER` is zensical's own documented fallback
# for such an environment and needs no inotify instance at all, so one retry
# with it tells "the machine refused the watcher" (try again, it is the box)
# apart from "the render's docs sources or configuration do not build" (both
# attempts write nothing).
ZENSICAL_WATCHER_FALLBACK = {"ZENSICAL_POLL_WATCHER": "1"}


def docs_pages(project: Path) -> list[Path]:
    """The pages a rendered project's docs task wrote, wherever its builder puts them."""
    return sorted(project.glob("site/**/*.html")) or sorted(project.glob("build/html/**/*.html"))


def build_docs(project: Path, run: Callable[..., str], cmd: str, label: str) -> list[str]:
    """Run a rendered project's docs task; return every attempt's output (1 or 2).

    `run` is `run_pipe`/`make_venv`'s callable, invoked with an optional `env`
    override. The second attempt is ZENSICAL_WATCHER_FALLBACK's; a docs task
    that writes no page under either is the render's failure, and the
    assertion carries what both attempts said.
    """
    outputs = [run(cmd)]
    if docs_pages(project):
        return outputs
    outputs.append(run(cmd, env=ZENSICAL_WATCHER_FALLBACK))
    site = sorted(path.name for path in (project / "site").glob("*")) if (project / "site").is_dir() else []
    assert docs_pages(project), (
        f"{label}: the docs build produced no pages.\n"
        f"  {cmd} exited 0, twice, in {project}\n"
        f"  attempt 1, the generated project's own recipe:\n{outputs[0]}"
        f"  attempt 2, without a file watcher ({', '.join(f'{k}={v}' for k, v in ZENSICAL_WATCHER_FALLBACK.items())}):\n"
        f"{outputs[1]}"
        f"  site/ holds: {site[:10]}"
    )
    return outputs
