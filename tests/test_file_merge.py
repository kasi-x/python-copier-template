"""Tests for tools/file_merge.py: append-only merges of line-oriented files.

Every kind has the same contract — the adopter's own content is never
rewritten — so each test checks the appended part *and* the preserved prefix.
"""

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


def test_cli_dry_run_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    target = tmp_path / ".gitignore"
    target.write_text("*.pyc\n")
    source = tmp_path / "source.gitignore"
    source.write_text("*.pyc\n.venv\n")

    assert file_merge.main(["--target", str(target), "--source", str(source), "--kind", "gitignore", "--dry-run"]) == 0
    assert "added: .venv" in capsys.readouterr().out
    assert target.read_text() == "*.pyc\n"
