"""Tests for tools/pyproject_merge.py: adding to an adopter's pyproject.toml.

The contract is what the merge must *not* do: touch an existing requirement,
drop one, or reformat the rest of the file.
"""

import sys
import tomllib
from pathlib import Path

import pytest

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import pyproject_merge  # noqa: E402

SOURCE = """\
[project]
name = "generated"
version = "0"
dependencies = ["structlog", "httpx>=0.27", "cli-helpers"]

[project.optional-dependencies]
experiment = ["marimo"]

[dependency-groups]
dev = ["ruff", "pytest"]
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_adds_missing_and_keeps_existing(tmp_path: Path):
    target = write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "legacy"\n# keep me\ndependencies = ["httpx>=0.20", "Foo_Bar>=1"]\n',
    )
    source = write(tmp_path, "source.toml", SOURCE)

    result = pyproject_merge.merge_dependencies(target, source)

    assert result.style == "pep621"
    assert result.added["runtime"] == ["structlog", "cli-helpers"]
    assert result.added["dev"] == ["ruff", "pytest"]
    assert result.kept["runtime"] == ["httpx>=0.27"]
    assert result.differing == ["httpx: kept 'httpx>=0.20', template wanted 'httpx>=0.27'"]
    text = target.read_text()
    assert "# keep me" in text, "comments survive the edit"
    assert '"httpx>=0.20"' in text, "an existing pin is never rewritten"
    assert '"Foo_Bar>=1"' in text
    assert '"structlog"' in text and '"cli-helpers"' in text
    assert 'dev = ["ruff", "pytest"]' in text
    assert result.applied


def test_canonical_names_are_not_added_twice(tmp_path: Path):
    target = write(tmp_path, "pyproject.toml", '[project]\nname = "x"\ndependencies = ["StructLog"]\n')
    source = write(tmp_path, "source.toml", SOURCE)

    result = pyproject_merge.merge_dependencies(target, source)

    assert "structlog" not in result.added.get("runtime", [])
    assert "structlog" in result.kept["runtime"]
    assert pyproject_merge.canonical("Foo_Bar[X]>=1") == "foo-bar"
    assert pyproject_merge.canonical("httpx") == "httpx"


def test_merge_is_idempotent(tmp_path: Path):
    target = write(tmp_path, "pyproject.toml", '[project]\nname = "x"\ndependencies = []\n')
    source = write(tmp_path, "source.toml", SOURCE)

    pyproject_merge.merge_dependencies(target, source)
    once = target.read_text()
    second = pyproject_merge.merge_dependencies(target, source)

    assert target.read_text() == once
    assert second.added == {}
    assert "every template dependency is already declared" in second.notes


def test_dry_run_reports_without_writing(tmp_path: Path):
    target = write(tmp_path, "pyproject.toml", '[project]\nname = "x"\ndependencies = []\n')
    source = write(tmp_path, "source.toml", SOURCE)
    before = target.read_text()

    result = pyproject_merge.merge_dependencies(target, source, apply=False)

    assert result.added["runtime"] == ["structlog", "httpx>=0.27", "cli-helpers"]
    assert target.read_text() == before
    assert not result.applied


def test_poetry_layout(tmp_path: Path):
    target = write(
        tmp_path,
        "pyproject.toml",
        '[tool.poetry]\nname = "legacy"\n\n[tool.poetry.dependencies]\npython = "^3.11"\nhttpx = ">=0.20"\n'
        '\n[tool.poetry.group.dev.dependencies]\nruff = "*"\n',
    )
    source = write(tmp_path, "source.toml", SOURCE)

    result = pyproject_merge.merge_dependencies(target, source)

    assert result.style == "poetry"
    parsed = tomllib.loads(target.read_text())
    dependencies = parsed["tool"]["poetry"]["dependencies"]
    assert dependencies["httpx"] == ">=0.20", "the adopter's constraint wins"
    assert dependencies["structlog"] == "*", "an unpinned requirement becomes Poetry's wildcard"
    assert parsed["tool"]["poetry"]["group"]["dev"]["dependencies"]["pytest"] == "*"


def test_a_file_without_a_table_is_only_reported(tmp_path: Path):
    target = write(tmp_path, "pyproject.toml", "[tool.ruff]\nline-length = 100\n")
    source = write(tmp_path, "source.toml", SOURCE)
    before = target.read_text()

    result = pyproject_merge.merge_dependencies(target, source)

    assert result.style == "none"
    assert not result.applied
    assert target.read_text() == before
    assert any("add these by hand" in note for note in result.notes)


def test_a_pyproject_that_does_not_parse_is_left_alone(tmp_path: Path):
    target = write(tmp_path, "pyproject.toml", "[project\nname = ")
    source = write(tmp_path, "source.toml", SOURCE)
    before = target.read_text()

    result = pyproject_merge.merge_dependencies(target, source)

    assert not result.applied
    assert target.read_text() == before
    assert any("does not parse" in note for note in result.notes)


def test_missing_files_are_reported(tmp_path: Path):
    source = write(tmp_path, "source.toml", SOURCE)
    result = pyproject_merge.merge_dependencies(tmp_path / "absent.toml", source)
    assert result.added == {} and any("does not exist" in note for note in result.notes)


def test_optional_extras_are_not_invented(tmp_path: Path):
    target = write(tmp_path, "pyproject.toml", '[project]\nname = "x"\ndependencies = []\n')
    source = write(tmp_path, "source.toml", SOURCE)

    result = pyproject_merge.merge_dependencies(target, source)

    assert "optional-dependencies" not in target.read_text()
    assert any("optional extras not merged" in note and "experiment" in note for note in result.notes)


def test_cli_reports_and_applies(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    target = write(tmp_path, "pyproject.toml", '[project]\nname = "x"\ndependencies = []\n')
    source = write(tmp_path, "source.toml", SOURCE)

    assert pyproject_merge.main(["--target", str(target), "--source", str(source), "--dry-run"]) == 0
    assert "added runtime" in capsys.readouterr().out
    assert target.read_text().count("structlog") == 0

    assert pyproject_merge.main(["--target", str(target), "--source", str(source)]) == 0
    assert "structlog" in target.read_text()
