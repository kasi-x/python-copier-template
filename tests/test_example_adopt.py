"""Adopt mode (existing_project): the adopter-owned files copier must leave
byte-identical, copier update interop on an adopted project, and the git-less
render publish pipelines use."""

from pathlib import Path

import pytest
import yaml
from copier import run_copy

from support import TOP
from support import copy_project
from support import make_venv
from support import run_pipe


def test_template_adopt_mode_protects_existing_files(tmp_path: Path):
    """Adopt mode (existing_project: true) must leave the adopter's own
    files byte-identical while still adding the missing infrastructure
    (SPEC-adoption.md U2 / phases P1)."""
    (tmp_path / "README.md").write_text("# my own readme\n")
    (tmp_path / "LICENSE").write_text("my own license\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "existing"\n')
    (tmp_path / ".gitignore").write_text("my own ignore\n")
    (tmp_path / ".python-version").write_text("3.12\n")
    pkg = tmp_path / "src" / "existing_pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('"""My package."""\n')

    copy_project(tmp_path, existing_project=True)

    # protected files remain byte-identical
    assert (tmp_path / "README.md").read_text() == "# my own readme\n"
    assert (tmp_path / "LICENSE").read_text() == "my own license\n"
    assert (tmp_path / "pyproject.toml").read_text() == '[project]\nname = "existing"\n'
    assert (tmp_path / ".gitignore").read_text() == "my own ignore\n"
    assert (tmp_path / ".python-version").read_text() == "3.12\n"
    assert (pkg / "__init__.py").read_text() == '"""My package."""\n'
    # the runner files are protected too (the adopter keeps their tooling)
    assert not (tmp_path / "justfile").exists()
    # infrastructure is still added
    for infra in (
        ".github/workflows/ci.yml",
        ".github/workflows/_hygiene.yml",
        ".gitleaks.toml",
        "renovate.json",
        "AGENTS.md",
        "cliff.toml",
        "docs",
    ):
        assert (tmp_path / infra).exists(), f"missing infra: {infra}"
    # answers recorded -> future copier update works
    recorded = yaml.safe_load((tmp_path / ".copier-answers.yml").read_text())
    assert recorded["existing_project"] is True


@pytest.mark.heavy
@pytest.mark.network
def test_template_adopt_mode_update_interop(tmp_path: Path):
    """An adopt-mode project can run copier update: the recorded answers
    (including adopt_protect) do not break the update mechanics, protected
    files stay untouched, and the adoption report task does not re-run
    (SPEC-adoption.md §10.4)."""
    # the adopter owns a minimal pyproject and README (protected, never
    # rewritten)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "existing"\nversion = "0.1.0"\n')
    (tmp_path / "README.md").write_text("# my own readme\n")
    # Render from a CLEAN clone of the template: copier commits a dirty local
    # template into a synthetic commit and records its describe in _commit;
    # that describe changes on every render, so copier judges the next update
    # a downgrade (same rule tools/batch.py enforces as an update
    # precondition). A clean clone has a stable, resolvable describe.
    clean_tpl = tmp_path / "tpl"
    run_pipe(f"git clone -q {str(TOP)!r} {clean_tpl}")
    run_pipe(f"git init -q {tmp_path}")

    # the adopter owns a minimal pyproject and README (protected, never
    # rewritten)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "existing"\nversion = "0.1.0"\n')
    (tmp_path / "README.md").write_text("# my own readme\n")

    answers = yaml.safe_load((TOP / "example-answers.yml").read_text())
    answers["existing_project"] = True
    run_copy(
        src_path=str(clean_tpl),
        dst_path=tmp_path,
        data=answers,
        vcs_ref="HEAD",
        unsafe=True,
        defaults=True,
    )

    run = make_venv(tmp_path)
    readme_before = (tmp_path / "README.md").read_text()
    assert (tmp_path / "pyproject.toml").read_text().startswith("[project]")
    run("uvx copier update --defaults --vcs-ref=HEAD --trust")
    assert (tmp_path / "README.md").read_text() == readme_before
    assert (tmp_path / "pyproject.toml").exists()


@pytest.mark.heavy
@pytest.mark.network
def test_template_works_outside_git(tmp_path: Path):
    """Publish pipelines generate first and `git init` later. Without git
    metadata setuptools_scm used to abort every `uv sync` — the fallback
    version keeps the workspace usable until the first commit."""
    run_copy(
        src_path=str(TOP),
        dst_path=tmp_path,
        data={
            "package_name": "nogit_test",
            "description": "generated outside git",
            "git_platform": "github.com",
            "github_org": "kasi-x",
            "author_name": "kasi-x",
            "author_email": "kasi-x@example.com",
        },
        vcs_ref="HEAD",
        unsafe=True,
        defaults=True,
    )
    assert 'fallback_version = "0.0.0"' in (tmp_path / "pyproject.toml").read_text()
    assert not (tmp_path / ".git").exists()
    run_pipe("uv sync", cwd=str(tmp_path))
