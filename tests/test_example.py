import functools
import json
import os
import re
import shlex
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from copier import run_copy

TOP = Path(__file__).absolute().parent.parent


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


def copy_project_recommended(project_path: Path, **kwargs: object):
    """Like copy_project, but without example-answers.yml's explicit overrides.

    example-answers.yml sets every option (docker, license, fair, ...) sets
    an explicit value so it never exercises the `use_recommended_*` gates'
    own defaults -- copier uses a `data`-supplied value even for a question
    whose `when` is false. This starts from only the required "Project
    Details" answers, so `use_recommended_*` (true by default) actually
    drives the rest of the answer set via each question's own `default:`.
    """
    answers: dict[str, object] = {
        "package_name": "recommended_example",
        "description": "An example project",
        "git_platform": "github.com",
        "github_org": "kasi-x",
        "author_name": "kasi-x",
        "author_email": "kashimiya.exe@gmail.com",
        "project_type": "library",
    }
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

    # Commit the freshly created lockfile so pre-commit's `uv sync` hook does
    # not report a diff.
    run("git config user.email 'you@example.com'")
    run("git config user.name 'Your Name'")
    run("git add -A")
    run("git commit -qm 'Initial sync'")

    return run


def test_template_defaults(tmp_path: Path):
    copy_project(tmp_path)
    run = make_venv(tmp_path)
    container_doc = tmp_path / "docs" / "how-to" / "run-container.md"
    pyproject_toml = tmp_path / "pyproject.toml"
    assert container_doc.exists()
    # example-answers.yml uses strictness: recommended
    assert 'typeCheckingMode = "recommended"' in pyproject_toml.read_text()
    run("uvx --from go-task-bin task check")
    if not run_pipe("git tag --points-at HEAD"):
        # Only run linkcheck if not on a tag, as the CI might not have pushed
        # the docs for this tag yet, so we will fail. `-b linkcheck` is
        # sphinx-specific; example-answers uses zensical so just build docs.
        run("uvx --from go-task-bin task docs")
    run("uvx --from build pyproject-build")
    run("uvx twine check --strict dist/*")


def test_template_with_extra_code_and_api_docs(tmp_path: Path):
    copy_project(tmp_path, docs_type="sphinx", project_type="library")
    run = make_venv(tmp_path)
    # add some code
    init = tmp_path / "src" / "python_copier_template_example" / "__init__.py"
    init.write_text(
        init.read_text().replace(
            'from ._version import __version__\n\n__all__ = ["__version__"]',
            '''from python_copier_template_example import extra_pkg

from ._version import __version__


class TopCls:
    """A top level class."""


__all__ = ["TopCls", "__version__", "extra_pkg"]''',
        )
    )
    extra_pkg = tmp_path / "src" / "python_copier_template_example" / "extra_pkg"
    extra_pkg.mkdir()
    (extra_pkg / "__init__.py").write_text('"""Extra Package."""\n')
    code = '''"""A module."""


class Thing:
    """A docstring."""
'''
    (extra_pkg / "extra_module.py").write_text(code)
    # Add to make sure pre-commit doesn't moan
    run("git add .")
    # Build
    run("uvx --from go-task-bin task check")
    run("uvx --from go-task-bin task docs")
    # Check it generates the right output
    api_dir = tmp_path / "build" / "html" / "_api"
    top_html = api_dir / "python_copier_template_example.html"
    assert "extra_pkg" in top_html.read_text()
    assert "Extra Package." in top_html.read_text()
    assert "TopCls" in top_html.read_text()
    assert "A top level class." in top_html.read_text()
    assert "__version__" in top_html.read_text()
    assert "setuptools_scm" in top_html.read_text()
    package_html = api_dir / "python_copier_template_example.extra_pkg.html"
    assert "extra_module" in package_html.read_text()
    assert "A module." in package_html.read_text()
    module_html = api_dir / "python_copier_template_example.extra_pkg.extra_module.html"
    assert "Thing" in module_html.read_text()
    assert "A docstring." in module_html.read_text()


def test_template_pyrefly(tmp_path: Path):
    copy_project(tmp_path, type_checker="pyrefly")
    run = make_venv(tmp_path)
    run("uvx --from go-task-bin task check")


def test_template_no_docs(tmp_path: Path):
    copy_project(tmp_path, docs_type="README")
    run = make_venv(tmp_path)
    run("uvx --from go-task-bin task check")


def test_template_zensical_docs(tmp_path: Path):
    copy_project(tmp_path, docs_type="zensical")
    pyproject_toml = tmp_path / "pyproject.toml"
    assert '"zensical"' in pyproject_toml.read_text()
    assert (tmp_path / "zensical.toml").exists()
    run = make_venv(tmp_path)
    run("uvx --from go-task-bin task check")


def test_template_great_docs(tmp_path: Path):
    copy_project(tmp_path, docs_type="great-docs")
    assert (tmp_path / "great-docs.yml").exists()
    assert (tmp_path / "index.qmd").exists()


def test_template_kaggle_competition(tmp_path: Path):
    copy_project(tmp_path, project_type="data_science", competition=True)
    # Top level has notebooks/ and src/, no standard DS dirs
    assert (tmp_path / "notebooks").is_dir()
    assert (tmp_path / "src").is_dir()
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "models").exists()
    # Kaggle dirs inside src/
    for d in ["configs", "data", "input", "output", "features", "logs", "models", "notebook", "scripts", "utils"]:
        assert (tmp_path / "src" / d).is_dir(), f"missing src/{d}"
    # utils is the installable package
    assert (tmp_path / "src" / "utils" / "__init__.py").exists()
    assert (tmp_path / "src" / "utils" / "config.py").exists()
    assert (tmp_path / "src" / "utils" / "modeling" / "train.py").exists()
    # GPU artifacts (always included for data_science)
    assert (tmp_path / "Dockerfile.gpu").exists()
    # no standard package dir
    assert not (tmp_path / "src" / "python_copier_template_example").exists()
    # Taskfile exists
    assert (tmp_path / "Taskfile.yml").exists()
    # pyproject references utils and lifelog-style deps
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("typer") for d in pyproject_toml["project"]["dependencies"])
    assert any(d.startswith("structlog") for d in pyproject_toml["project"]["dependencies"])
    # ML tools and experiment extras
    assert any(d.startswith("optuna") for d in pyproject_toml["project"]["dependencies"])
    assert any(d.startswith("torch") for d in pyproject_toml["project"]["dependencies"])
    experiment = pyproject_toml["project"]["optional-dependencies"]["experiment"]
    assert any(d.startswith("marimo") for d in experiment)
    assert any(d.startswith("matplotlib") for d in experiment)
    # marimo notebook exists
    assert (tmp_path / "src" / "notebook" / "explore.py").exists()


def test_template_data_science_layout(tmp_path: Path):
    copy_project(tmp_path, project_type="data_science")
    # Standard DS layout
    assert (tmp_path / "notebooks").is_dir()
    for d in ["external", "interim", "processed", "raw"]:
        assert (tmp_path / "data" / d).is_dir(), f"missing data/{d}"
    assert (tmp_path / "models").is_dir()
    assert (tmp_path / "reports" / "figures").is_dir()
    for d in ["data", "features", "models", "visualization"]:
        assert (tmp_path / "src" / d).is_dir(), f"missing src/{d}"
    # Data governance & restricted-data sharing kit, always present
    for name in [
        "DEIDENTIFICATION.md",
        "sharing/DATA_TRANSFER_AGREEMENT.md",
        "sharing/TRANSFER_LOG.csv",
    ]:
        assert (tmp_path / "data" / name).exists(), f"data/{name}"
    log = (tmp_path / "data" / "sharing" / "TRANSFER_LOG.csv").read_text()
    assert log.startswith("date,recipient")
    # Package is src/<package_name>
    assert (tmp_path / "src" / "python_copier_template_example" / "__init__.py").exists()
    # GPU + Quarto always included for data_science
    assert (tmp_path / "Dockerfile.gpu").exists()
    assert (tmp_path / "paper" / "paper.qmd").exists()
    assert (tmp_path / "slides" / "slides.qmd").exists()
    # experiment extras
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    experiment = pyproject_toml["project"]["optional-dependencies"]["experiment"]
    assert any(d.startswith("marimo") for d in experiment)
    # No competition artifacts
    assert not (tmp_path / "src" / "utils").exists()


def test_template_script_type(tmp_path: Path):
    copy_project(tmp_path, project_type="script")
    # Minimal: flat package at repo root (no src/), no notebooks
    pkg = tmp_path / "python_copier_template_example"
    assert (pkg / "__init__.py").exists()
    assert not (tmp_path / "src").exists()
    assert not (tmp_path / "notebooks").exists()
    # No DS extras
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert "optional-dependencies" not in pyproject_toml.get("project", {})
    # Regression: the flat-layout copies of __main__.py/logging_setup.py used
    # to wrap their .jinja suffix *inside* the `{% if %}` filename condition
    # (`...py.jinja{% endif %}` instead of `...py{% endif %}.jinja`), so
    # copier never recognised them as templates -- they were copied verbatim,
    # keeping a literal .jinja suffix and unrendered `{{ }}`/`{% %}` content.
    assert not list(pkg.glob("*.jinja"))
    assert "{% if" not in (pkg / "__main__.py").read_text()
    assert "{% if" not in (pkg / "logging_setup.py").read_text()


def test_template_cloud_provider_aws(tmp_path: Path):
    copy_project(tmp_path, project_type="web_api", cloud_provider="aws", aws_services="s3")
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert any(d.startswith("boto3") for d in deps)
    assert any(d.startswith("botocore") for d in deps)
    dev = pyproject_toml["dependency-groups"]["dev"]
    assert any("boto3-stubs[s3]" in d for d in dev)


def test_template_cloud_provider_gcp(tmp_path: Path):
    copy_project(tmp_path, project_type="web_api", cloud_provider="gcp")
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert any(d.startswith("google-cloud-storage") for d in deps)


def test_template_cloud_provider_azure(tmp_path: Path):
    copy_project(tmp_path, project_type="web_api", cloud_provider="azure")
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert any(d.startswith("azure-identity") for d in deps)


def test_template_include_sentry(tmp_path: Path):
    copy_project(tmp_path, include_sentry=True)
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("sentry-sdk") for d in pyproject_toml["project"]["dependencies"])
    main_file = tmp_path / "src" / "python_copier_template_example" / "__main__.py"
    assert "sentry_sdk.init" in main_file.read_text()


def test_template_include_mcp(tmp_path: Path):
    copy_project(tmp_path, include_mcp=True)
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d == "mcp" for d in pyproject_toml["project"]["dependencies"])
    assert (tmp_path / "src" / "python_copier_template_example" / "mcp_server.py").exists()


def test_template_no_ci(tmp_path: Path):
    copy_project(tmp_path, ci_provider="none")
    assert not (tmp_path / ".github" / "workflows").exists()
    # GitHub-specific files are still generated
    assert (tmp_path / ".github" / "actionlint.yaml").exists()


def test_template_log_library_default_is_structlog(tmp_path: Path):
    copy_project_recommended(tmp_path, project_type="cli")
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert "structlog" in deps
    assert "loguru" not in deps
    assert "picologging" not in deps
    logging_setup = (tmp_path / "src" / "recommended_example" / "logging_setup.py").read_text()
    assert "import structlog" in logging_setup


def test_template_log_library_loguru(tmp_path: Path):
    copy_project(tmp_path, log_library="loguru")
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert "loguru" in pyproject_toml["project"]["dependencies"]
    logging_setup = (tmp_path / "src" / "python_copier_template_example" / "logging_setup.py").read_text()
    assert "from loguru import logger" in logging_setup
    run = make_venv(tmp_path)
    run("uvx --from go-task-bin task check")
    # logger.bind(...).info(event, **kv) works the same as the structlog default
    run(
        "uv run --locked python -c "
        '"from python_copier_template_example.logging_setup import logger; '
        "logger.bind(task_id='T-123').info('job_done', chunks=3)\""
    )


def test_template_log_library_picologging(tmp_path: Path):
    copy_project(tmp_path, log_library="picologging")
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert "picologging" in pyproject_toml["project"]["dependencies"]
    logging_setup = (tmp_path / "src" / "python_copier_template_example" / "logging_setup.py").read_text()
    assert "import picologging as logging" in logging_setup
    run = make_venv(tmp_path)
    run("uvx --from go-task-bin task check")


def test_template_log_library_stdlib(tmp_path: Path):
    copy_project(tmp_path, log_library="logging")
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert not {"structlog", "loguru", "picologging"} & set(deps)
    logging_setup = (tmp_path / "src" / "python_copier_template_example" / "logging_setup.py").read_text()
    assert "import logging" in logging_setup
    run = make_venv(tmp_path)
    run("uvx --from go-task-bin task check")


def test_template_log_library_skipped_for_ros2(tmp_path: Path):
    copy_project_recommended(
        tmp_path,
        project_type="ros2",
        pkg_language="python",
        ros_distro="humble",
        ros2_package_manager="apt",
    )
    # ros2 packages use rclpy's own node logger; logging_setup.py isn't generated
    assert not list(tmp_path.rglob("logging_setup.py"))


def test_template_recommended_settings(tmp_path: Path):
    copy_project_recommended(tmp_path, project_type="data_science")
    # Accepting every "use the recommended ...?" gate still generates a
    # working project, using only the template's built-in defaults.
    assert (tmp_path / "pyproject.toml").exists()
    # use_gpu defaults to true for data_science -> Dockerfile.gpu present
    assert (tmp_path / "Dockerfile.gpu").exists()
    # the recommended license is MIT
    assert "MIT License" in (tmp_path / "LICENSE").read_text()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["license"] == "MIT"


def test_template_license_choice(tmp_path: Path):
    copy_project(tmp_path, license="GPL-3.0")
    assert "GNU GENERAL PUBLIC LICENSE" in (tmp_path / "LICENSE").read_text()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["license"] == "GPL-3.0"
    assert pyproject_toml["project"]["license-files"] == ["LICENSE"]


def test_template_license_proprietary(tmp_path: Path):
    copy_project(tmp_path, license="Proprietary")
    license_text = (tmp_path / "LICENSE").read_text()
    assert "All Rights Reserved" in license_text
    assert "UNAUTHORIZED COPYING" in license_text
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    # PEP 639 has no SPDX expression for "no license": omit the field entirely
    assert "license" not in pyproject_toml["project"]


def test_template_fair_metadata(tmp_path: Path):
    copy_project(
        tmp_path,
        fair=True,
        author_orcid="0000-0002-1825-0099",
        data_reusable=True,
        data_ethics=True,
    )
    cff = (tmp_path / "CITATION.cff").read_text()
    assert "cff-version: 1.2.0" in cff
    assert 'title: "python-copier-template-example"' in cff
    assert 'repository-code: "https://github.com/kasi-x/python-copier-template-example"' in cff
    assert 'license: "Apache-2.0"' in cff
    assert 'orcid: "https://orcid.org/0000-0002-1825-0099"' in cff
    reuse_toml = (tmp_path / "REUSE.toml").read_text()
    assert 'SPDX-License-Identifier = "Apache-2.0"' in reuse_toml
    pre_commit = (tmp_path / ".pre-commit-config.yaml").read_text()
    assert "cff-converter-python" in pre_commit
    assert "reuse-tool" in pre_commit
    assert (tmp_path / "data" / "DUO.md").exists()
    assert (tmp_path / "data" / "CARE.md").exists()
    assert "Traceability & provenance" in (tmp_path / "data" / "CARE.md").read_text()
    fair_software_workflow = tmp_path / ".github" / "workflows" / "fair-software.yml"
    assert fair_software_workflow.exists()
    assert "fair-software/howfairis-github-action@0.2.1" in fair_software_workflow.read_text()
    assert "fair-software/howfairis-github-action" in (tmp_path / "renovate.json").read_text()


def test_template_fair_off(tmp_path: Path):
    copy_project(tmp_path, fair=False)
    assert not (tmp_path / "CITATION.cff").exists()
    assert not (tmp_path / "REUSE.toml").exists()
    assert not (tmp_path / ".github" / "workflows" / "fair-software.yml").exists()
    assert "howfairis" not in (tmp_path / "renovate.json").read_text()
    pre_commit = (tmp_path / ".pre-commit-config.yaml").read_text()
    assert "cff-converter-python" not in pre_commit
    assert "reuse-tool" not in pre_commit


def test_template_data_governance_off_by_default(tmp_path: Path):
    # DUO/CARE are independent of fair -- a data_science project gets
    # neither sheet unless data_reusable/data_ethics are explicitly asked
    # for (example-answers.yml leaves both at their default: false).
    copy_project(tmp_path, fair=True)
    assert not (tmp_path / "data" / "DUO.md").exists()
    assert not (tmp_path / "data" / "CARE.md").exists()


def test_template_data_governance_skipped_for_competition(tmp_path: Path):
    # Competition projects never get the DUO/CARE sheets, even when asked.
    copy_project(tmp_path, competition=True, data_reusable=True, data_ethics=True)
    assert not (tmp_path / "data" / "DUO.md").exists()
    assert not (tmp_path / "data" / "CARE.md").exists()


@pytest.mark.parametrize("restricted_license", ["Proprietary", "Confidential"])
def test_template_fair_restricted_license(tmp_path: Path, restricted_license: str):
    copy_project(tmp_path, fair=True, license=restricted_license)
    cff = (tmp_path / "CITATION.cff").read_text()
    assert "cff-version: 1.2.0" in cff
    # CFF has no SPDX expression for "all rights reserved": omit the field
    assert "license:" not in cff
    # reuse only applies to open-source licenses
    assert not (tmp_path / "REUSE.toml").exists()
    pre_commit = (tmp_path / ".pre-commit-config.yaml").read_text()
    assert "cff-converter-python" in pre_commit
    assert "reuse-tool" not in pre_commit


def test_template_license_confidential(tmp_path: Path):
    copy_project(tmp_path, license="Confidential")
    license_text = (tmp_path / "LICENSE").read_text()
    assert "CONFIDENTIAL AND PROPRIETARY INFORMATION" in license_text
    assert "trade secrets" in license_text
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert "license" not in pyproject_toml["project"]


def test_template_license_confidential_recommended_elsewhere(tmp_path: Path):
    # Opting out of just the license/FAIR gate should still leave every
    # other section (docs, quality, integrations, ...) on its recommended
    # default.
    copy_project_recommended(
        tmp_path,
        use_recommended_license=False,
        license="Confidential",
        fair=False,
    )
    license_text = (tmp_path / "LICENSE").read_text()
    assert "CONFIDENTIAL AND PROPRIETARY INFORMATION" in license_text
    assert not (tmp_path / "CITATION.cff").exists()


def test_template_changelog(tmp_path: Path):
    copy_project(tmp_path)
    assert (tmp_path / "CHANGELOG.md").exists()
    assert (tmp_path / "cliff.toml").exists()


def test_template_gitlab(tmp_path: Path):
    copy_project(tmp_path, git_platform="gitlab.com", gitlab_group="mygroup")
    assert (tmp_path / ".gitlab-ci.yml").exists()
    assert not (tmp_path / ".github").exists()


def test_template_poetry(tmp_path: Path):
    copy_project(tmp_path, package_manager="poetry")
    assert (tmp_path / "poetry.lock").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert "tool" in pyproject_toml and "poetry" in pyproject_toml["tool"]
    readme = (tmp_path / "README.md").read_text()
    # only the uv-tested matrix gets the full "3.11 | 3.12 | 3.13 | 3.14" range
    assert "Python-3.11-3776AB" in readme


def test_template_readme_badges(tmp_path: Path):
    copy_project(tmp_path)  # example-answers.yml uses package_manager: uv
    readme = (tmp_path / "README.md").read_text()
    # only officially-documented tool badges: no unofficial/inferred ones
    # (e.g. uv, pixi have no official "used by" badge upstream)
    assert "astral-sh/ruff/main/assets/badge/v2.json" in readme
    assert "copier-org/copier/master/img/badge/badge-black.json" in readme
    assert "pre--commit-enabled-brightgreen" in readme
    assert "astral-sh/uv" not in readme
    assert "prefix-dev/pixi" not in readme
    assert "Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB" in readme


def test_template_task_runner_just(tmp_path: Path):
    copy_project(tmp_path, task_runner="just")
    assert (tmp_path / "justfile").exists()
    assert not (tmp_path / "Taskfile.yml").exists()
    assert not (tmp_path / "Makefile").exists()
    assert "lint:" in (tmp_path / "justfile").read_text()


def test_template_task_runner_make(tmp_path: Path):
    copy_project(tmp_path, task_runner="make")
    assert (tmp_path / "Makefile").exists()
    assert not (tmp_path / "Taskfile.yml").exists()
    assert "lint:" in (tmp_path / "Makefile").read_text()


def test_template_task_runner_poe(tmp_path: Path):
    copy_project(tmp_path, task_runner="poe")
    assert not (tmp_path / "Taskfile.yml").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert "lint" in pyproject_toml["tool"]["poe"]["tasks"]
    dev = pyproject_toml["dependency-groups"]["dev"]
    assert any(d.startswith("poethepoet") for d in dev)


def test_template_task_runner_pixi_native(tmp_path: Path):
    copy_project(tmp_path, package_manager="pixi", task_runner_pixi="pixi")
    assert not (tmp_path / "Taskfile.yml").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert "lint" in pyproject_toml["tool"]["pixi"]["feature"]["dev"]["tasks"]


def test_template_task_runner_pixi_with_task(tmp_path: Path):
    copy_project(tmp_path, package_manager="pixi", task_runner_pixi="task")
    assert (tmp_path / "Taskfile.yml").exists()
    pyproject = (tmp_path / "pyproject.toml").read_text()
    assert "[tool.pixi.feature.dev.tasks]" not in pyproject


def test_template_task_runner_just_works(tmp_path: Path):
    copy_project(tmp_path, task_runner="just")
    run = make_venv(tmp_path)
    run("uvx --from rust-just just lint")


def test_template_specialty_mcp_server(tmp_path: Path):
    copy_project(tmp_path, specialty="mcp_server")
    assert (tmp_path / "scripts" / "mcp_inspector.sh").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("mcp") for d in pyproject_toml["project"]["dependencies"])


def test_template_specialty_ai_agent(tmp_path: Path):
    copy_project(tmp_path, specialty="ai_agent")
    assert (tmp_path / "prompts" / "README.md").exists()
    assert (tmp_path / "src" / "python_copier_template_example" / "tools" / "__init__.py").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("pydantic-ai") for d in pyproject_toml["project"]["dependencies"])


def test_template_specialty_data_polars(tmp_path: Path):
    copy_project(tmp_path, specialty="data_polars")
    assert (tmp_path / "queries" / "README.md").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert any(d.startswith("polars") for d in deps)
    assert any(d.startswith("duckdb") for d in deps)


def test_template_specialty_rust_extension(tmp_path: Path):
    copy_project(tmp_path, specialty="rust_extension")
    assert (tmp_path / "rust" / "Cargo.toml").exists()
    assert (tmp_path / "rust" / "src" / "lib.rs").exists()


def test_template_specialty_pure_python_web(tmp_path: Path):
    copy_project(tmp_path, specialty="pure_python_web")
    assert (tmp_path / "app" / "app.py").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("python-fasthtml") for d in pyproject_toml["project"]["dependencies"])


def test_template_github_org_reflected(tmp_path: Path):
    copy_project(tmp_path, github_org="myorg")
    # github_org is used in generated URLs and badges
    readme = (tmp_path / "README.md").read_text()
    assert "myorg" in readme
    assert "DiamondLightSource" not in readme


def test_template_no_docker_has_no_docs_and_works(tmp_path: Path):
    copy_project(tmp_path, docker=False)
    container_doc = tmp_path / "docs" / "how-to" / "run-container.md"
    assert not container_doc.exists()
    run = make_venv(tmp_path)
    run("uvx --from go-task-bin task check")


def test_bad_repo_name(tmp_path: Path):
    with pytest.raises(ValueError, match="bad:thing is not a valid repo name"):
        copy_project(tmp_path, repo_name="bad:thing")


def test_django_not_supported_aborts(tmp_path: Path):
    # Selecting the web_django project type must abort generation with a
    # pointer to the alternatives, instead of generating a project.
    with pytest.raises(Exception, match="Django is not supported"):
        copy_project(tmp_path, project_type="web_django")


def test_web_api_ships_env_and_compose(tmp_path: Path):
    copy_project(tmp_path, project_type="web_api", docker=True)
    # cookiecutter-django style additions
    assert (tmp_path / ".editorconfig").exists()
    assert (tmp_path / ".env.example").exists()
    assert (tmp_path / ".dockerignore").exists()
    assert (tmp_path / "compose.local.yml").exists()
    # The compose file wires up the API + postgres
    compose = (tmp_path / "compose.local.yml").read_text()
    assert "postgres" in compose
    assert "8000:8000" in compose
    # .env is git-ignored
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".env" in gitignore


def test_web_api_ci_postgres_service(tmp_path: Path):
    # Without docker, the CI test job gets a postgres service container
    copy_project(tmp_path, project_type="web_api", docker=False)
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "postgres" in ci
    assert "postgres-host: localhost" in ci
    assert "postgres:17-alpine" in ci
    # No compose file when docker is off
    assert not (tmp_path / "compose.local.yml").exists()
    assert not (tmp_path / ".dockerignore").exists()


def test_library_no_web_api_extras(tmp_path: Path):
    # A plain library should not get the web_api-only compose/env additions
    copy_project(tmp_path, project_type="library", docker=False)
    assert not (tmp_path / "compose.local.yml").exists()
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "postgres" not in ci
    # .env.example and .editorconfig are always shipped
    assert (tmp_path / ".env.example").exists()
    assert (tmp_path / ".editorconfig").exists()


def test_pr_template_shipped(tmp_path: Path):
    copy_project(tmp_path)
    pr = tmp_path / ".github" / "PULL_REQUEST_TEMPLATE" / "pull_request_template.md"
    assert pr.exists()
    assert "Checks for reviewer" in pr.read_text()


def test_template_ros2_python_apt(tmp_path: Path):
    copy_project_recommended(
        tmp_path,
        project_type="ros2",
        pkg_language="python",
        ros_distro="humble",
        ros2_package_manager="apt",
    )
    # ament_python layout
    assert (tmp_path / "package.xml").exists()
    assert "ament_python" in (tmp_path / "package.xml").read_text()
    assert "<depend>rclpy</depend>" in (tmp_path / "package.xml").read_text()
    assert (tmp_path / "setup.py").exists()
    assert (tmp_path / "setup.cfg").exists()
    assert (tmp_path / "resource" / "recommended_example").exists()
    assert (tmp_path / "test" / "test_flake8.py").exists()
    assert (tmp_path / "recommended_example" / "main.py").exists()
    # The standard toolchain coexists: pyproject has [project] (no rclpy dep —
    # package.xml owns the ROS deps), uv.lock and Dockerfile are generated.
    pyproject = (tmp_path / "pyproject.toml").read_text()
    assert "[project]" in pyproject
    assert "requires-python" in pyproject
    assert "rclpy" not in pyproject
    assert (tmp_path / "uv.lock").exists()
    assert (tmp_path / "Dockerfile").exists()
    # Humble -> Python 3.10
    assert (tmp_path / ".python-version").read_text().strip() == "3.10"
    # CI uses industrial_ci (apt flavour)
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "industrial_ci" in ci
    assert "ROS_DISTRO: humble" in ci
    # ros2-specific Dockerfile + the standard one coexist
    dockerfile = (tmp_path / "Dockerfile.ros2").read_text()
    assert "ros:humble-ros-base" in dockerfile
    # justfile drives colcon
    justfile = (tmp_path / "justfile").read_text()
    assert "colcon build" in justfile


def test_template_ros2_cpp_apt(tmp_path: Path):
    copy_project_recommended(
        tmp_path,
        project_type="ros2",
        pkg_language="cpp",
        ros_distro="humble",
        ros2_package_manager="apt",
    )
    # ament_cmake layout
    assert (tmp_path / "CMakeLists.txt").exists()
    assert "ament_cmake" in (tmp_path / "package.xml").read_text()
    assert "<depend>rclcpp</depend>" in (tmp_path / "package.xml").read_text()
    assert (tmp_path / "src" / "talker.cpp").exists()
    assert (tmp_path / "include" / "recommended_example" / "talker.hpp").exists()
    # C++ package: the build is CMake, so no pyproject.toml/setup.py is needed
    # (the standard toolchain files stay, but the ament build is authoritative).
    assert not (tmp_path / "pyproject.toml").exists()
    assert not (tmp_path / "setup.py").exists()


def test_template_ros2_python_pixi(tmp_path: Path):
    copy_project_recommended(
        tmp_path,
        project_type="ros2",
        pkg_language="python",
        ros_distro="jazzy",
        ros2_package_manager="pixi",
    )
    # pixi.toml with the RoboStack distro channel
    pixi = (tmp_path / "pixi.toml").read_text()
    assert "robostack-jazzy" in pixi
    assert "ros-jazzy-rclpy" in pixi
    # Jazzy -> Python 3.12
    assert (tmp_path / ".python-version").read_text().strip() == "3.12"
    # CI uses setup-pixi
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "setup-pixi" in ci
    assert "industrial_ci" not in ci
    # Dockerfile.ros2 pixi flavour
    dockerfile = (tmp_path / "Dockerfile.ros2").read_text()
    assert "pixi install" in dockerfile
    # pixi manages everything: no justfile, package_manager is pixi
    assert not (tmp_path / "justfile").exists()
    assert (tmp_path / "pixi.lock").exists()
    # pyproject still coexists (dev tooling config)
    assert (tmp_path / "pyproject.toml").exists()
    assert "[project]" in (tmp_path / "pyproject.toml").read_text()


def test_template_ros2_coexists_with_standard_tooling(tmp_path: Path):
    copy_project_recommended(
        tmp_path,
        project_type="ros2",
        pkg_language="python",
        ros_distro="humble",
        ros2_package_manager="apt",
    )
    # Docs, ASCII banner and dev tooling all coexist with the ament layout
    assert (tmp_path / "docs").exists()
    assert (tmp_path / "tools" / "ascii_banner.py").exists()
    assert (tmp_path / "NOTICE").exists()
    # The ros2 package __init__ exports __version__ (docs import it)
    init = (tmp_path / "recommended_example" / "__init__.py").read_text()
    assert "__version__" in init
    # devcontainer is ROS-aware and rendered (no raw jinja)
    devcontainer = (tmp_path / ".devcontainer" / "devcontainer.json").read_text()
    assert "Dockerfile.ros2" in devcontainer
    assert "{%" not in devcontainer


def test_dots_in_package_name(tmp_path: Path):
    copy_project(tmp_path, repo_name="dots.in.name")


def test_example_repo_updates(tmp_path: Path):
    generated_path = tmp_path / "generated"
    example_url = "https://github.com/DiamondLightSource/python-copier-template-example.git"
    example_path = tmp_path / "example"
    copy_project(generated_path)
    run_pipe(f"git clone {example_url} {example_path}")
    with Path(example_path / ".copier-answers.yml").open() as f:
        d = yaml.safe_load(f)
    d["_src_path"] = str(TOP)
    with Path(example_path / ".copier-answers.yml").open("w") as f:
        yaml.dump(d, f)
    run = functools.partial(run_pipe, cwd=str(example_path))
    run("git config user.email 'you@example.com'")
    run("git config user.name 'Your Name'")
    run("git commit -am 'Update src'")
    run(
        f"uvx --with copier-template-extensions copier update --defaults --vcs-ref=HEAD --trust --data-file {TOP}/example-answers.yml"
    )
    output = run(
        # Git directory expected to be different
        "diff -ur --exclude=.git --exclude=.venv --exclude='*.egg-info' --exclude=_version.py "
        # uv lock expected to be different
        "--exclude=uv.lock "
        # The commit hash is different for some reason
        "--ignore-matching-lines='^_commit: ' "
        # If we tag an existing commit that has been pushed to main, then the copier
        # update on the old commit id will be generated with the new tag name, which
        # means the link will not be updated. As this only affects the example repo
        # which is the only thing that points to main then we ignore it
        "--ignore-matching-lines='^For more information on common tasks like setting' "
        f"{generated_path} {example_path}"
    )
    assert not output, output


def test_gitignore_same():
    with (
        Path(TOP / ".gitignore").open() as top_gi,
        Path(TOP / "template" / ".gitignore").open() as template_gi,
    ):
        assert top_gi.read() == template_gi.read()


def test_private_member_access(tmp_path: Path):
    code = """
class MyClass:
    def __init__(self):
        self.foo: int = 1
        self._bar: int = 2

obj = MyClass()
print(obj.foo)
print(obj._bar)
"""

    copy_project(tmp_path)
    run = make_venv(tmp_path)

    # Private member access should be allowed in tests
    test_file = tmp_path / "tests" / "test_private_access.py"
    with test_file.open("w") as stream:
        stream.write(code)
    run("ruff check")

    # Private member access should not be allowed in src
    src_file = tmp_path / "src" / "python_copier_template_example" / "private_access.py"
    with src_file.open("w") as stream:
        stream.write(code)
    with pytest.raises(AssertionError, match=r"private-member-access: Private member accessed: `_bar`"):
        run("ruff check")


def test_pep8_naming(tmp_path: Path):
    code = """
myVariable = "foo"
"""

    copy_project(tmp_path)
    run = make_venv(tmp_path)

    src_file = tmp_path / "src" / "python_copier_template_example" / "bad_example.py"
    with src_file.open("w") as stream:
        stream.write(code)
    with pytest.raises(AssertionError, match=r"mixed-case-variable-in-global-scope.*"):
        run("ruff check")


def test_basedpyright_works_in_none_typing_mode(tmp_path: Path):
    copy_project(tmp_path, strictness="none")
    pyproject_toml = tmp_path / "pyproject.toml"

    # none: pytest + ruff (minimal rules) - no basedpyright, no type-checking env
    assert "basedpyright" not in pyproject_toml.read_text()
    assert "[tool.ruff]" in pyproject_toml.read_text()
    assert "type-check" not in (tmp_path / "Taskfile.yml").read_text()


def test_basedpyright_works_in_basic_mode(tmp_path: Path):
    copy_project(tmp_path, strictness="basic")
    pyproject_toml = tmp_path / "pyproject.toml"

    # basic: ruff but no type checking
    assert "[tool.ruff]" in pyproject_toml.read_text()
    assert "basedpyright" not in pyproject_toml.read_text()
    assert "type-check" not in (tmp_path / "Taskfile.yml").read_text()


def test_basedpyright_works_with_external_deps(tmp_path: Path):
    copy_project(tmp_path)
    # Add an external dependency (regex insert -- log_library picks which
    # logging package, if any, already opens the `dependencies = [...]` array)
    pyproject_toml = tmp_path / "pyproject.toml"
    text = pyproject_toml.read_text()
    text, n = re.subn(r"dependencies = \[", 'dependencies = ["numpy", ', text, count=1)
    assert n == 1, "could not find dependencies array in generated pyproject.toml"
    pyproject_toml.write_text(text)
    # And some code that uses it
    src_file = tmp_path / "src" / "python_copier_template_example" / "example.py"
    src_file.write_text("""
import numpy as np

def is_big(arr: np.ndarray) -> bool:
    return arr.size > 0
""")
    # Ensure basedpyright is still happy
    run = make_venv(tmp_path)
    run("uvx --from go-task-bin task type-check")


def test_full_strictness_mode(tmp_path: Path):
    copy_project(tmp_path, strictness="full")
    pyproject_toml = tmp_path / "pyproject.toml"

    # Check strict mode with Any-reporting is configured
    assert 'typeCheckingMode = "strict"' in pyproject_toml.read_text()
    assert "reportAny = true" in pyproject_toml.read_text()


def test_works_with_pydocstyle(tmp_path: Path):
    # Use English docstrings (allow_japanese=False) so ruff's D415
    # (punctuation check) applies cleanly.
    copy_project(tmp_path, allow_japanese=False)
    pyproject_toml = tmp_path / "pyproject.toml"
    text = (
        pyproject_toml.read_text()
        .replace('"C4",', '"C4", "D",')  # Enable all pydocstyle
        .replace(
            '"tests/**/*" = [',
            '"tests/**/*" = [\n    "D",',
        )
    )
    # Add __init__.py as a separate key at the end of the per-file-ignores table
    text += '\n"__init__.py" = ["D104"]\n'
    pyproject_toml.write_text(text)

    # Ensure ruff is still happy
    run = make_venv(tmp_path)
    run("ruff check")


@pytest.mark.parametrize(
    "override",
    [
        {},
        {"docker": True},
        {"docker": True, "docker_debug": True},
        {"pypi": True},
        {"docs_type": "sphinx"},
        {"docs_type": "zensical"},
        {"docs_type": "great-docs"},
        {"package_manager": "pixi"},
    ],
)
def test_renovate_actions_match_what_is_shipped(override: dict, tmp_path: Path):
    # Generate a project with the given answers
    answers = {
        "docker": False,
        "docker_debug": False,
        "pypi": False,
        "docs_type": "README",
    }
    answers.update(override)
    copy_project(tmp_path, **answers)
    # Find the GitHub actions ignored by renovate
    renovate_config_path = tmp_path / "renovate.json"
    renovate_config = json.loads(renovate_config_path.read_text())
    config_github_actions = set(renovate_config["packageRules"][1]["matchPackageNames"])
    # Find the GitHub actions actually used in the workflows
    used_github_actions = set[str]()
    for workflow_file in (tmp_path / ".github" / "workflows").glob("*.yml"):
        workflow = yaml.safe_load(workflow_file.read_text())
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                action = step.get("uses")
                if action:
                    used_github_actions.add(action.split("@")[0])
    # Check they match
    assert used_github_actions == config_github_actions


def test_python_versions_match(tmp_path: Path):
    copy_project(tmp_path)
    # Grab the python versions from ci.yml
    ci_yaml = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(ci_yaml.read_text())
    python_versions = workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"]
    # Check .python-version is the first of these
    python_version_file = tmp_path / ".python-version"
    min_version = python_version_file.read_text().strip()
    assert python_versions[0] == min_version
    # Check pyproject.toml has correct requires-python and classifiers
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["requires-python"] == f">={min_version}"
    for version in python_versions:
        assert f"Programming Language :: Python :: {version}" in pyproject_toml["project"]["classifiers"]
