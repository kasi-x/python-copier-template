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


TOOL_SOURCE = """\
[project]
name = "probe"
dependencies = ["structlog"]

[tool.ruff]
line-length = 88
src = ["src/probe", "tests"]

[tool.ruff.lint]
select = ["ALL"]
extend-ignore = ["D10", "T20"]

[tool.ruff.lint.per-file-ignores]
"tests/**/*" = ["S101"]
"src/probe/_version.py" = ["ALL"]

[tool.typos]
locale = "en-us"

[tool.setuptools_scm]
version_file = "src/probe/_version.py"
"""


def test_tool_config_merges_generic_keys(tmp_path: Path):
    target = write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "legacy"\n\n[tool.ruff]\nline-length = 100\n\n[tool.typos]\nlocale = "en-gb"\n',
    )
    source = write(tmp_path, "source.toml", TOOL_SOURCE)

    result = pyproject_merge.merge_tool_config(target, source, identity=("probe",))

    assert "tool.ruff.lint" in result.added
    assert "select" in result.added["tool.ruff.lint"]
    assert any("tool.ruff.line-length" in line and "100" in line for line in result.kept)
    assert any("tool.typos.locale" in line for line in result.kept)
    parsed = tomllib.loads(target.read_text())
    assert parsed["tool"]["ruff"]["line-length"] == 100, "their setting is untouched"
    assert parsed["tool"]["ruff"]["lint"]["select"] == ["ALL"]
    assert parsed["tool"]["typos"]["locale"] == "en-gb"


def test_tool_config_reports_project_specific_values(tmp_path: Path):
    """Values naming this project must not be copied into someone else's file."""
    target = write(tmp_path, "pyproject.toml", '[project]\nname = "legacy"\n')
    source = write(tmp_path, "source.toml", TOOL_SOURCE)

    result = pyproject_merge.merge_tool_config(target, source, identity=("probe",))

    assert any("tool.ruff.src" in line for line in result.needs_your_value)
    assert any("per-file-ignores" in line and "_version.py" in line for line in result.needs_your_value)
    parsed = tomllib.loads(target.read_text())
    assert "src" not in parsed["tool"]["ruff"], "the template's paths stay out"
    assert "src/probe/_version.py" not in target.read_text()
    assert "tests/**/*" in parsed["tool"]["ruff"]["lint"]["per-file-ignores"], "generic patterns do merge"


def test_tool_config_skips_build_tables(tmp_path: Path):
    target = write(tmp_path, "pyproject.toml", '[project]\nname = "legacy"\n')
    source = write(tmp_path, "source.toml", TOOL_SOURCE)

    result = pyproject_merge.merge_tool_config(target, source, identity=("probe",))

    assert result.skipped_tables == ["tool.setuptools_scm"]
    assert "setuptools_scm" not in target.read_text()
    assert any("build/environment config" in note for note in result.notes)


def test_tool_config_merge_is_idempotent_and_reports_lists(tmp_path: Path):
    target = write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "legacy"\n\n[tool.ruff.lint]\nextend-ignore = ["E501"]\n',
    )
    source = write(tmp_path, "source.toml", TOOL_SOURCE)

    first = pyproject_merge.merge_tool_config(target, source, identity=("probe",))
    once = target.read_text()
    second = pyproject_merge.merge_tool_config(target, source, identity=("probe",))

    assert target.read_text() == once
    assert not second.added
    assert any("extend-ignore" in line and "D10" in line for line in first.kept), "the missing codes are named"


def test_declared_values_covers_tool_leaves():
    document = tomllib.loads(TOOL_SOURCE)
    values = pyproject_merge.declared_values(document)
    assert values["tool.ruff.line-length"] == "88"
    assert values["tool.ruff.lint.select"] == "['ALL']"
    assert any(key.startswith("project.dependencies::") for key in values)


def test_cli_reports_and_applies(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    target = write(tmp_path, "pyproject.toml", '[project]\nname = "x"\ndependencies = []\n')
    source = write(tmp_path, "source.toml", SOURCE)

    assert pyproject_merge.main(["--target", str(target), "--source", str(source), "--dry-run"]) == 0
    assert "added runtime" in capsys.readouterr().out
    assert target.read_text().count("structlog") == 0

    assert pyproject_merge.main(["--target", str(target), "--source", str(source)]) == 0
    assert "structlog" in target.read_text()

    # --tool-config adds the [tool.*] keys too
    assert pyproject_merge.main(["--target", str(target), "--source", str(source), "--tool-config"]) == 0
    assert "[tool.ruff.lint]" not in target.read_text(), "SOURCE has no tool tables"
