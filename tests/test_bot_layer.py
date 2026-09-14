"""The bot layer's render contract and its real-execution proof.

tests/test_example.py owns the per-feature render assertions for the layers
that predate the witness ledger; this module is the bot layer's own file
(TODO.md §4). The fast tests pin the wiring on each base (scaffold iff
``bot_discord_effective``, the dependency / entry point / env-var gates, the
leak check on the types that must never be offered the layer); the heavy test
renders a cli project with the layer, installs it, and exercises
``build_bot()``'s ``/ping`` callback in-process through the generated test
suite — a fake interaction, no Gateway connection, no token.
"""

import os
import shlex
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml
from copier import run_copy

from support import make_venv
from support import run_pipe

TOP = Path(__file__).absolute().parent.parent

BASE_ANSWERS: dict[str, object] = {
    "package_name": "bot_example",
    "description": "An example project",
    "git_platform": "github.com",
    "github_org": "kasi-x",
    "author_name": "kasi-x",
    "author_email": "kashiimiya.exe@gmail.com",
    "repo_name": "bot-example",
    "distribution_name": "bot-example",
}


def copy_project(project_path: Path, **kwargs: object) -> None:
    """Render once into `project_path` (no venv — the fast tier's recipe)."""
    answers = {**BASE_ANSWERS, **kwargs}
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


def pyproject_deps(project_path: Path) -> dict:
    return tomllib.loads((project_path / "pyproject.toml").read_text())


def scripts_of(project_path: Path) -> dict:
    """The render's [project.scripts] (absent entirely on a web_api base)."""
    return pyproject_deps(project_path).get("project", {}).get("scripts", {})


def test_bot_scaffold_on_cli(tmp_path: Path):
    """cli + include_bot: the module rides the src-layout package with its
    own console script, its in-process test, the dependency and the env var."""
    copy_project(tmp_path, project_type="cli", include_bot=True)
    pkg = tmp_path / "src" / "bot_example"
    bot_module = (pkg / "bot_discord.py").read_text()
    assert (pkg / "bot_discord.py").is_file()
    assert (tmp_path / "tests" / "test_bot_discord.py").is_file()
    pyproject = pyproject_deps(tmp_path)
    assert "discord.py>=2,<3" in pyproject["project"]["dependencies"]
    assert scripts_of(tmp_path)["bot-discord-bot-example"] == "bot_example.bot_discord:main"
    assert "anyio" in pyproject["dependency-groups"]["dev"]
    # startup env check, build_bot()/main() split, logging through the
    # generated logging_setup
    assert "DISCORD_BOT_TOKEN" in bot_module
    assert "def build_bot(" in bot_module
    assert "from bot_example.logging_setup import logger" in bot_module
    # .env.example documents the token variable
    assert "DISCORD_BOT_TOKEN=" in (tmp_path / ".env.example").read_text()
    # the README advertises the layer (the MCP section's style)
    assert "bot-discord-bot-example" in (tmp_path / "README.md").read_text()
    # the CLI contract is untouched: the console script stays the package's
    assert scripts_of(tmp_path)["bot-example"] == "bot_example.__main__:main"


def test_bot_scaffold_on_web_api(tmp_path: Path):
    """A web_api base hosts the bot in the top-level app/ package — no
    <pkg>-side duplicate, and the entry point points at the app import root."""
    copy_project(tmp_path, project_type="web_api", include_bot=True)
    pyproject = pyproject_deps(tmp_path)
    assert "discord.py>=2,<3" in pyproject["project"]["dependencies"]
    assert (tmp_path / "app" / "bot_discord.py").is_file()
    assert not list(tmp_path.rglob("src/*/bot_discord.py"))
    assert scripts_of(tmp_path)["bot-discord-bot-example"] == "app.bot_discord:main"
    assert "from app import bot_discord" in (tmp_path / "tests" / "test_bot_discord.py").read_text()
    # no console script for the web_api CLI (there is no <pkg> CLI at all)
    assert "bot-example" not in scripts_of(tmp_path)


def test_bot_flat_layout(tmp_path: Path):
    """The flat-layout package variant also ships the module and its script."""
    copy_project(tmp_path, project_type="cli", layout="flat", include_bot=True)
    pyproject = pyproject_deps(tmp_path)
    assert "discord.py>=2,<3" in pyproject["project"]["dependencies"]
    assert (tmp_path / "bot_example" / "bot_discord.py").is_file()
    assert (tmp_path / "tests" / "test_bot_discord.py").is_file()
    assert not (tmp_path / "src").exists()


def test_bot_gate_recommendation_is_discord(tmp_path: Path):
    """use_recommended_bot keeps discord (the only offered platform); the
    custom path answers bot_platform explicitly and renders the same thing."""
    copy_project(tmp_path, project_type="cli", include_bot=True, use_recommended_bot=False, bot_platform="discord")
    assert (tmp_path / "src" / "bot_example" / "bot_discord.py").is_file()
    assert "discord.py>=2,<3" in pyproject_deps(tmp_path)["project"]["dependencies"]


def test_bot_absent_by_default(tmp_path: Path):
    """Without the layer: no module, no test, no dependency, no env gate."""
    copy_project(tmp_path, project_type="cli")
    assert not (tmp_path / "src" / "bot_example" / "bot_discord.py").exists()
    assert not (tmp_path / "tests" / "test_bot_discord.py").exists()
    assert not any(d.startswith("discord") for d in pyproject_deps(tmp_path)["project"]["dependencies"])
    assert "bot-discord-bot-example" not in scripts_of(tmp_path)
    assert not (tmp_path / ".env.example").exists()


@pytest.mark.parametrize(
    ("project_type", "extra"),
    [
        ("library", {}),
        ("data_science", {}),
        ("script", {}),
        ("online_judge", {"oj_category": "competitive_coding", "oj_kind": "atcoder"}),
        ("online_judge", {"oj_category": "data_science", "oj_kind": "kaggle"}),
        ("ros2", {"pkg_language": "python"}),
        ("micropython", {}),
    ],
)
def test_bot_not_offered_to_other_types(tmp_path: Path, project_type: str, extra: dict):
    """Forcing include_bot on the types that must not be offered the layer
    must not leak the module, the dependency or the entry point anywhere."""
    project_path = tmp_path / project_type
    copy_project(project_path, project_type=project_type, include_bot=True, **extra)
    assert not list(project_path.rglob("bot_discord.py"))
    assert not (project_path / "tests" / "test_bot_discord.py").exists()
    deps = pyproject_deps(project_path)["project"]["dependencies"]
    assert not any(d.startswith("discord") for d in deps)
    assert "bot-discord-bot-example" not in scripts_of(project_path)
    # no bot-shaped directory is left empty by a half-applied layer (the
    # render's own empty dirs — .git internals, an unpopulated docs/ tree —
    # are pre-existing behaviour, not the layer's)
    layer_dirs = [project_path / "src", project_path / "tests", project_path / "app", *project_path.rglob("src/*")]
    empty = [d for d in layer_dirs if d.is_dir() and not any(d.iterdir())]
    assert not empty


def test_bot_docker_task(tmp_path: Path):
    """docker + the layer ships the bot-serve task (the mcp-serve twin) and
    the Dockerfile documents the token-driven run."""
    copy_project(tmp_path, project_type="cli", include_bot=True, docker=True)
    taskfile = (tmp_path / "justfile").read_text()
    assert "bot-serve:" in taskfile
    assert "bot-discord-bot-example" in taskfile
    assert "DISCORD_BOT_TOKEN" in taskfile
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "bot-discord-bot-example" in dockerfile
    assert "DISCORD_BOT_TOKEN" in dockerfile


def test_bot_no_docker_no_task(tmp_path: Path):
    """Without docker, no bot-serve task is generated."""
    copy_project(tmp_path, project_type="cli", include_bot=True, docker=False)
    assert "bot-serve" not in (tmp_path / "justfile").read_text()


def test_bot_and_mcp_entry_points_do_not_collide(tmp_path: Path):
    """The two long-running layers stack: distinct modules, distinct scripts,
    both dependencies declared, one .env.example carrying both variables."""
    copy_project(tmp_path, project_type="cli", include_bot=True, include_mcp=True)
    scripts = scripts_of(tmp_path)
    assert scripts["bot-discord-bot-example"] == "bot_example.bot_discord:main"
    assert scripts["mcp-server-bot-example"] == "bot_example.mcp_server:main"
    deps = pyproject_deps(tmp_path)["project"]["dependencies"]
    assert "discord.py>=2,<3" in deps
    assert any(d.startswith("mcp") for d in deps)
    env_example = (tmp_path / ".env.example").read_text()
    assert "DISCORD_BOT_TOKEN=" in env_example
    assert "MCP_ALLOWED_HOSTS=" in env_example


def test_bot_questionnaire_records_the_answers(tmp_path: Path):
    """copier records the layer's answers so `copier update` replays them."""
    copy_project(tmp_path, project_type="cli", include_bot=True)
    recorded = yaml.safe_load((tmp_path / ".copier-answers.yml").read_text())
    assert recorded["include_bot"] is True


@pytest.mark.heavy
@pytest.mark.network
def test_bot_runs_in_process(tmp_path: Path):
    """The scaffold must actually work: sync the project, run its own pytest
    (tests/test_bot_discord.py drives build_bot()'s /ping callback with a
    fake interaction — ping in, pong out, no Gateway), type-check and lint
    the bot module with no exclusions."""
    copy_project(tmp_path, project_type="cli", include_bot=True)
    run = make_venv(tmp_path)
    run("uv run --locked pytest -q")
    run("uv run --locked basedpyright src tests")
    run("uv run --locked ruff check src tests")
    _refusal_output(tmp_path, tmp_path / ".venv")


def _refusal_output(project_path: Path, venv: Path) -> str:
    """`python -m <pkg>.bot_discord` without a token: the startup env check
    refuses (exit code 2, naming the variable) instead of half-starting."""
    proc = subprocess.run(
        shlex.split("uv run --locked python -m bot_example.bot_discord"),
        cwd=str(project_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=dict(os.environ, UV_PROJECT_ENVIRONMENT="", VIRTUAL_ENV=str(venv)),
        check=False,
    )
    output = proc.stdout.decode()
    assert proc.returncode == 2, output
    assert "DISCORD_BOT_TOKEN" in output
    return output
