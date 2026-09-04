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
    pyproject = (tmp_path / "pyproject.toml").read_text()
    assert "[tool.basedpyright]" in pyproject
    assert "[tool.pyrefly]" in pyproject


def test_template_ty(tmp_path: Path):
    copy_project(tmp_path, type_checker="ty")
    pyproject = (tmp_path / "pyproject.toml").read_text()
    # basedpyright is always present; ty is the secondary checker.
    assert "[tool.basedpyright]" in pyproject
    assert "[tool.ty]" in pyproject


def test_template_no_docs(tmp_path: Path):
    copy_project(tmp_path, docs_type="README")
    # README-only: no docs site config, no docs/ tree, no docs build task
    assert not (tmp_path / "zensical.toml").exists()
    assert not (tmp_path / "docs").exists()
    assert "task docs" not in (tmp_path / "Taskfile.yml").read_text()


def test_template_zensical_docs(tmp_path: Path):
    copy_project(tmp_path, docs_type="zensical")
    pyproject_toml = tmp_path / "pyproject.toml"
    assert '"zensical"' in pyproject_toml.read_text()
    assert (tmp_path / "zensical.toml").exists()
    assert (tmp_path / "docs").exists()


def test_template_great_docs(tmp_path: Path):
    copy_project(tmp_path, docs_type="great-docs")
    assert (tmp_path / "great-docs.yml").exists()
    assert (tmp_path / "index.qmd").exists()


def test_template_kaggle_competition(tmp_path: Path):
    copy_project(tmp_path, project_type="online_judge", oj_category="data_science", oj_kind="kaggle")
    # src/ with the Kaggle dirs; the analysis-only DS dirs are not generated
    assert (tmp_path / "src").is_dir()
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "models").exists()
    assert not (tmp_path / "notebooks").exists()
    assert not (tmp_path / "paper").exists()
    # Kaggle dirs inside src/
    for d in ["configs", "data", "input", "output", "features", "logs", "models", "notebook", "scripts", "utils"]:
        assert (tmp_path / "src" / d).is_dir(), f"missing src/{d}"
    # utils is the installable package
    assert (tmp_path / "src" / "utils" / "__init__.py").exists()
    assert (tmp_path / "src" / "utils" / "config.py").exists()
    assert (tmp_path / "src" / "utils" / "modeling" / "train.py").exists()
    # GPU artifacts (kaggle implies the GPU Dockerfile)
    assert (tmp_path / "Dockerfile.gpu").exists()
    assert (tmp_path / ".devcontainer" / "devcontainer.gpu.json").exists()
    # no standard package dir
    assert not (tmp_path / "src" / "python_copier_template_example").exists()
    # Taskfile exists
    assert (tmp_path / "Taskfile.yml").exists()
    # pyproject references utils and the competition deps
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("typer") for d in pyproject_toml["project"]["dependencies"])
    assert any(d.startswith("structlog") for d in pyproject_toml["project"]["dependencies"])
    # ML tools and experiment extras
    assert any(d.startswith("optuna") for d in pyproject_toml["project"]["dependencies"])
    assert any(d.startswith("torch") for d in pyproject_toml["project"]["dependencies"])
    # duckdb/polars base deps apply to kaggle too (inherited from competition)
    assert any(d.startswith("polars") for d in pyproject_toml["project"]["dependencies"])
    assert any(d.startswith("duckdb") for d in pyproject_toml["project"]["dependencies"])
    experiment = pyproject_toml["project"]["optional-dependencies"]["experiment"]
    assert any(d.startswith("marimo") for d in experiment)
    assert any(d.startswith("matplotlib") for d in experiment)
    # marimo notebook exists
    assert (tmp_path / "src" / "notebook" / "explore.py").exists()
    # no solutions/ tree (that is for the other online_judge kinds)
    assert not (tmp_path / "solutions").exists()


def test_template_kaggle_deptry_ignores_match_shipped_deps(tmp_path: Path):
    """The kaggle render's deptry ignores must cover its own dep sets.

    Regression: the kaggle render once failed `task type-check` — unused
    `responses` dev dep (DEP002), unused ML deps (DEP002), and the
    installable `utils` package's self-imports (DEP003). The ignores below
    pin the contract: every ML dep and `utils` must be ignored, and no
    stale ignore (like `responses`) may linger.
    """
    copy_project(tmp_path, project_type="online_judge", oj_category="data_science", oj_kind="kaggle")
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    ignores = pyproject_toml["tool"]["deptry"]["per_rule_ignores"]
    deps = pyproject_toml["project"]["dependencies"]
    ml_deps = [d.split(">")[0].split("<")[0].split("[")[0].split("=")[0] for d in deps]
    for dep in ("hydra-core", "lightgbm", "omegaconf", "optuna", "pandas", "pyyaml", "torch", "torchvision", "xgboost"):
        assert dep in ml_deps, f"{dep} missing from kaggle deps"
        assert dep in ignores, f"{dep} missing from deptry DEP002 ignores"
    dev_deps = pyproject_toml.get("dependency-groups", {}).get("dev", [])
    assert "responses" not in dev_deps, "stale responses dev dep"
    assert "responses" not in ignores, "stale responses ignore"


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
        "queries/README.md",
        "queries/example.sql",
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
    # experiment extras + the duckdb/polars base deps
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    experiment = pyproject_toml["project"]["optional-dependencies"]["experiment"]
    assert any(d.startswith("marimo") for d in experiment)
    deps = pyproject_toml["project"]["dependencies"]
    assert any(d.startswith("duckdb") for d in deps)
    assert any(d.startswith("pyarrow") for d in deps)
    assert any(d.startswith("polars") for d in deps)
    # No competition artifacts
    assert not (tmp_path / "src" / "utils").exists()


def test_template_oj_ctf_workspace(tmp_path: Path):
    """oj_category=ctf: the OJ-owned CTF path ships the same shape as the
    library/cli include_ctf layer (challenges + ctf extra + AGENTS.md)."""
    copy_project(tmp_path, project_type="online_judge", oj_category="ctf", oj_kind="ctf")
    assert (tmp_path / "challenges" / "pwn" / "example" / "solve.py").exists()
    assert (tmp_path / "tests" / "test_ctf_example.py").exists()
    assert (tmp_path / "AGENTS.md").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["optional-dependencies"]["ctf"] == [
        "pwntools>=4.13,<5",
        "z3-solver>=4.13,<5",
    ]
    readme = (tmp_path / "README.md").read_text()
    assert "challenges/pwn/example/solve.py" in readme


def test_template_atcoder_workspace(tmp_path: Path):
    # code-submission judge: a bare workspace, no solutions/ scaffold — the
    # user drives oj/atcoder-cli which create their own dirs and test/ files
    copy_project(tmp_path, project_type="online_judge", oj_category="competitive_coding", oj_kind="atcoder")
    assert not (tmp_path / "solutions").exists()
    assert not (tmp_path / "tests" / "test_samples.py").exists()
    # No package layout at all: no src/, no flat package, no CLI/logging files
    assert not (tmp_path / "src").exists()
    assert not list(tmp_path.glob("*.py"))
    assert not list(tmp_path.rglob("__main__.py"))
    assert not list(tmp_path.rglob("logging_setup.py"))
    assert not (tmp_path / "tests" / "test_cli.py").exists()
    # stdlib only: no structlog or other runtime deps
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["dependencies"] == []
    # no dist/pypi CI jobs for a submission repo
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "dist:" not in ci
    # ruff is relaxed for contest code (project-wide, not per solutions/)
    ruff = (tmp_path / "pyproject.toml").read_text()
    assert "A001" in ruff  # builtin shadowing relaxed
    assert "solutions" not in ruff
    # README points at the oj / acc workflow
    readme = (tmp_path / "README.md").read_text()
    assert "oj download" in readme


def test_template_leetcode_workspace_like_atcoder(tmp_path: Path):
    copy_project(tmp_path, project_type="online_judge", oj_category="competitive_coding", oj_kind="leetcode")
    assert not (tmp_path / "solutions").exists()
    assert not (tmp_path / "src").exists()
    assert not (tmp_path / "tests" / "test_samples.py").exists()


def test_template_yukicoder_workspace(tmp_path: Path):
    # yukicoder is a code-submission judge: same bare workspace as atcoder,
    # driven with oj (download / test / submit all work for yukicoder)
    copy_project(tmp_path, project_type="online_judge", oj_category="competitive_coding", oj_kind="yukicoder")
    assert not (tmp_path / "solutions").exists()
    assert not (tmp_path / "tests" / "test_samples.py").exists()
    assert not (tmp_path / "src").exists()
    assert not list(tmp_path.glob("*.py"))
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["dependencies"] == []
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "dist:" not in ci
    # README drives the oj workflow with a yukicoder URL example
    readme = (tmp_path / "README.md").read_text()
    assert "oj download https://yukicoder.me/problems/no/1234" in readme
    assert "oj submit https://yukicoder.me/problems/no/1234 main.py" in readme


def test_template_aoj_workspace(tmp_path: Path):
    # AOJ is a code-submission judge: same bare workspace, but oj cannot
    # submit to AOJ — the README leads with aoj-cli
    copy_project(tmp_path, project_type="online_judge", oj_category="competitive_coding", oj_kind="aoj")
    assert not (tmp_path / "solutions").exists()
    assert not (tmp_path / "tests" / "test_samples.py").exists()
    assert not (tmp_path / "src").exists()
    assert not list(tmp_path.glob("*.py"))
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["dependencies"] == []
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "dist:" not in ci
    # README leads with aoj-cli (init / test / submit) for AOJ
    readme = (tmp_path / "README.md").read_text()
    assert "aoj init ITP1_1_A" in readme
    assert "aoj submit main.py --lang Python3" in readme


def test_template_online_judge_repo_lints_clean(tmp_path: Path):
    """The empty workspace renders a ruff/type-check-clean repo (no sources)."""
    copy_project_recommended(tmp_path, project_type="online_judge", oj_category="competitive_coding", oj_kind="atcoder")
    run = make_venv(tmp_path)
    run("uvx --from rust-just just check")


def test_template_online_judge_no_solutions_for_kaggle(tmp_path: Path):
    # kaggle is a result competition: no solutions/ scripts tree either
    copy_project(tmp_path, project_type="online_judge", oj_category="data_science", oj_kind="kaggle")
    assert not (tmp_path / "solutions").exists()


def test_template_agents_md_present_by_default(tmp_path: Path):
    """library ships AGENTS.md and the README points at it."""
    copy_project(tmp_path, project_type="library")
    agents = tmp_path / "AGENTS.md"
    assert agents.exists()
    body = agents.read_text()
    assert "task check" in body
    assert ".github/CONTRIBUTING.md" in body
    readme = (tmp_path / "README.md").read_text()
    assert "AGENTS.md" in readme


def test_template_agents_md_present_for_kaggle_and_opt_in_judges(tmp_path: Path):
    """kaggle always ships AGENTS.md; atcoder/leetcode ship it when
    oj_allow_ai is Yes (with the judge-specific workspace note)."""
    kaggle_path = tmp_path / "kaggle"
    copy_project(kaggle_path, project_type="online_judge", oj_category="data_science", oj_kind="kaggle")
    kaggle_agents = (kaggle_path / "AGENTS.md").read_text()
    assert (kaggle_path / "AGENTS.md").exists()
    assert "src/input/" in kaggle_agents

    atcoder_path = tmp_path / "atcoder"
    copy_project(
        atcoder_path, project_type="online_judge", oj_category="competitive_coding", oj_kind="atcoder", oj_allow_ai=True
    )
    atcoder_agents = (atcoder_path / "AGENTS.md").read_text()
    assert (atcoder_path / "AGENTS.md").exists()
    assert "atcoder" in atcoder_agents
    assert "AGENTS.md" in (atcoder_path / "README.md").read_text()

    leetcode_path = tmp_path / "leetcode"
    copy_project(
        leetcode_path,
        project_type="online_judge",
        oj_category="competitive_coding",
        oj_kind="leetcode",
        oj_allow_ai=True,
    )
    assert (leetcode_path / "AGENTS.md").exists()


def test_template_agents_md_absent_for_ai_ng_judges(tmp_path: Path):
    """AI-NG workspaces omit AGENTS.md and its README mention (byte-identical
    renders apart from the pre-existing oj_kind branches)."""
    cases = [
        ("atcoder", {}),
        ("atcoder", {"oj_allow_ai": False}),
        ("leetcode", {}),
        ("yukicoder", {}),
        ("aoj", {}),
    ]
    for index, (oj_kind, extra) in enumerate(cases):
        project_path = tmp_path / f"case_{index}"
        copy_project(
            project_path, project_type="online_judge", oj_category="competitive_coding", oj_kind=oj_kind, **extra
        )
        assert not (project_path / "AGENTS.md").exists()
        readme = (project_path / "README.md").read_text()
        assert "AGENTS.md" not in readme


def test_template_agents_md_absent_for_ros2_and_micropython(tmp_path: Path):
    """ros2 / micropython never ship the agent guide."""
    ros2_path = tmp_path / "ros2"
    copy_project(ros2_path, project_type="ros2", pkg_language="python", ros_distro="humble", ros2_package_manager="apt")
    assert not (ros2_path / "AGENTS.md").exists()
    micro_path = tmp_path / "micro"
    copy_project(micro_path, project_type="micropython", micropython_port="esp32")
    assert not (micro_path / "AGENTS.md").exists()


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
    copy_project(tmp_path, project_type="cli", include_mcp=True)
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("mcp[cli]") for d in pyproject_toml["project"]["dependencies"])
    pkg_dir = tmp_path / "src" / "python_copier_template_example"
    assert (pkg_dir / "mcp_server.py").exists()
    assert (tmp_path / "tests" / "test_mcp_server.py").exists()
    scripts = pyproject_toml["project"]["scripts"]
    assert "mcp-server-python-copier-template-example" in scripts
    # mcp_server.py is covered by the type checkers (v2 SDK ships stubs) and
    # the scaffold uses the v2 API with safe-by-default HTTP serving.
    mcp_server = (pkg_dir / "mcp_server.py").read_text()
    assert "from mcp.server import MCPServer" in mcp_server
    assert "fastmcp" not in mcp_server
    assert "streamable-http" in mcp_server
    # Security hardening: non-local binds require MCP_ALLOWED_HOSTS, --host /
    # --port are exposed, and a /health custom route is registered.
    assert "MCP_ALLOWED_HOSTS" in mcp_server
    assert "--host" in mcp_server
    assert '"/health"' in mcp_server
    assert "transport_security" in mcp_server


def test_template_mcp_docker_task(tmp_path: Path):
    """With docker enabled, the task runner ships an mcp-serve task that
    builds and runs the MCP server over Streamable HTTP."""
    copy_project(tmp_path, project_type="cli", include_mcp=True, docker=True)
    taskfile = (tmp_path / "Taskfile.yml").read_text()
    assert "mcp-serve" in taskfile
    assert "mcp-server-python-copier-template-example" in taskfile
    assert "MCP_ALLOWED_HOSTS" in taskfile
    # The Dockerfile exposes the MCP port and documents the run command.
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "EXPOSE 8000" in dockerfile
    assert "mcp-server-python-copier-template-example" in dockerfile
    # .env.example documents the allowlist variable.
    env_example = (tmp_path / ".env.example").read_text()
    assert "MCP_ALLOWED_HOSTS" in env_example
    # .mcp.json points the host at the stdio command (zero-config registration).
    mcp_json = json.loads((tmp_path / ".mcp.json").read_text())
    server = mcp_json["mcpServers"]["python-copier-template-example"]
    assert server["args"] == ["run", "mcp-server-python-copier-template-example"]
    # README advertises the registration path.
    assert ".mcp.json" in (tmp_path / "README.md").read_text()


def test_template_mcp_no_docker_no_task(tmp_path: Path):
    """Without docker, no mcp-serve task is generated."""
    copy_project(tmp_path, project_type="cli", include_mcp=True, docker=False)
    taskfile = (tmp_path / "Taskfile.yml").read_text()
    assert "mcp-serve" not in taskfile


def test_template_mcp_runs_in_process(tmp_path: Path):
    """The generated MCP server must actually work against the installed v2
    SDK: sync the project, run the in-process client test, and type-check the
    scaffold (no exclusions)."""
    copy_project(tmp_path, project_type="cli", include_mcp=True)
    run = make_venv(tmp_path)
    run("uv run --locked pytest -q")
    run("uv run --locked basedpyright src tests")
    run("uv run --locked ruff check src tests")


def test_template_mcp_not_offered_to_library(tmp_path: Path):
    """A plain library must not ship a server module, and forcing the answer
    must not add an orphan mcp dep. (Adding the web_api layer opts back in:
    see test_template_mcp_on_web_api.)"""
    copy_project(tmp_path, project_type="library", include_mcp=True)
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert not any(d.startswith("mcp") for d in pyproject_toml["project"]["dependencies"])
    assert not (tmp_path / "src" / "python_copier_template_example" / "mcp_server.py").exists()
    assert not (tmp_path / "tests" / "test_mcp_server.py").exists()


def test_template_mcp_not_offered_to_online_judge(tmp_path: Path):
    """online_judge renders no package module: forcing include_mcp must not
    add an orphan mcp dependency or a server file."""
    copy_project(
        tmp_path, project_type="online_judge", oj_category="competitive_coding", oj_kind="atcoder", include_mcp=True
    )
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert not any(d.startswith("mcp") for d in pyproject_toml["project"]["dependencies"])
    assert not (tmp_path / "mcp_server.py").exists()
    assert not (tmp_path / "tests" / "test_mcp_server.py").exists()


def test_template_mcp_not_offered_to_data_science(tmp_path: Path):
    """data_science / script / kaggle render no mcp_server.py variant:
    forcing include_mcp must not add an orphan mcp dependency."""
    cases = [
        ("data_science", {}),
        ("script", {}),
        ("online_judge", {"oj_category": "data_science", "oj_kind": "kaggle"}),
    ]
    for index, (project_type, extra) in enumerate(cases):
        project_path = tmp_path / f"case_{index}"
        copy_project(project_path, project_type=project_type, include_mcp=True, **extra)
        pyproject_toml = tomllib.loads((project_path / "pyproject.toml").read_text())
        assert not any(d.startswith("mcp") for d in pyproject_toml["project"]["dependencies"])
        assert not (project_path / "tests" / "test_mcp_server.py").exists()


def test_template_mcp_on_web_api(tmp_path: Path):
    """web_api offers the MCP scaffold in app/: the server module, its
    in-process client test, the mcp dependency and the console script all
    point at the app import root."""
    copy_project(
        tmp_path,
        project_type="web_api",
        use_recommended_integrations=False,
        include_mcp=True,
    )
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("mcp[cli]") for d in pyproject_toml["project"]["dependencies"])
    assert (tmp_path / "app" / "mcp_server.py").exists()
    assert (tmp_path / "tests" / "test_mcp_server.py").exists()
    test_body = (tmp_path / "tests" / "test_mcp_server.py").read_text()
    assert "from app import mcp_server" in test_body
    assert "app.mcp_server:main" in (tmp_path / "pyproject.toml").read_text()
    # no <pkg>-side duplicate
    assert not list(tmp_path.rglob("src/*/mcp_server.py"))


def test_template_mcp_runs_on_web_api_in_process(tmp_path: Path):
    """The app/-hosted MCP server must actually work: sync the web_api+MCP
    project and run its in-process client test plus the API tests."""
    copy_project(
        tmp_path,
        project_type="web_api",
        use_recommended_integrations=False,
        include_mcp=True,
    )
    run = make_venv(tmp_path)
    run("uv run --locked pytest -q")
    run("uv run --locked ruff check app tests")


def test_template_mcp_flat_layout(tmp_path: Path):
    """The flat-layout package variant also ships mcp_server.py and its
    console script."""
    copy_project(tmp_path, project_type="cli", layout="flat", include_mcp=True)
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("mcp[cli]") for d in pyproject_toml["project"]["dependencies"])
    assert (tmp_path / "python_copier_template_example" / "mcp_server.py").exists()
    assert (tmp_path / "tests" / "test_mcp_server.py").exists()


def test_template_no_ci(tmp_path: Path):
    copy_project(tmp_path, ci_provider="none")
    assert not (tmp_path / ".github" / "workflows").exists()
    # GitHub-specific files are still generated
    assert (tmp_path / ".github" / "actionlint.yaml").exists()


def test_template_include_ctf(tmp_path: Path):
    """include_ctf layers the participant workspace: solve.py starter, its
    test, the ctf extra, and the gitignore guards."""
    copy_project(tmp_path, project_type="cli", include_ctf=True)
    assert (tmp_path / "challenges" / "pwn" / "example" / "solve.py").exists()
    assert (tmp_path / "tests" / "test_ctf_example.py").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["optional-dependencies"]["ctf"] == [
        "pwntools>=4.13,<5",
        "z3-solver>=4.13,<5",
    ]
    gitignore = (tmp_path / ".gitignore").read_text()
    assert "challenges/**/vuln" in gitignore


def test_template_include_ctf_runs(tmp_path: Path):
    """The generated solve.py starter must actually run: sync the project
    and execute both the starter directly and its generated test."""
    copy_project(tmp_path, project_type="cli", include_ctf=True)
    run = make_venv(tmp_path)
    run(
        "uv run --locked python challenges/pwn/example/solve.py",
        # noqa: S603 -- test helper, fixed argv
    )
    run("uv run --locked pytest tests/test_ctf_example.py -q")
    run("uv run --locked ruff check challenges tests/test_ctf_example.py")


def test_template_include_ctf_not_offered_elsewhere(tmp_path: Path):
    """Forcing include_ctf outside library/cli must not leak the workspace
    or the ctf extra (ctf_effective guard)."""
    cases = [
        ("web_api", {}),
        ("data_science", {}),
        ("script", {}),
        ("online_judge", {"oj_category": "competitive_coding", "oj_kind": "atcoder"}),
    ]
    for index, (project_type, extra) in enumerate(cases):
        project_path = tmp_path / f"case_{index}"
        copy_project(project_path, project_type=project_type, include_ctf=True, **extra)
        pyproject = tomllib.loads((project_path / "pyproject.toml").read_text())
        assert "ctf" not in pyproject["project"].get("optional-dependencies", {})
        assert not (project_path / "challenges").exists()
        assert not (project_path / "tests" / "test_ctf_example.py").exists()


def test_template_include_scraping_httpx(tmp_path: Path):
    """include_scraping layers the polite fetcher: CHARTER.md, fetcher.py,
    its offline test, the httpx dep, ruff banned-api and gitignore guards."""
    copy_project(tmp_path, project_type="cli", include_scraping=True)
    assert (tmp_path / "CHARTER.md").exists()
    pkg_dir = tmp_path / "src" / "python_copier_template_example"
    assert (pkg_dir / "fetcher.py").exists()
    assert (tmp_path / "tests" / "test_scraping.py").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("httpx") for d in pyproject_toml["project"]["dependencies"])
    pyproject_text = (tmp_path / "pyproject.toml").read_text()
    assert "banned-api" in pyproject_text
    assert "fetcher.py" in pyproject_text
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".cache/fetcher/" in gitignore
    agents = (tmp_path / "AGENTS.md").read_text()
    assert "CHARTER.md" in agents
    assert "banned-api" in agents
    readme = (tmp_path / "README.md").read_text()
    assert "CHARTER.md" in readme


def test_template_include_scraping_runs(tmp_path: Path):
    """The generated fetcher must actually run: sync the project and execute
    its offline test plus ruff on the fetcher."""
    copy_project(tmp_path, project_type="cli", include_scraping=True)
    run = make_venv(tmp_path)
    run("uv run --locked pytest tests/test_scraping.py -q")
    run("uv run --locked ruff check src tests/test_scraping.py")


def test_template_include_scraping_not_offered_elsewhere(tmp_path: Path):
    """Forcing include_scraping outside cli must not leak the fetcher
    (scraping_effective guard)."""
    cases = [
        ("library", {}),
        ("web_api", {}),
        ("data_science", {}),
        ("script", {}),
        ("online_judge", {"oj_category": "competitive_coding", "oj_kind": "atcoder"}),
    ]
    for index, (project_type, extra) in enumerate(cases):
        project_path = tmp_path / f"case_{index}"
        copy_project(project_path, project_type=project_type, include_scraping=True, **extra)
        pyproject = tomllib.loads((project_path / "pyproject.toml").read_text())
        assert not any(d.startswith("httpx") for d in pyproject["project"]["dependencies"])
        assert not (project_path / "CHARTER.md").exists()
        assert not list(project_path.rglob("fetcher.py"))
        assert not (project_path / "tests" / "test_scraping.py").exists()


def test_template_scraping_engine_choices(tmp_path: Path):
    """Each non-default engine ships its starter + test; `all` ships all."""
    cases = {
        "scrapy": (["spider.py"], ["test_scrapy_spider.py"], "scrapy"),
        "memorious": (["crawler.py"], ["test_memorious_crawler.py"], "memorious4"),
        "playwright": (["browser_fetch.py"], ["test_browser_fetch.py"], "playwright"),
        "all": (
            ["fetcher.py", "spider.py", "crawler.py", "browser_fetch.py"],
            ["test_scraping.py", "test_scrapy_spider.py", "test_memorious_crawler.py", "test_browser_fetch.py"],
            "memorious4",
        ),
    }
    for engine, (modules, tests, dep) in cases.items():
        project_path = tmp_path / f"engine_{engine}"
        copy_project(
            project_path,
            project_type="cli",
            include_scraping=True,
            use_recommended_scraping=False,
            scraping_engine=engine,
        )
        pkg_dir = project_path / "src" / "python_copier_template_example"
        for module in modules:
            assert (pkg_dir / module).exists(), f"{engine}: missing {module}"
        for test in tests:
            assert (project_path / "tests" / test).exists(), f"{engine}: missing {test}"
        pyproject = tomllib.loads((project_path / "pyproject.toml").read_text())
        assert any(d.startswith(dep) for d in pyproject["project"]["dependencies"]), f"{engine}: missing {dep}"


def test_template_scraping_memorious_forces_agpl(tmp_path: Path):
    """memorious4 is AGPL-3.0: the generated project license must be AGPL-3.0
    even when MIT was asked."""
    copy_project(
        tmp_path,
        project_type="cli",
        include_scraping=True,
        use_recommended_scraping=False,
        scraping_engine="memorious",
        license="MIT",
    )
    pyproject = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject["project"]["license"] == "AGPL-3.0"
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in (tmp_path / "LICENSE").read_text()


def test_template_license_check_task(tmp_path: Path):
    """Recommended path ships pip-licenses + a standalone license-check task.

    The task stays out of local `type-check`/`check` (both must run
    offline): CI's lint job calls `lint,type-check,license-check` together
    instead (see ci.yml / .gitlab-ci.yml). Opting out drops the dep and
    the task.
    """
    copy_project(tmp_path, project_type="cli")
    pyproject = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("pip-licenses") for d in pyproject["dependency-groups"]["dev"])
    taskfile = (tmp_path / "Taskfile.yml").read_text()
    assert "license-check" in taskfile
    assert "pip-licenses" in taskfile
    type_check_block = taskfile.split("type-check:")[1].split("\n  ")[0]
    assert "pip-licenses" not in type_check_block
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "lint,type-check,license-check" in ci

    off_path = tmp_path / "off"
    copy_project(
        off_path,
        project_type="cli",
        use_recommended_security=False,
        security_policy=True,
        scorecard=False,
        license_check=False,
    )
    off_pyproject = tomllib.loads((off_path / "pyproject.toml").read_text())
    assert not any(d.startswith("pip-licenses") for d in off_pyproject["dependency-groups"]["dev"])
    assert "license-check" not in (off_path / "Taskfile.yml").read_text()


def test_template_data_governance_asked_on_recommended_path(tmp_path: Path):
    """DUO/CARE are asked even when the data_science gate stays recommended.

    The recommended answer only settles GPU now; data_reusable/data_ethics
    default to false but are always asked, so silence is an explicit No,
    not an unseen question.
    """
    from copier import run_copy

    from test_recommended_path import BASE

    run_copy(
        src_path=str(TOP),
        dst_path=tmp_path,
        data={**BASE, "project_type": "data_science"},
        vcs_ref="HEAD",
        defaults=True,
        unsafe=True,
        overwrite=True,
        skip_tasks=True,
    )
    assert not (tmp_path / "data" / "DUO.md").exists()
    assert not (tmp_path / "data" / "CARE.md").exists()
    # The trio is unconditional on the data layout: guardrails ship even
    # when both sheets are declined.
    assert (tmp_path / "data" / "DEIDENTIFICATION.md").exists()
    assert (tmp_path / "data" / "sharing" / "DATA_TRANSFER_AGREEMENT.md").exists()
    assert (tmp_path / "data" / "sharing" / "TRANSFER_LOG.csv").exists()


def test_template_ci_runs_license_check(tmp_path: Path):
    """CI lint calls the standalone license-check; GitLab matches."""
    copy_project(tmp_path, project_type="cli")
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "lint,type-check,license-check" in ci

    gitlab_path = tmp_path / "gitlab"
    copy_project(
        gitlab_path,
        project_type="cli",
        git_platform="gitlab.com",
        gitlab_group="mygroup",
    )
    gitlab = (gitlab_path / ".gitlab-ci.yml").read_text()
    assert "license-check" in gitlab


def test_template_gitleaks_blocks_deidentification_salt(tmp_path: Path):
    """The generated gitleaks config carries the deidentification-salt rule."""
    copy_project(tmp_path, project_type="cli")
    gitleaks = (tmp_path / ".gitleaks.toml").read_text()
    assert "deidentification-salt" in gitleaks
    assert "secret_salt" in gitleaks


def test_template_author_orcid_validator(tmp_path: Path):
    """A malformed ORCID iD is rejected at question time (validator)."""
    from test_recommended_path import BASE

    with pytest.raises(ValueError, match="not a valid ORCID"):
        run_copy(
            src_path=str(TOP),
            dst_path=tmp_path,
            data={
                **BASE,
                "project_type": "library",
                "use_recommended_license": False,
                "fair": True,
                "author_orcid": "not-an-orcid",
            },
            vcs_ref="HEAD",
            defaults=True,
            unsafe=True,
            overwrite=True,
            skip_tasks=True,
        )


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


@pytest.mark.parametrize("log_library", ["structlog", "loguru", "picologging", "logging"])
def test_template_log_library_gcp_json_fields(tmp_path: Path, log_library: str, monkeypatch: pytest.MonkeyPatch):
    """With cloud_provider=gcp, LOG_FORMAT=json should use the field names
    Cloud Logging's structured-log parser recognises (severity/message/time)
    instead of each library's own default (level/event/timestamp), so the
    generated project's logs get severity colouring/filtering for free.
    """
    copy_project(tmp_path, log_library=log_library, cloud_provider="gcp")
    run = make_venv(tmp_path)
    run("uvx --from go-task-bin task check")
    monkeypatch.setenv("LOG_FORMAT", "json")
    output = run(
        "uv run --locked python -c "
        '"from python_copier_template_example.logging_setup import logger; '
        "logger.bind(task_id='T-123').info('job_done', chunks=3)\""
    )
    payload = json.loads(output)
    assert payload["severity"] == "INFO"
    assert payload["message"] == "job_done"
    assert "time" in payload
    assert "level" not in payload
    assert "event" not in payload
    assert "timestamp" not in payload


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
    assert (
        "fair-software/howfairis-github-action@4c11146488125aa6e1531184eed51d781bcd5871 # 0.2.1"
        in fair_software_workflow.read_text()
    )
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


def test_template_data_governance_skipped_for_online_judge(tmp_path: Path):
    # online_judge projects have no data/ tree, so the DUO/CARE sheets never
    # apply -- they are a data_science-only concern.
    copy_project(
        tmp_path,
        project_type="online_judge",
        oj_category="data_science",
        oj_kind="kaggle",
        data_reusable=True,
        data_ethics=True,
    )
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
    # SECURITY.md / Scorecard are GitHub-only (private advisories + badge
    # both require github.com), so GitLab projects skip them.
    assert not (tmp_path / "SECURITY.md").exists()
    assert "SECURITY.md" not in (tmp_path / "README.md").read_text()


def test_template_security_policy_opt_out(tmp_path: Path):
    """use_recommended_security=false + security_policy=false drops SECURITY.md."""
    copy_project(tmp_path, use_recommended_security=False, security_policy=False, scorecard=False)
    assert not (tmp_path / "SECURITY.md").exists()
    assert "SECURITY.md" not in (tmp_path / "README.md").read_text()


def test_template_scorecard_opt_in(tmp_path: Path):
    """scorecard=true adds the Scorecard workflow + README badge."""
    copy_project(tmp_path, use_recommended_security=False, scorecard=True, security_policy=True)
    assert (tmp_path / "SECURITY.md").exists()
    assert (tmp_path / ".github" / "workflows" / "scorecard.yml").exists()
    readme = (tmp_path / "README.md").read_text()
    assert "api.scorecard.dev/projects/github.com/kasi-x/python-copier-template-example/badge" in readme


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


def test_template_agent_off_by_default(tmp_path: Path):
    # use_recommended_agent defaults to true: no agent scaffold on a library
    copy_project_recommended(tmp_path, project_type="library")
    assert not (tmp_path / "prompts").exists()
    assert not (tmp_path / "src" / "recommended_example" / "tools").exists()
    assert not (tmp_path / "src" / "recommended_example" / "agent.py").exists()
    assert not (tmp_path / "tests" / "test_agent.py").exists()


def test_template_agent_scaffold(tmp_path: Path):
    copy_project(tmp_path, project_type="library", use_recommended_agent=False)
    # prompt, typed tools package and the runnable agent module
    assert (tmp_path / "prompts" / "agent.md").exists()
    assert (tmp_path / "src" / "python_copier_template_example" / "tools" / "__init__.py").exists()
    assert (tmp_path / "src" / "python_copier_template_example" / "tools" / "example.py").exists()
    assert (tmp_path / "src" / "python_copier_template_example" / "agent.py").exists()
    assert (tmp_path / "tests" / "test_agent.py").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("pydantic-ai") for d in pyproject_toml["project"]["dependencies"])


def test_template_agent_cli_only(tmp_path: Path):
    # cli also offers the agent gate
    copy_project(tmp_path, project_type="cli", use_recommended_agent=False)
    assert (tmp_path / "prompts" / "agent.md").exists()
    assert (tmp_path / "src" / "python_copier_template_example" / "agent.py").exists()


def test_template_agent_not_offered_for_web_api(tmp_path: Path):
    # The agent gate only exists for library/cli; web_api never scaffolds it,
    # even when the answer is forced.
    copy_project(tmp_path, project_type="web_api", use_recommended_agent=False)
    assert not (tmp_path / "prompts").exists()
    assert not (tmp_path / "src" / "python_copier_template_example" / "agent.py").exists()


def test_template_github_org_reflected(tmp_path: Path):
    copy_project(tmp_path, github_org="myorg")
    # github_org is used in generated URLs and badges
    readme = (tmp_path / "README.md").read_text()
    assert "myorg" in readme
    assert "DiamondLightSource" not in readme


def test_template_no_docker_has_no_docs_and_works(tmp_path: Path):
    copy_project(tmp_path, docker=False)
    # The devcontainer-only Dockerfile is always shipped, but with docker off
    # it has no build/runtime stages and no container how-to in the docs.
    container_doc = tmp_path / "docs" / "how-to" / "run-container.md"
    assert not container_doc.exists()
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "AS build" not in dockerfile
    assert "AS runtime" not in dockerfile
    assert "docker run" not in (tmp_path / "README.md").read_text()


def test_bad_repo_name(tmp_path: Path):
    with pytest.raises(ValueError, match="bad:thing is not a valid repo name"):
        copy_project(tmp_path, repo_name="bad:thing")


def test_django_not_supported_aborts(tmp_path: Path):
    # Selecting the web_django project type must abort generation with a
    # pointer to the alternatives, instead of generating a project.
    with pytest.raises(Exception, match="Django is not supported"):
        copy_project(tmp_path, project_type="web_django")


@pytest.mark.parametrize("package_manager", ["uv", "pixi"])
def test_web_api_ships_env_and_compose(tmp_path: Path, package_manager: str):
    copy_project(tmp_path, project_type="web_api", docker=True, package_manager=package_manager)
    # cookiecutter-django style additions
    assert (tmp_path / ".editorconfig").exists()
    assert (tmp_path / ".env.example").exists()
    assert (tmp_path / ".dockerignore").exists()
    assert (tmp_path / "compose.local.yml").exists()
    # The compose file wires up the API + postgres
    compose = (tmp_path / "compose.local.yml").read_text()
    assert "postgres" in compose
    assert "8000:8000" in compose
    # least privilege: read-only rootfs (writable /tmp + $HOME cache tmpfs)
    # with real local-dev caps (plain `compose up` ignores `deploy`)
    assert "read_only: true" in compose
    assert "- /tmp" in compose
    assert ".cache" in compose
    assert "mem_limit: 512M" in compose
    assert "deploy:" not in compose
    # the runtime image runs as a non-root user owning its workdir
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "USER appuser" in dockerfile
    assert "chown appuser" in dockerfile
    assert "PYTHONDONTWRITEBYTECODE" in dockerfile
    # USER comes after the runtime COPY/WORKDIR it locks down
    assert dockerfile.index("COPY --from=build") < dockerfile.index("USER appuser")
    # .env is git-ignored
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".env" in gitignore


def test_web_api_recommended_fastapi_stack(tmp_path: Path):
    """The recommended web_api path ships a working FastAPI scaffold.

    example-answers.yml sets use_recommended_web_api=false, so the detailed
    questions (prometheus / rate_limit / cors) all default to true — this is
    the full-stack render.
    """
    copy_project(tmp_path, project_type="web_api", docker=True)
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    for expected in ("fastapi", "uvicorn", "sqlalchemy", "alembic", "asyncpg", "asgi-correlation-id"):
        assert any(expected in d for d in deps), f"{expected} missing from {deps}"
    # optional observability / protection deps (all default on)
    assert any("prometheus-client" in d for d in deps)
    assert any("slowapi" in d for d in deps)

    pkg = tmp_path / "app"
    # app factory + settings + db + demo model/schemas/router live in the
    # top-level app/ package (web_api has no <pkg> library).
    for rel in (
        "main.py",
        "settings.py",
        "db.py",
        "models.py",
        "schemas.py",
        "router.py",
        "routers/health.py",
        "routers/items.py",
    ):
        assert (pkg / rel).exists(), f"{rel} not generated"
    main = (pkg / "main.py").read_text()
    assert "create_app" in main
    assert "CorrelationIdMiddleware" in main
    assert "app = create_app()" in main
    # uvicorn entrypoint + healthcheck in the Dockerfile
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "uvicorn" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    # alembic pre-wired at the repo root
    assert (tmp_path / "alembic" / "env.py").exists()
    assert (tmp_path / "alembic" / "alembic.ini").exists()
    # generated HTTP tests exercise the endpoints
    test_app = (tmp_path / "tests" / "test_app.py").read_text()
    assert "ASGITransport" in test_app
    assert "/health" in test_app


def test_web_api_detail_options_off(tmp_path: Path):
    """use_recommended_web_api=false + all three switches off: minimal stack.

    FastAPI itself stays (it is the recommended base), but no /metrics,
    no slowapi, no CORS middleware, and the conditional modules are absent.
    """
    copy_project(
        tmp_path,
        project_type="web_api",
        docker=True,
        use_recommended_web_api=False,
        prometheus=False,
        rate_limit=False,
        cors=False,
    )
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert any("fastapi" in d for d in deps)
    assert not any("prometheus" in d for d in deps)
    assert not any("slowapi" in d for d in deps)

    pkg = tmp_path / "app"
    assert (pkg / "main.py").exists()
    main = (pkg / "main.py").read_text()
    assert "metrics" not in main
    assert "slowapi" not in main
    assert "CORS" not in main
    # conditional modules are not generated
    assert not (pkg / "metrics.py").exists()
    assert not (pkg / "rate_limit.py").exists()


def test_web_api_not_offered_to_other_types(tmp_path: Path):
    """FastAPI deps and app/ code must not leak into other project types.

    Force the detail answers on a library without the combo opt-in — the
    *_effective variables must keep them out.
    """
    copy_project(
        tmp_path,
        project_type="library",
        docker=True,
        use_recommended_web_api=False,
        prometheus=True,
        rate_limit=True,
        cors=True,
    )
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert not any("fastapi" in d for d in deps)
    assert not any("slowapi" in d for d in deps)
    assert not any("prometheus" in d for d in deps)
    assert not (tmp_path / "src" / "python_copier_template_example" / "app").exists()
    assert not (tmp_path / "alembic").exists()
    assert not (tmp_path / "tests" / "test_app.py").exists()


def test_combo_data_science_with_web_api(tmp_path: Path):
    """The include_web_api opt-in adds the FastAPI scaffold on top of a
    data_science base: app/ + alembic + FastAPI deps coexist with the
    analysis layout (notebooks/, data/, ...)."""
    copy_project(
        tmp_path,
        project_type="data_science",
        include_web_api=True,
    )
    assert (tmp_path / "app" / "main.py").exists()
    assert (tmp_path / "alembic").exists()
    assert (tmp_path / "notebooks").exists()
    assert (tmp_path / "data" / "DEIDENTIFICATION.md").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert any("fastapi" in d for d in deps)
    assert any("polars" in d for d in deps)
    assert (tmp_path / "tests" / "test_app.py").exists()


def test_combo_guards_reject_incompatible_bases(tmp_path: Path):
    """Forcing a combo opt-in on a non-combinable base (ros2 / script / ...)
    must not leak the layered artifacts: the combinable guard keeps them out."""
    copy_project(tmp_path, project_type="script", include_web_api=True)
    assert not (tmp_path / "app").exists()
    assert not (tmp_path / "alembic").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert not any("fastapi" in d for d in pyproject_toml["project"]["dependencies"])


def test_template_web_api_runs_in_process(tmp_path: Path):
    """The generated FastAPI scaffold must actually work: sync the project,
    run the HTTP tests (SQLite fallback), and keep it ruff/basedpyright-clean
    — the same gates the generated project's own CI applies."""
    copy_project(tmp_path, project_type="web_api", docker=True)
    run = make_venv(tmp_path)
    run("uv run --locked pytest -q")
    run("uv run --locked ruff check .")
    run("uv run --locked basedpyright")


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
    # Docs and dev tooling all coexist with the ament layout; the ASCII
    # banner was removed template-wide, so no banner tooling is generated.
    assert (tmp_path / "docs").exists()
    assert not (tmp_path / "tools" / "ascii_banner.py").exists()
    assert not (tmp_path / "NOTICE").exists()
    # The ros2 package __init__ exports __version__ (docs import it)
    init = (tmp_path / "recommended_example" / "__init__.py").read_text()
    assert "__version__" in init
    # devcontainer is ROS-aware and rendered (no raw jinja)
    devcontainer = (tmp_path / ".devcontainer" / "devcontainer.json").read_text()
    assert "Dockerfile.ros2" in devcontainer
    assert "{%" not in devcontainer


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
    assert "Install MicroPython stubs" in (tmp_path / ".github" / "workflows" / "_tasks.yml").read_text()
    # the freeze build ships a manifest and a docker-based build script
    manifest = (tmp_path / "firmware" / "manifest.py").read_text()
    assert 'freeze(".")' in manifest
    assert "micropython/build-micropython-arm:bookworm" in freeze
    assert "espressif/idf" in freeze
    assert "freeze" in (tmp_path / "justfile").read_text()


def test_template_micropython_rp2_stub(tmp_path: Path):
    copy_project_recommended(tmp_path, project_type="micropython", micropython_port="rp2")
    reqs = (tmp_path / "requirements-dev.txt").read_text()
    assert "micropython-rp2-stubs~=" in reqs
    assert "micropython-esp32-stubs" not in reqs


def test_template_micropython_core_test_runs(tmp_path: Path):
    """The device-independent core must be importable and testable under CPython."""
    copy_project_recommended(tmp_path, project_type="micropython", micropython_port="unix")
    run = make_venv(tmp_path)
    run("uv run pytest -q")


def test_dots_in_package_name(tmp_path: Path):
    copy_project(tmp_path, repo_name="dots.in.name")


def test_example_repo_updates(tmp_path: Path):
    generated_path = tmp_path / "generated"
    example_url = "https://github.com/kasi-x/python-copier-template-example.git"
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
    # template/.gitignore.jinja is conditional (data_science / kaggle /
    # ros2 blocks render per project type); the root .gitignore is the
    # union of every conditional branch, so the template repo itself
    # ignores everything any generated project could produce.
    # Compare normalized line sets (jinja tags stripped) in both
    # directions: exact parity catches stale root-only lines (e.g. a
    # removed input//exp/) and missing template lines, which a one-way
    # substring check would hide. template/.gitignore.jinja shares its
    # CTF / scraping bodies via {% include %} (_shared/gitignore-*.jinja),
    # so those are inlined before normalizing.
    def normalized(path: Path) -> set[str]:
        lines = set()
        text = path.read_text()
        for included in re.findall(r'{%\s*include\s*"([^"]+)"\s*%}', text):
            text += "\n" + (TOP / included).read_text()
        for line in text.splitlines():
            stripped = re.sub(r"{%.*?%}|{#.*?#}", "", line).strip()
            if not stripped or stripped.startswith("#"):
                continue
            lines.add(stripped)
        return lines

    template = normalized(TOP / "template" / ".gitignore.jinja")
    root = normalized(TOP / ".gitignore")
    assert template - root == set(), f"missing from root .gitignore: {sorted(template - root)}"
    assert root - template == set(), f"stale in root .gitignore: {sorted(root - template)}"
    assert ".gitignore.jinja" not in (TOP / ".gitignore").read_text()


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


def test_audit_isolated_from_type_check(tmp_path: Path):
    # pip-audit is network-dependent (OSV/PyPI): on-demand `audit` task,
    # never inside type-check/check so offline CI stays green.
    copy_project(tmp_path)
    taskfile = (tmp_path / "Taskfile.yml").read_text()
    assert "pip-audit" in taskfile
    type_check_block = taskfile.split("type-check", 1)[1].split("audit", 1)[0]
    assert "pip-audit" not in type_check_block


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
    # Find the GitHub actions ignored by renovate (all github-actions
    # packageRules now that they are split per category, not one block)
    renovate_config_path = tmp_path / "renovate.json"
    renovate_config = json.loads(renovate_config_path.read_text())
    config_github_actions = set()
    for rule in renovate_config["packageRules"]:
        if rule.get("matchManagers") == ["github-actions"]:
            config_github_actions.update(rule.get("matchPackageNames", []))
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
