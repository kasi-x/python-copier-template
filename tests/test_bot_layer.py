"""The bot layer's render contract and its real-execution proof.

tests/test_example_layers.py owns the per-feature render assertions for the
layers that predate the witness ledger; this module is the bot layer's own file
(TODO.md §4). The fast tests pin the wiring on each base (scaffold iff
``bot_discord_effective`` / ``bot_slack_effective``, the dependency / entry
point / env-var gates, the leak check on the types that must never be offered
the layer); the heavy tests render a cli project per platform, install it, and
exercise the generated in-process test suite — a fake interaction driving
``build_bot()``'s ``/ping`` callback (discord) or a fake ``say`` driving the
``/app_mention`` listener (slack), with no connection and no token either way.
"""

import os
import shlex
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from support import copy_project_recommended
from support import make_venv

# The package this file renders under: the shared "Project Details"
# (tools/answers.py BASE) plus this name, with copier's own defaults driving
# everything else, so the use_recommended_* gates are exercised rather than
# pinned (support.copy_project_recommended's docstring).
BOT_PACKAGE = "bot_example"

# The second generated platform's answers: No to the recommended platform,
# then `slack`. Spread into the renders that exercise it, and registered in
# tests/test_answer_fixtures.py's drift guard like every other fixture here.
SLACK_ANSWERS: dict[str, Any] = {"use_recommended_bot": False, "bot_platform": "slack"}


def copy_project(project_path: Path, **kwargs: object) -> None:
    """Render the bot fixture into `project_path` (no venv — the fast recipe)."""
    copy_project_recommended(project_path, package_name=BOT_PACKAGE, **kwargs)


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


def test_bot_slack_scaffold_on_cli(tmp_path: Path):
    """No + bot_platform=slack on a cli base: the slack module rides the
    src-layout package with its own console script, its in-process test, the
    slack-bolt dependency and both token variables — and no discord part."""
    copy_project(tmp_path, project_type="cli", include_bot=True, **SLACK_ANSWERS)
    pkg = tmp_path / "src" / "bot_example"
    assert (pkg / "bot_slack.py").is_file()
    assert (tmp_path / "tests" / "test_bot_slack.py").is_file()
    pyproject = pyproject_deps(tmp_path)
    assert "slack-bolt>=1.21,<2" in pyproject["project"]["dependencies"]
    assert scripts_of(tmp_path)["bot-slack-bot-example"] == "bot_example.bot_slack:main"
    bot_module = (pkg / "bot_slack.py").read_text()
    # startup env check for both tokens, build_app()/register_listeners()
    # split, logging through the generated logging_setup
    assert "SLACK_BOT_TOKEN" in bot_module
    assert "SLACK_APP_TOKEN" in bot_module
    assert "def build_app(" in bot_module
    assert "from bot_example.logging_setup import logger" in bot_module
    # .env.example documents both token variables
    env_example = (tmp_path / ".env.example").read_text()
    assert "SLACK_BOT_TOKEN=" in env_example
    assert "SLACK_APP_TOKEN=" in env_example
    # the README advertises the platform that was selected
    assert "bot-slack-bot-example" in (tmp_path / "README.md").read_text()
    # one platform per render: nothing from the recommended one is generated
    assert not (pkg / "bot_discord.py").exists()
    assert not (tmp_path / "tests" / "test_bot_discord.py").exists()
    assert not any(d.startswith("discord") for d in pyproject["project"]["dependencies"])
    assert "bot-discord-bot-example" not in scripts_of(tmp_path)
    # the CLI contract is untouched: the console script stays the package's
    assert scripts_of(tmp_path)["bot-example"] == "bot_example.__main__:main"


def test_bot_slack_scaffold_on_web_api(tmp_path: Path):
    """A web_api base hosts the slack module in the top-level app/ package —
    no <pkg>-side duplicate, and the entry point points at the app import root."""
    copy_project(tmp_path, project_type="web_api", include_bot=True, **SLACK_ANSWERS)
    pyproject = pyproject_deps(tmp_path)
    assert "slack-bolt>=1.21,<2" in pyproject["project"]["dependencies"]
    assert (tmp_path / "app" / "bot_slack.py").is_file()
    assert not list(tmp_path.rglob("src/*/bot_slack.py"))
    assert scripts_of(tmp_path)["bot-slack-bot-example"] == "app.bot_slack:main"
    assert "from app import bot_slack" in (tmp_path / "tests" / "test_bot_slack.py").read_text()
    # no console script for the web_api CLI (there is no <pkg> CLI at all)
    assert "bot-example" not in scripts_of(tmp_path)


def test_bot_slack_flat_layout(tmp_path: Path):
    """The flat-layout package variant also ships the slack module and its script."""
    copy_project(tmp_path, project_type="cli", layout="flat", include_bot=True, **SLACK_ANSWERS)
    pyproject = pyproject_deps(tmp_path)
    assert "slack-bolt>=1.21,<2" in pyproject["project"]["dependencies"]
    assert (tmp_path / "bot_example" / "bot_slack.py").is_file()
    assert (tmp_path / "tests" / "test_bot_slack.py").is_file()
    assert not (tmp_path / "src").exists()


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
    """use_recommended_bot keeps discord (the recommended platform); the
    custom path answering discord explicitly renders the same thing, and
    never the slack module, its dependency or its console script."""
    copy_project(tmp_path, project_type="cli", include_bot=True, use_recommended_bot=False, bot_platform="discord")
    assert (tmp_path / "src" / "bot_example" / "bot_discord.py").is_file()
    pyproject = pyproject_deps(tmp_path)
    assert "discord.py>=2,<3" in pyproject["project"]["dependencies"]
    assert not (tmp_path / "src" / "bot_example" / "bot_slack.py").exists()
    assert not any(d.startswith("slack") for d in pyproject["project"]["dependencies"])
    assert "bot-slack-bot-example" not in scripts_of(tmp_path)
    assert "SLACK_BOT_TOKEN" not in (tmp_path / ".env.example").read_text()


def test_bot_absent_by_default(tmp_path: Path):
    """Without the layer: no module, no test, no dependency, no env gate."""
    copy_project(tmp_path, project_type="cli")
    assert not (tmp_path / "src" / "bot_example" / "bot_discord.py").exists()
    assert not (tmp_path / "src" / "bot_example" / "bot_slack.py").exists()
    assert not (tmp_path / "tests" / "test_bot_discord.py").exists()
    assert not (tmp_path / "tests" / "test_bot_slack.py").exists()
    deps = pyproject_deps(tmp_path)["project"]["dependencies"]
    assert not any(d.startswith(("discord", "slack")) for d in deps)
    assert "bot-discord-bot-example" not in scripts_of(tmp_path)
    assert "bot-slack-bot-example" not in scripts_of(tmp_path)
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
    """Forcing the layer on the types that must not be offered it must not
    leak a module, a dependency or an entry point anywhere.

    The custom slack platform is forced alongside include_bot on purpose: what
    keeps the layer out of these bases is ``bot_effective``'s base guard, not
    the platform selection, so the sharpest fixture is the one that would leak
    if the guard were wired to a platform condition instead.
    """
    project_path = tmp_path / project_type
    copy_project(project_path, project_type=project_type, include_bot=True, **SLACK_ANSWERS, **extra)
    assert not list(project_path.rglob("bot_discord.py"))
    assert not list(project_path.rglob("bot_slack.py"))
    assert not (project_path / "tests" / "test_bot_discord.py").exists()
    assert not (project_path / "tests" / "test_bot_slack.py").exists()
    deps = pyproject_deps(project_path)["project"]["dependencies"]
    assert not any(d.startswith(("discord", "slack")) for d in deps)
    scripts = scripts_of(project_path)
    assert "bot-discord-bot-example" not in scripts
    assert "bot-slack-bot-example" not in scripts
    # no bot-shaped directory is left empty by a half-applied layer (the
    # render's own empty dirs — .git internals, an unpopulated docs/ tree —
    # are pre-existing behaviour, not the layer's)
    layer_dirs = [project_path / "src", project_path / "tests", project_path / "app", *project_path.rglob("src/*")]
    empty = [d for d in layer_dirs if d.is_dir() and not any(d.iterdir())]
    assert not empty


@pytest.mark.parametrize(
    ("platform_answers", "entry_point", "tokens", "dockerfile_note"),
    [
        ({}, "bot-discord-bot-example", ("DISCORD_BOT_TOKEN",), "--sync-guild"),
        (SLACK_ANSWERS, "bot-slack-bot-example", ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"), "no port"),
    ],
    ids=["discord", "slack"],
)
def test_bot_docker_task(
    tmp_path: Path,
    platform_answers: dict,
    entry_point: str,
    tokens: tuple[str, ...],
    dockerfile_note: str,
):
    """docker + the layer ships the bot-serve task (the mcp-serve twin) for the
    selected platform: the task runs that platform's entry point with exactly
    its tokens, and the Dockerfile documents the same run (the Slack container
    opens no port, so nothing is EXPOSEd for it)."""
    copy_project(tmp_path, project_type="cli", include_bot=True, docker=True, **platform_answers)
    taskfile = (tmp_path / "justfile").read_text()
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "bot-serve:" in taskfile
    for text in (entry_point, *tokens):
        assert text in taskfile, text
        assert text in dockerfile, text
    assert dockerfile_note in dockerfile


def test_bot_no_docker_no_task(tmp_path: Path):
    """Without docker, no bot-serve task is generated."""
    copy_project(tmp_path, project_type="cli", include_bot=True, docker=False)
    assert "bot-serve" not in (tmp_path / "justfile").read_text()


@pytest.mark.parametrize(
    ("platform_answers", "bot"),
    [
        ({}, ("bot_discord", "bot-discord-bot-example", "discord.py", "DISCORD_BOT_TOKEN")),
        (SLACK_ANSWERS, ("bot_slack", "bot-slack-bot-example", "slack-bolt", "SLACK_BOT_TOKEN")),
    ],
    ids=["discord", "slack"],
)
def test_bot_and_mcp_entry_points_do_not_collide(
    tmp_path: Path,
    platform_answers: dict,
    bot: tuple[str, str, str, str],
):
    """The two long-running layers stack: distinct modules, distinct scripts,
    both dependencies declared, one .env.example carrying both variables.

    `bot` is the selected platform's (module, console script, runtime
    dependency, token variable) — the four things its own scaffold test pins.
    """
    module, script, dependency, token = bot
    copy_project(tmp_path, project_type="cli", include_bot=True, include_mcp=True, **platform_answers)
    scripts = scripts_of(tmp_path)
    assert scripts[script] == f"bot_example.{module}:main"
    assert scripts["mcp-server-bot-example"] == "bot_example.mcp_server:main"
    deps = pyproject_deps(tmp_path)["project"]["dependencies"]
    assert any(d.startswith(dependency) for d in deps)
    assert any(d.startswith("mcp") for d in deps)
    env_example = (tmp_path / ".env.example").read_text()
    assert f"{token}=" in env_example
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
    _refusal_output(tmp_path, tmp_path / ".venv", "bot_example.bot_discord", ("DISCORD_BOT_TOKEN",))


@pytest.mark.heavy
@pytest.mark.network
def test_bot_slack_runs_in_process(tmp_path: Path):
    """The slack scaffold must work the same way: sync the project and run its
    own pytest (tests/test_bot_slack.py registers the listeners on a recording
    stand-in for slack_bolt.App and drives the /app_mention listener with a
    fake say — mention in, pong out, no socket, no token, no WebClient), then
    type-check and lint the slack module with no exclusions."""
    copy_project(tmp_path, project_type="cli", include_bot=True, **SLACK_ANSWERS)
    run = make_venv(tmp_path)
    run("uv run --locked pytest -q")
    run("uv run --locked basedpyright src tests")
    run("uv run --locked ruff check src tests")
    _refusal_output(
        tmp_path,
        tmp_path / ".venv",
        "bot_example.bot_slack",
        ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"),
    )


def _refusal_output(project_path: Path, venv: Path, module: str, tokens: tuple[str, ...]) -> str:
    """`python -m <pkg>.<module>` without tokens: the startup env check refuses
    (exit code 2, naming every variable that is not set) instead of
    half-starting."""
    # The tokens must be absent for the refusal to be what starts: drop them
    # from this process's environment rather than trusting it to be clean.
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DISCORD_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"}
    }
    proc = subprocess.run(
        shlex.split(f"uv run --locked python -m {module}"),
        cwd=str(project_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**env, "UV_PROJECT_ENVIRONMENT": "", "VIRTUAL_ENV": str(venv)},
        check=False,
    )
    output = proc.stdout.decode()
    assert proc.returncode == 2, output
    for token in tokens:
        assert token in output, output
    return output
