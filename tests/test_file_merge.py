"""Tests for tools/file_merge.py: append-only merges of line-oriented files.

Every kind has the same contract — the adopter's own content is never
rewritten — so each test checks the appended part *and* the preserved prefix.
"""

import ast
import sys
from pathlib import Path

import pytest
import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import file_merge  # noqa: E402

CI_SOURCE = """\
name: CI

permissions:
  contents: read

on:
  push:
    branches:
      - main
  pull_request:

jobs:

  lint:
    uses: ./.github/workflows/_tasks.yml
    with:
      task_runner: just

  test:
    uses: ./.github/workflows/_test.yml
    with:
      task_runner: just

  docs:
    uses: ./.github/workflows/_docs.yml
    permissions:
      contents: write

  release:
    needs: [test, docs]
    if: github.ref_type == 'tag'
    uses: ./.github/workflows/_release.yml

  required-checks-passed:
    name: all required checks passed
    needs: [lint, test]
"""

CI_TARGET = """\
name: my-ci

on:
  push:
    branches:
      - main

jobs:

  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo build
"""


def test_gitignore_appends_only_what_is_missing(tmp_path: Path):
    target = tmp_path / ".gitignore"
    target.write_text("*.pyc\n# mine\ncustom/\n")
    source = tmp_path / "source.gitignore"
    source.write_text("*.pyc\n.venv\nsite/\n")

    result = file_merge.merge_gitignore(target, source)

    assert result.added == [".venv", "site/"]
    assert result.applied
    text = target.read_text()
    assert text.startswith("*.pyc\n# mine\ncustom/\n"), "the adopter's lines are untouched"
    assert ".venv" in text and "site/" in text
    assert text.count("*.pyc") == 1
    assert file_merge.original_is_preserved(b"*.pyc\n# mine\ncustom/\n", target.read_bytes())


def test_gitignore_is_idempotent(tmp_path: Path):
    target = tmp_path / ".gitignore"
    target.write_text("*.pyc\n")
    source = tmp_path / "source.gitignore"
    source.write_text("*.pyc\n.venv\n")

    file_merge.merge_gitignore(target, source)
    once = target.read_text()
    second = file_merge.merge_gitignore(target, source)

    assert target.read_text() == once
    assert second.added == []
    assert any("already present" in note for note in second.notes)


def test_makefile_appends_missing_targets_with_tabs(tmp_path: Path):
    target = tmp_path / "Makefile"
    target.write_text(".PHONY: lint\n\nlint:\n\truff check .\n\nmine:\n\techo mine\n")
    source = tmp_path / "source.mk"
    source.write_text(".PHONY: lint test\n\nlint:\n\truff check .\n\ntest:\n\tpytest\n")

    result = file_merge.merge_recipes(target, source, "makefile")

    assert result.added == ["test"]
    text = target.read_text()
    assert text.startswith(".PHONY: lint\n\nlint:\n\truff check .\n")
    assert "test:\n\tpytest" in text, "recipe bodies keep their tabs"


def test_justfile_appends_missing_recipes(tmp_path: Path):
    target = tmp_path / "justfile"
    target.write_text("lint:\n    ruff check .\n")
    source = tmp_path / "source.just"
    source.write_text("lint:\n    ruff check .\n\ncheck: lint\n    @echo ok\n")

    result = file_merge.merge_recipes(target, source, "justfile")

    assert result.added == ["check"]
    assert "check: lint" in target.read_text()


def test_justfile_ignores_keywords(tmp_path: Path):
    """`set`, `alias` and friends are not recipes."""
    target = tmp_path / "justfile"
    target.write_text("set shell := ['bash', '-c']\n")
    source = tmp_path / "source.just"
    source.write_text("set shell := ['bash', '-c']\n\ntest:\n    pytest\n")

    result = file_merge.merge_recipes(target, source, "justfile")

    assert result.added == ["test"], "the `set` line is not treated as a missing recipe"


def test_taskfile_is_reported_not_appended(tmp_path: Path):
    target = tmp_path / "Taskfile.yml"
    target.write_text("version: '3'\ntasks:\n  mine:\n    cmds:\n      - echo mine\n")
    source = tmp_path / "source.yml"
    source.write_text("version: '3'\ntasks:\n  lint:\n    cmds:\n      - ruff check .\n")
    before = target.read_text()

    result = file_merge.merge_text_file(target, source, "taskfile")

    assert result.reported == ["lint"]
    assert not result.applied
    assert target.read_text() == before
    assert any("reported rather than appended" in note for note in result.notes)


def test_taskfile_appends_when_approved(tmp_path: Path):
    """YAML is not append-friendly in general, so this needs approval — and then it parses."""
    target = tmp_path / "Taskfile.yml"
    target.write_text("version: '3'\n\ntasks:\n  mine:\n    desc: mine\n    cmds:\n      - echo mine\n")
    source = tmp_path / "source.yml"
    source.write_text("version: '3'\n\ntasks:\n  lint:\n    desc: lint\n    cmds:\n      - ruff check .\n")

    reported = file_merge.merge_taskfile(target, source)
    assert reported.reported == ["lint"] and not reported.applied
    assert "lint" not in target.read_text()

    applied = file_merge.merge_taskfile(target, source, append=True)

    assert applied.added == ["lint"] and applied.applied
    document = yaml.safe_load(target.read_text())
    assert set(document["tasks"]) == {"mine", "lint"}
    assert document["tasks"]["mine"]["desc"] == "mine", "their task is unchanged"
    assert file_merge.original_is_preserved(
        b"version: '3'\n\ntasks:\n  mine:\n    desc: mine\n    cmds:\n      - echo mine\n", target.read_bytes()
    )


def test_taskfile_is_not_appended_when_tasks_are_not_last(tmp_path: Path):
    """Appending would land inside the wrong block, so it stays a report."""
    target = tmp_path / "Taskfile.yml"
    target.write_text("version: '3'\n\ntasks:\n  mine:\n    cmds:\n      - echo mine\n\noutput: dot\n")
    source = tmp_path / "source.yml"
    source.write_text("version: '3'\n\ntasks:\n  lint:\n    cmds:\n      - ruff check .\n")
    before = target.read_text()

    result = file_merge.merge_taskfile(target, source, append=True)

    assert not result.applied and result.reported == ["lint"]
    assert target.read_text() == before
    assert any("not the last block" in note for note in result.notes)


def test_ci_caller_keeps_only_the_read_only_jobs():
    caller, kept, dropped = file_merge.ci_caller(CI_SOURCE)

    assert kept == ["lint", "test"]
    assert dropped == ["docs", "release"]
    assert "name: Copier CI" in caller
    assert "\non:\n" in caller, "the `on:` key must survive as YAML (PyYAML 1.1 reads it as true)"
    document = yaml.safe_load(caller)
    assert set(document["jobs"]) == {"lint", "test"}
    assert document["jobs"]["lint"]["uses"] == "./.github/workflows/_tasks.yml"
    assert "required-checks-passed" not in caller


def test_ci_caller_is_written_beside_their_workflow(tmp_path: Path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("# MY OWN CI\n")
    source = tmp_path / "source-ci.yml"
    source.write_text(CI_SOURCE)

    result = file_merge.merge_ci_caller(tmp_path, source)

    assert result.applied
    written = workflows / "copier-ci.yml"
    assert written.is_file()
    assert (workflows / "ci.yml").read_text() == "# MY OWN CI\n", "their workflow is untouched"
    assert any("alongside" in note for note in result.notes)

    again = file_merge.merge_ci_caller(tmp_path, source)
    assert not again.applied
    assert any("already exists" in note for note in again.notes)


def test_unknown_kind_is_an_error(tmp_path: Path):
    with pytest.raises(file_merge.FileMergeError, match="unknown kind"):
        file_merge.merge_text_file(tmp_path / "x", tmp_path / "y", "toml")


PYTHON_TASKS_TARGET = '''\
"""My own tasks, run via `invoke <task>`."""

from invoke.context import Context
from invoke.tasks import task


@task
def mine(c: Context) -> None:
    """My own task."""
    c.run(
        "echo mine",
    )
'''

PYTHON_TASKS_SOURCE = '''\
"""Development tasks, run via `invoke <task>`."""

from invoke.context import Context
from invoke.tasks import task


@task
def lint(c: Context) -> None:
    """Check formatting and lint."""
    c.run(
        "ruff format --check .",
    )


@task
def test(c: Context) -> None:
    """Run the test suite."""
    c.run(
        "pytest",
    )
'''


def test_python_tasks_are_reported_not_appended(tmp_path: Path):
    target = tmp_path / "tasks.py"
    target.write_text(PYTHON_TASKS_TARGET)
    source = tmp_path / "source-tasks.py"
    source.write_text(PYTHON_TASKS_SOURCE)
    before = target.read_text()

    result = file_merge.merge_text_file(target, source, "python_tasks")

    assert result.reported == ["lint", "test"]
    assert not result.applied
    assert target.read_text() == before
    assert any("reported rather than appended" in note for note in result.notes)


def test_python_tasks_append_only_the_missing_functions(tmp_path: Path):
    target = tmp_path / "tasks.py"
    target.write_text(PYTHON_TASKS_TARGET)
    source = tmp_path / "source-tasks.py"
    source.write_text(PYTHON_TASKS_SOURCE)

    result = file_merge.merge_python_tasks(target, source, append=True)

    assert result.added == ["lint", "test"] and result.applied
    text = target.read_text()
    assert text.startswith(PYTHON_TASKS_TARGET), "their file is byte-identical up to the append"
    module = ast.parse(text)
    assert {node.name for node in module.body if isinstance(node, ast.FunctionDef)} == {"mine", "lint", "test"}
    for function in ("lint", "test"):
        fragment = f"@task\ndef {function}(c: Context) -> None:"
        assert fragment in text, f"the appended {function} keeps its decorator and signature"
    assert text.count("@task") == 3, "their decorator is theirs alone"


def test_python_tasks_is_idempotent(tmp_path: Path):
    target = tmp_path / "tasks.py"
    target.write_text(PYTHON_TASKS_TARGET)
    source = tmp_path / "source-tasks.py"
    source.write_text(PYTHON_TASKS_SOURCE)

    file_merge.merge_python_tasks(target, source, append=True)
    once = target.read_text()
    second = file_merge.merge_python_tasks(target, source, append=True)

    assert target.read_text() == once
    assert second.added == [] and not second.applied
    assert any("already present" in note for note in second.notes)


def test_python_tasks_are_not_appended_without_the_decorator_import(tmp_path: Path):
    """Appending a `@task` function into a file with no `task` import breaks it at import time."""
    target = tmp_path / "tasks.py"
    target.write_text('"""My own tasks."""\n\n\ndef mine():\n    """Mine."""\n    ...\n')
    source = tmp_path / "source-tasks.py"
    source.write_text(PYTHON_TASKS_SOURCE)
    before = target.read_text()

    result = file_merge.merge_python_tasks(target, source, append=True)

    assert not result.applied and result.reported == ["lint", "test"]
    assert target.read_text() == before
    assert any("`task` is not defined" in note for note in result.notes)
    assert any("from invoke.tasks import task" in note for note in result.notes)


def test_ci_jobs_are_reported_not_appended(tmp_path: Path):
    target = tmp_path / "ci.yml"
    target.write_text(CI_TARGET)
    source = tmp_path / "source-ci.yml"
    source.write_text(CI_SOURCE)
    before = target.read_text()

    result = file_merge.merge_ci_jobs(target, source)

    assert result.reported == ["lint", "test"]
    assert not result.applied
    assert target.read_text() == before
    assert any("reported rather than appended" in note for note in result.notes)
    assert any("not copied" in note for note in result.notes), "the publish jobs are named as excluded"


def test_ci_jobs_append_only_the_read_only_jobs(tmp_path: Path):
    """Their workflow keeps its bytes; the template's read-only jobs join `jobs:`."""
    target = tmp_path / "ci.yml"
    target.write_text(CI_TARGET)
    source = tmp_path / "source-ci.yml"
    source.write_text(CI_SOURCE)

    result = file_merge.merge_ci_jobs(target, source, append=True)

    assert result.added == ["lint", "test"] and result.applied
    text = target.read_text()
    assert text.startswith(CI_TARGET), "their file is byte-identical up to the append"
    assert "\non:\n" in text, "the `on:` key survives as written (never re-dumped by PyYAML)"
    document = yaml.safe_load(text)
    assert set(document["jobs"]) == {"build", "lint", "test"}
    assert document["jobs"]["build"]["steps"] == [{"run": "echo build"}], "their job is unchanged"
    assert document["jobs"]["lint"]["uses"] == "./.github/workflows/_tasks.yml"
    assert document["jobs"]["test"]["uses"] == "./.github/workflows/_test.yml"


def test_ci_jobs_is_idempotent(tmp_path: Path):
    target = tmp_path / "ci.yml"
    target.write_text(CI_TARGET)
    source = tmp_path / "source-ci.yml"
    source.write_text(CI_SOURCE)

    file_merge.merge_ci_jobs(target, source, append=True)
    once = target.read_text()
    second = file_merge.merge_ci_jobs(target, source, append=True)

    assert target.read_text() == once
    assert second.added == [] and not second.applied
    assert any("already present" in note for note in second.notes)


def test_ci_jobs_skip_a_job_name_that_already_exists(tmp_path: Path):
    """A job name that is already theirs is never overwritten — it is left alone and reported."""
    target = tmp_path / "ci.yml"
    target.write_text(CI_TARGET + "\n  lint:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo my lint\n")
    source = tmp_path / "source-ci.yml"
    source.write_text(CI_SOURCE)

    result = file_merge.merge_ci_jobs(target, source, append=True)

    assert result.added == ["test"] and result.applied
    document = yaml.safe_load(target.read_text())
    assert document["jobs"]["lint"] == {"runs-on": "ubuntu-latest", "steps": [{"run": "echo my lint"}]}
    assert any("already in your workflow, left alone: lint" in note for note in result.notes)


def test_ci_jobs_are_not_appended_when_jobs_are_not_last(tmp_path: Path):
    """Appending would land inside the wrong block, so it stays a report."""
    target = tmp_path / "ci.yml"
    target.write_text("name: my-ci\n\njobs:\n  build:\n    runs-on: ubuntu-latest\n\nconcurrency:\n  group: mine\n")
    source = tmp_path / "source-ci.yml"
    source.write_text(CI_SOURCE)
    before = target.read_text()

    result = file_merge.merge_ci_jobs(target, source, append=True)

    assert not result.applied and result.reported == ["lint", "test"]
    assert target.read_text() == before
    assert any("not the last block" in note for note in result.notes)


def test_cli_dry_run_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    target = tmp_path / ".gitignore"
    target.write_text("*.pyc\n")
    source = tmp_path / "source.gitignore"
    source.write_text("*.pyc\n.venv\n")

    assert file_merge.main(["--target", str(target), "--source", str(source), "--kind", "gitignore", "--dry-run"]) == 0
    assert "added: .venv" in capsys.readouterr().out
    assert target.read_text() == "*.pyc\n"
