"""online_judge: the bare judge workspaces (atcoder / leetcode / yukicoder /
aoj / ctf) and the AGENTS.md presence rules that follow oj_allow_ai."""

import tomllib
from pathlib import Path

import pytest
import yaml

from support import copy_project
from support import copy_project_recommended
from support import make_venv


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
    ci = yaml.safe_load((tmp_path / ".github" / "workflows" / "ci.yml").read_text())
    assert "dist" not in ci["jobs"], "a submission repo needs no dist/pypi job"
    # ruff is relaxed for contest code (project-wide, not per solutions/)
    lint = pyproject_toml["tool"]["ruff"]["lint"]
    assert "A001" in lint["extend-ignore"], "builtin shadowing is relaxed"
    assert not any("solutions" in key for key in lint.get("per-file-ignores", {})), "the relaxation is project-wide"
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
    ci = yaml.safe_load((tmp_path / ".github" / "workflows" / "ci.yml").read_text())
    assert "dist" not in ci["jobs"], "a submission repo needs no dist/pypi job"
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
    ci = yaml.safe_load((tmp_path / ".github" / "workflows" / "ci.yml").read_text())
    assert "dist" not in ci["jobs"], "a submission repo needs no dist/pypi job"
    # README leads with aoj-cli (init / test / submit) for AOJ
    readme = (tmp_path / "README.md").read_text()
    assert "aoj init ITP1_1_A" in readme
    assert "aoj submit main.py --lang Python3" in readme


@pytest.mark.heavy
@pytest.mark.network
def test_template_online_judge_repo_lints_clean(tmp_path: Path):
    """The empty workspace renders a ruff/type-check-clean repo (no sources)."""
    copy_project_recommended(tmp_path, project_type="online_judge", oj_category="competitive_coding", oj_kind="atcoder")
    run = make_venv(tmp_path)
    run("uvx --from rust-just just check")


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
