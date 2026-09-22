"""online_judge: the bare judge workspaces (atcoder / leetcode / yukicoder /
aoj / codeforces / kattis / other / ctf) and the AGENTS.md wording rules that follow oj_allow_ai."""

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


def test_template_codeforces_workspace(tmp_path: Path):
    # Codeforces is a code-submission judge: the same bare workspace as
    # atcoder, driven with oj (download / test work; submit via oj or browser)
    copy_project(tmp_path, project_type="online_judge", oj_category="competitive_coding", oj_kind="codeforces")
    assert not (tmp_path / "src").exists()
    assert not (tmp_path / "tests" / "test_samples.py").exists()
    assert not list(tmp_path.glob("*.py"))
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["dependencies"] == []
    readme = (tmp_path / "README.md").read_text()
    assert "oj download https://codeforces.com/contest/4/problem/A" in readme
    assert "oj test" in readme
    guide = (tmp_path / "AGENTS.md").read_text()
    assert "codeforces" in guide
    assert "test/" in (tmp_path / ".gitignore").read_text()


def test_template_kattis_workspace(tmp_path: Path):
    # Kattis is a code-submission judge: the same bare workspace, but the
    # README leads with submit.py + .kattisrc and oj only downloads samples
    copy_project(tmp_path, project_type="online_judge", oj_category="competitive_coding", oj_kind="kattis")
    assert not (tmp_path / "src").exists()
    assert not list(tmp_path.glob("*.py"))
    readme = (tmp_path / "README.md").read_text()
    assert "python3 submit.py hello.py" in readme
    assert "oj download https://open.kattis.com/problems/hello" in readme
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".kattisrc" in gitignore
    assert "test/" in gitignore


def test_template_other_workspace(tmp_path: Path):
    # other is the generic stdin/stdout judge: a bare workspace with no
    # site-specific tooling beyond oj download/test where allowed
    copy_project(tmp_path, project_type="online_judge", oj_category="competitive_coding", oj_kind="other")
    assert not (tmp_path / "src").exists()
    readme = (tmp_path / "README.md").read_text()
    assert "oj download <problem-url>" in readme
    guide = (tmp_path / "AGENTS.md").read_text()
    assert "other" in guide


def test_template_oj_sample_workflow_per_site(tmp_path: Path):
    # oj_sample is opt-in (default off): off renders no file, on renders a
    # per-site oj-sample.yml that parses as YAML and pins that site's tool.
    # Off must stay byte-identical for existing renders, so assert absence too.
    off = tmp_path / "off"
    copy_project(off, project_type="online_judge", oj_category="competitive_coding", oj_kind="codeforces")
    assert not (off / ".github" / "workflows" / "oj-sample.yml").exists()
    pins = {
        "atcoder": "https://atcoder.jp/contests/abc086/tasks/abc086_a",
        "codeforces": "https://codeforces.com/contest/4/problem/A",
        "yukicoder": "https://yukicoder.me/problems/no/1234",
        "aoj": "aoj init",
        "kattis": "submit.py",
        "leetcode": "Solution",
        "other": "judge.yosupo.jp",
    }
    for oj_kind, pin in pins.items():
        project_path = tmp_path / f"sample_{oj_kind}"
        copy_project(
            project_path,
            project_type="online_judge",
            oj_category="competitive_coding",
            oj_kind=oj_kind,
            oj_sample=True,
        )
        body = (project_path / ".github" / "workflows" / "oj-sample.yml").read_text()
        assert pin in body, f"{oj_kind}: oj-sample.yml lacks its pinned marker {pin!r}"
        parsed = yaml.safe_load(body)
        assert "sample" in parsed["jobs"], f"{oj_kind}: oj-sample.yml has no sample job"


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


def test_template_agents_md_wording_follows_oj_allow_ai(tmp_path: Path):
    """Every judge ships AGENTS.md since 2026-09-21; oj_allow_ai picks the
    AI wording and the AI-NG judges get the check-the-rules sentence."""
    cases = [
        ("atcoder", {"oj_allow_ai": True}, "The judge's rules permit AI assistance"),
        ("atcoder", {}, "Contest rules govern AI use"),
        ("atcoder", {"oj_allow_ai": False}, "Contest rules govern AI use"),
        ("leetcode", {}, "Contest rules govern AI use"),
        ("yukicoder", {}, "Contest rules govern AI use"),
        ("aoj", {}, "Contest rules govern AI use"),
        ("codeforces", {"oj_allow_ai": True}, "The judge's rules permit AI assistance"),
        ("codeforces", {}, "Contest rules govern AI use"),
        ("kattis", {"oj_allow_ai": True}, "The judge's rules permit AI assistance"),
        ("kattis", {}, "Contest rules govern AI use"),
        ("other", {"oj_allow_ai": True}, "The judge's rules permit AI assistance"),
        ("other", {}, "Contest rules govern AI use"),
    ]
    for index, (oj_kind, extra, expected) in enumerate(cases):
        project_path = tmp_path / f"case_{index}"
        copy_project(
            project_path, project_type="online_judge", oj_category="competitive_coding", oj_kind=oj_kind, **extra
        )
        guide = (project_path / "AGENTS.md").read_text()
        assert expected in guide, f"{oj_kind} {extra}: AGENTS.md lacks the {expected!r} wording"
        assert "ライセンス変動" in guide, "the ethics appendix ships with the guide"
        readme = (project_path / "README.md").read_text()
        assert "AGENTS.md" in readme


def test_template_agents_md_ships_for_ros2_and_micropython(tmp_path: Path):
    """ros2 / micropython ship the agent guide since 2026-09-21; micropython
    is the registry's `iot` audience for PKI-chain, ros2 is not."""
    ros2_path = tmp_path / "ros2"
    copy_project(ros2_path, project_type="ros2", pkg_language="python", ros_distro="humble", ros2_package_manager="apt")
    ros2_guide = (ros2_path / "AGENTS.md").read_text()
    assert "PKIチェーン" not in ros2_guide
    assert "ライセンス変動" in ros2_guide
    micro_path = tmp_path / "micro"
    copy_project(micro_path, project_type="micropython", micropython_port="esp32")
    micro_guide = (micro_path / "AGENTS.md").read_text()
    assert "PKIチェーン" in micro_guide
