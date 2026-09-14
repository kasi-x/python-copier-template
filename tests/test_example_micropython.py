"""The micropython project_type: the firmware tree, the port-specific stubs, and
the device-independent core test under CPython."""

import re
from pathlib import Path

import pytest
import yaml

from support import copy_project
from support import copy_project_recommended
from support import make_venv


def test_template_micropython_sphinx_falls_back_to_zensical(tmp_path: Path):
    """docs_type has static choices (for --data-file validation), so sphinx
    is answerable for micropython even though the firmware has nothing for
    autodoc to import — render must redirect that answer to zensical."""
    copy_project(
        tmp_path,
        project_type="micropython",
        micropython_port="esp32",
        use_recommended_docs=False,
        docs_type="sphinx",
    )
    assert (tmp_path / "zensical.toml").exists()
    assert not (tmp_path / "docs" / "conf.py").exists()
    assert not (tmp_path / "docs" / "_api.rst").exists()
    pyproject_toml = (tmp_path / "pyproject.toml").read_text()
    assert "pydata-sphinx-theme" not in pyproject_toml
    assert '"zensical"' in pyproject_toml


def test_template_micropython_default(tmp_path: Path):
    copy_project_recommended(tmp_path, project_type="micropython", micropython_port="esp32")
    # firmware tree
    assert (tmp_path / "firmware" / "boot.py").exists()
    assert (tmp_path / "firmware" / "main.py").exists()
    assert (tmp_path / "firmware" / "board_config.py").exists()
    assert (tmp_path / "firmware" / "core" / "app.py").exists()
    # stub requirement matches the port and is pinned to the firmware version
    reqs = (tmp_path / "requirements-dev.txt").read_text()
    assert "micropython-esp32-stubs~=" in reqs
    freeze = (tmp_path / "tools" / "micropython" / "freeze.py").read_text()
    tag = next(line.split('"')[1] for line in freeze.splitlines() if "DEFAULT_TAG =" in line)
    assert f"~={tag[1:]}" in reqs  # stubs pinned to the same MicroPython release
    # CPython dev toolchain coexists, but there is no installable package
    pyproject = (tmp_path / "pyproject.toml").read_text()
    assert "[project]" in pyproject
    assert "mpremote" in pyproject
    # The standard CPython package / logging / CLI test is not generated
    assert not list(tmp_path.rglob("logging_setup.py"))
    assert not list(tmp_path.rglob("__main__.py"))
    assert not list(tmp_path.rglob("test_cli.py"))
    # But a CPython core test is
    assert (tmp_path / "tests" / "test_core.py").exists()
    # firmware has its own type-check config pointing at the port stubs
    fw_pyright = (tmp_path / "firmware" / "pyrightconfig.json").read_text()
    assert "../typings" in fw_pyright
    # CI keeps lint+test and adds no dist job for a firmware project
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "required-checks-passed" in ci
    assert "firmware:" in ci
    assert "freeze.py" in ci
    ci_tasks = yaml.safe_load((tmp_path / ".github" / "workflows" / "_tasks.yml").read_text())
    runs = [step.get("run", "") for job in ci_tasks["jobs"].values() for step in job.get("steps", [])]
    assert any("requirements-dev.txt" in run and "--target typings" in run for run in runs), (
        "CI must install the MicroPython stubs where type-checking can see them"
    )
    # the freeze build ships a manifest and a docker-based build script
    manifest = (tmp_path / "firmware" / "manifest.py").read_text()
    assert 'freeze(".")' in manifest
    assert "micropython/build-micropython-arm:bookworm" in freeze
    assert "espressif/idf" in freeze
    justfile = (tmp_path / "justfile").read_text()
    assert re.search(r"^freeze:", justfile, re.MULTILINE), "the firmware build is exposed as a recipe"


def test_template_micropython_rp2_stub(tmp_path: Path):
    copy_project_recommended(tmp_path, project_type="micropython", micropython_port="rp2")
    reqs = (tmp_path / "requirements-dev.txt").read_text()
    assert "micropython-rp2-stubs~=" in reqs
    assert "micropython-esp32-stubs" not in reqs


@pytest.mark.heavy
@pytest.mark.network
def test_template_micropython_core_test_runs(tmp_path: Path):
    """The device-independent core must be importable and testable under CPython."""
    copy_project_recommended(tmp_path, project_type="micropython", micropython_port="unix")
    run = make_venv(tmp_path)
    run("uv run pytest -q")
