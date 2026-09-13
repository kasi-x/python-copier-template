"""Conformance and runtime guards for the generated task-runner outputs.

`_tasks.jinja` builds the task model ONCE (a single declarative list) and
every runner file serializes that same list. Both failure classes that
happened for real are guarded here:

- the poe-class bug: a task rendered into one runner but broke in another
  (poe's `cmd` entries are not shells, so lint's embedded `&&` died);
- the invoke/duty bug: the generated tasks.py / duties.py failed the
  generated project's own ruff format --check (extra blank lines, >88-char
  command lines).

The contract is pinned structurally — each runner's parsed task table
(names AND dependency structure) must equal the model, read out of the
pixi `[tool.pixi.feature.dev.tasks]` table, which is a direct
serialization of `_tasks.jinja` — and at runtime, where `lint` executes
on the runners whose CLIs install from PyPI, `test` executes via make and
`check` (lint + type-check + test) via poe. task and just execute in
test_example.py's runtime tests; pixi is excluded from the runtime tests
because a conda solve is too heavy for the suite.
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

# The example-answers contract the model must keep exposing (recommended
# strictness): the core four everywhere, the quality/docs tasks on top, and
# `check` aggregating exactly the offline checks.
MODEL_CORE = {"lint", "fix", "test", "check"}
MODEL_RECOMMENDED = {"type-check", "audit", "license-check", "docs", "docs-serve"}
CHECK_DEPS = ["lint", "type-check", "test"]


def _render(runner: str, tmp_path: Path) -> Path:
    copy_project(tmp_path, **RENDER_ARGS[runner])
    return tmp_path


def _parse_tasks(runner: str, project: Path) -> dict[str, list[str] | None]:
    """Parse the rendered runner file into {task: deps or None}.

    None means the task carries commands; a list means it only aggregates
    other tasks. This is a structural read-out, not a string comparison of
    rendered wording: runners may format freely as long as the task set and
    the dependency graph survive.
    """
    if runner == "pixi":
        raw = tomllib.loads((project / "pyproject.toml").read_text())["tool"]["pixi"]["feature"]["dev"]["tasks"]
        return {name: table.get("depends-on") for name, table in raw.items()}
    if runner == "poe":
        raw = tomllib.loads((project / "pyproject.toml").read_text())["tool"]["poe"]["tasks"]
        return {name: table.get("sequence") for name, table in raw.items()}
    if runner == "task":
        raw = yaml.safe_load((project / "Taskfile.yml").read_text())["tasks"]
        # `default` is runner plumbing, not part of the model.
        return {name: table.get("deps") for name, table in raw.items() if name != "default"}
    if runner in ("just", "make"):
        # just/make recipes (or targets) are the unindented `name:` lines.
        text = (project / ("justfile" if runner == "just" else "Makefile")).read_text()
        parsed: dict[str, list[str] | None] = {}
        for m in re.finditer(r"^([a-zA-Z][a-zA-Z_-]*):([^\n]*)$", text, re.MULTILINE):
            name, rest = m.group(1), m.group(2).strip()
            if name == "default":
                continue
            parsed[name] = rest.split() if rest else None
        return parsed
    if runner == "invoke":
        # python function names use underscores; normalize back to the
        # hyphenated task name so every runner compares equal
        text = (project / "tasks.py").read_text()
        pairs = re.findall(r"^@task(?:\(([^)]*)\))?[^\n]*\ndef ([a-z_]+)\(c: Context\)", text, re.MULTILINE)
        return {
            name.replace("_", "-"): (
                [dep.strip().replace("_", "-") for dep in decorator.split(",")] if decorator else None
            )
            for decorator, name in pairs
        }
    if runner == "duty":
        text = (project / "duties.py").read_text()
        pairs = re.findall(r"^@duty(?:\(pre=\[([^\]]*)\]\))?[^\n]*\ndef ([a-z_]+)\(ctx: Context\)", text, re.MULTILINE)
        return {
            name.replace("_", "-"): (
                [dep.strip().strip('"').replace("_", "-") for dep in decorator.split(",")] if decorator else None
            )
            for decorator, name in pairs
        }
    msg = f"unknown runner {runner!r}"
    raise AssertionError(msg)


@pytest.fixture(scope="module")
def model_tasks(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[str] | None]:
    """The task model itself, read out of the pixi pyproject table."""
    project = tmp_path_factory.mktemp("model-pixi")
    copy_project(project, **RENDER_ARGS["pixi"])
    return _parse_tasks("pixi", project)


def test_task_model_pins_the_example_contract(model_tasks: dict[str, list[str] | None]):
    """The model keeps exposing the tasks the example project is documented
    to have, and `check` aggregates exactly the offline checks. If this
    drifts on purpose, update it together with AGENTS.md and the CI inputs."""
    assert model_tasks.keys() >= MODEL_CORE
    assert model_tasks.keys() >= MODEL_RECOMMENDED
    assert model_tasks["check"] == CHECK_DEPS


@pytest.mark.parametrize("runner", RENDER_ARGS, ids=RENDER_ARGS)
def test_runner_matches_the_task_model(
    runner: str,
    tmp_path: Path,
    model_tasks: dict[str, list[str] | None],
):
    """Every runner serializes the SAME model: task names and dependency
    structure must be equal, not merely overlapping. A task that renders
    into some runners but not others — or a deps edge that one runner
    drops — is silent drift, the poe regression class."""
    project = _render(runner, tmp_path)
    rendered = _parse_tasks(runner, project)
    assert rendered == model_tasks, (
        f"{runner}: task table drifted from the model "
        f"(missing={set(model_tasks) - set(rendered)}, "
        f"extra={set(rendered) - set(model_tasks)}, "
        f"deps-differs={[(t, rendered[t], model_tasks[t]) for t in rendered if rendered[t] != model_tasks[t] and t in model_tasks]})"
    )


def test_ci_lint_job_tasks_exist_in_the_model(tmp_path: Path, model_tasks: dict[str, list[str] | None]):
    """The generated ci.yml hands task names to `_tasks.yml` (`task: lint,
    type-check, ...`). A name the model no longer defines would fail CI at
    runtime, so every requested task must exist in the model."""
    project = _render("task", tmp_path)
    ci = yaml.safe_load((project / ".github" / "workflows" / "ci.yml").read_text())
    requested = str(ci["jobs"]["lint"]["with"]["task"]).replace(",", " ").split()
    assert requested, "ci.yml lint job must request at least one task"
    assert set(requested) <= set(model_tasks), f"ci.yml requests non-model tasks: {set(requested) - set(model_tasks)}"


@pytest.mark.heavy
@pytest.mark.network
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


@pytest.mark.heavy
@pytest.mark.network
def test_test_task_executes_on_make(tmp_path: Path):
    """`make test` runs the generated pytest suite (coverage flags and all)
    through the makefile's per-line recipe serialization."""
    project = _render("make", tmp_path)
    run = make_venv(project)
    run("make test")


@pytest.mark.heavy
@pytest.mark.network
def test_check_task_executes_on_poe(tmp_path: Path):
    """`poe check` walks the model's dependency graph (lint -> type-check ->
    test) through poe's sequence type, exercising every serializer branch
    (shell join, cmd, sequence) in one go."""
    project = _render("poe", tmp_path)
    run = make_venv(project)
    run("uv run --locked poe check")
