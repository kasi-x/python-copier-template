"""data_science and the kaggle competition path: the analysis layout, the ML
dependency/deptry contract, and the DUO/CARE + deidentification governance
sheets."""

import tomllib
from pathlib import Path

from render_cache import RenderCache
from render_cache import render_cache as render_cache  # noqa: PLC0414  # the session fixture, made visible here
from support import copy_project


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
    # Bug #15 regression: a data_science GPU render (use_gpu_effective, not just
    # kaggle) must ship the cu126 torch index, so a user adding torch gets the
    # CUDA wheel instead of PyPI's CPU default under a GPU Dockerfile.
    if package_manager := pyproject_toml.get("tool", {}).get("uv", {}):
        index_urls = {i.get("url") for i in package_manager.get("index", [])}
        assert any("download.pytorch.org/whl/cu126" in u for u in index_urls), (
            "a data_science GPU render must declare the pytorch-cu126 index (bug #15)"
        )
    # Bug #17 regression: web_api-only names must NOT leak into data_science deptry ignores.
    ignores = pyproject_toml["tool"]["deptry"]["per_rule_ignores"]
    for web_api_name in ("alembic", "asgi-correlation-id", "asyncpg", "fastapi", "slowapi", "sqlalchemy", "uvicorn"):
        assert web_api_name not in ignores, (
            f"deptry DEP002 leaks {web_api_name} into a pure data_science render (bug #17)"
        )


def test_template_online_judge_no_solutions_for_kaggle(tmp_path: Path):
    # kaggle is a result competition: no solutions/ scripts tree either
    copy_project(tmp_path, project_type="online_judge", oj_category="data_science", oj_kind="kaggle")
    assert not (tmp_path / "solutions").exists()


# The render inputs of test_template_data_governance_asked_on_recommended_path,
# composed with tools/answers.py BASE at the call site: registered in
# tests/test_answer_fixtures.py like every other answer fixture.
DATA_GOV_ANSWERS: dict[str, object] = {"project_type": "data_science"}


def test_template_data_governance_asked_on_recommended_path(tmp_path: Path, render_cache: RenderCache):
    """DUO/CARE are asked even when the data_science gate stays recommended.

    The recommended answer only settles GPU now; data_reusable/data_ethics
    default to false but are always asked, so silence is an explicit No,
    not an unseen question.
    """

    from tools.answers import BASE

    render_cache.render(tmp_path, {**BASE, **DATA_GOV_ANSWERS})
    assert not (tmp_path / "data" / "DUO.md").exists()
    assert not (tmp_path / "data" / "CARE.md").exists()
    # The trio is unconditional on the data layout: guardrails ship even
    # when both sheets are declined.
    assert (tmp_path / "data" / "DEIDENTIFICATION.md").exists()
    assert (tmp_path / "data" / "sharing" / "DATA_TRANSFER_AGREEMENT.md").exists()
    assert (tmp_path / "data" / "sharing" / "TRANSFER_LOG.csv").exists()


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
