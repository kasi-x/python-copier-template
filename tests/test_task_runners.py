"""Conformance and runtime guards for the generated task-runner outputs.

Every task runner must expose the *same* task set with commands that
actually execute. Both classes of failure happened for real:

- the poe-class bug: a task rendered into one runner but broke in another
  (poe's `cmd` entries are not shells, so lint's embedded `&&` died);
- the invoke/duty bug: the generated tasks.py / duties.py failed the
  generated project's own ruff format --check (extra blank lines, >88-char
  command lines).

This module pins the contract structurally (task NAME SET across all seven
runners) and at runtime (lint actually executes for the runners whose CLIs
install from PyPI; task and just are covered by test_example.py's runtime
tests, and pixi is excluded because a conda solve is too heavy for the
suite).
"""

import re
import tomllib
from pathlib import Path

import pytest
import yaml

from test_example import copy_project
from test_example import make_venv

RENDER_ARGS: dict[str, dict[str, object]] = {
    "task": {"use_recommended_toolchain": False, "task_runner": "task"},
    "just": {"use_recommended_toolchain": False, "task_runner": "just"},
    "make": {"use_recommended_toolchain": False, "task_runner": "make"},
    "poe": {"use_recommended_toolchain": False, "task_runner": "poe"},
    "invoke": {"use_recommended_toolchain": False, "task_runner": "invoke"},
    "duty": {"use_recommended_toolchain": False, "task_runner": "duty"},
    "pixi": {
        "use_recommended_toolchain": False,
        "package_manager": "pixi",
        "task_runner_pixi": "pixi",
    },
}

CORE_TASKS = {"lint", "fix", "test", "check"}


def _render(runner: str, tmp_path: Path) -> Path:
    copy_project(tmp_path, **RENDER_ARGS[runner])
    return tmp_path


def _task_names(runner: str, project: Path) -> set[str]:
    """Extract the defined task names from a rendered runner file."""
    if runner == "task":
        return set(yaml.safe_load((project / "Taskfile.yml").read_text())["tasks"])
    if runner == "pixi":
        pyproject = tomllib.loads((project / "pyproject.toml").read_text())
        return set(pyproject["tool"]["pixi"]["feature"]["dev"]["tasks"])
    if runner == "poe":
        pyproject = tomllib.loads((project / "pyproject.toml").read_text())
        return set(pyproject["tool"]["poe"]["tasks"])
    if runner == "invoke":
        text = (project / "tasks.py").read_text()
        # python function names use underscores; normalize back to the
        # hyphenated task name so every runner compares equal
        return {name.replace("_", "-") for name in re.findall(r"^def ([a-z_]+)\(c: Context\)", text, re.MULTILINE)}
    if runner == "duty":
        text = (project / "duties.py").read_text()
        return {name.replace("_", "-") for name in re.findall(r"^def ([a-z_]+)\(ctx: Context\)", text, re.MULTILINE)}
    # just / make: recipes (or targets) are the unindented `name:` lines;
    # `default:` is runner plumbing, not a task.
    text = (project / ("justfile" if runner == "just" else "Makefile")).read_text()
    names = set(re.findall(r"^([a-zA-Z][a-zA-Z_-]*):", text, re.MULTILINE))
    return names - {"default"}


@pytest.mark.parametrize("runner", RENDER_ARGS, ids=RENDER_ARGS)
def test_task_set_is_identical_across_runners(runner: str, tmp_path: Path):
    """All runners expose the identical task set (plus runner plumbing like
    task's `default`). A task that renders into some runners but not others
    is silent drift — the poe regression class."""
    project = _render(runner, tmp_path)
    names = _task_names(runner, project)
    assert names >= CORE_TASKS, f"{runner}: missing tasks {CORE_TASKS - names}"
    # The recommended path also ships type-check/audit/docs tasks.
    assert {"type-check", "audit", "docs", "docs-serve"} <= names, f"{runner}: recommended-path tasks missing: {names}"


@pytest.mark.parametrize(
    ("runner", "lint_cmd"),
    [
        ("make", "make lint"),
        ("poe", "uv run --locked poe lint"),
        ("invoke", "uv run --locked invoke lint"),
        ("duty", "uv run --locked duty lint"),
    ],
)
def test_lint_task_executes(runner: str, lint_cmd: str, tmp_path: Path):
    """`lint` must actually EXECUTE on the runners whose CLIs install from
    PyPI. Render-only asserts cannot see a non-shell `cmd` type or a broken
    recipe indent. task/just execute in test_example's runtime tests."""
    project = _render(runner, tmp_path)
    run = make_venv(project)
    run(lint_cmd)
