"""The bot layer's render contract and its real-execution proof.

tests/test_example_layers.py owns the per-feature render assertions for the
layers that predate the witness ledger; this module is the bot layer's own file
(TODO.md §4). The fast tests pin the wiring on each base (scaffold iff
``bot_discord_effective`` / ``bot_slack_effective`` / ``bot_line_effective`` /
``bot_gmail_effective``,
the dependency / entry point / env-var gates, the leak check on the types that
must never be offered the layer); the heavy tests render a cli project per
platform, install it, and exercise the generated in-process test suite — a
fake interaction driving ``build_bot()``'s ``/ping`` callback (discord), a fake
``say`` driving the ``/app_mention`` listener (slack), a signed
``POST /callback`` over httpx's ASGITransport with a recording reply (line,
where the unsigned and wrongly signed bodies are the cases that matter) or a
recording discovery client driving ``poll_once()`` (gmail, whose recorded
``send`` kwargs are decoded RFC 2822 bytes), with
no connection and no token either way.
"""

import os
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from support import copy_project_recommended
from support import make_venv

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_copier_structure.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools import when_model  # noqa: E402

# The package this file renders under: the shared "Project Details"
# (tools/answers.py BASE) plus this name, with copier's own defaults driving
# everything else, so the use_recommended_* gates are exercised rather than
# pinned (support.copy_project_recommended's docstring).
BOT_PACKAGE = "bot_example"

# The second generated platform's answers: No to the recommended platform,
# then `slack`. Spread into the renders that exercise it, and registered in
# tests/test_answer_fixtures.py's drift guard like every other fixture here.
SLACK_ANSWERS: dict[str, Any] = {"use_recommended_bot": False, "bot_platform": "slack"}

# The third generated platform's answers, same shape. LINE is the platform
# that listens (the Messaging API pushes to a webhook), so this fixture is also
# what pins the port / BOT_PORT side of the render.
LINE_ANSWERS: dict[str, Any] = {"use_recommended_bot": False, "bot_platform": "line"}

# The fourth generated platform's answers, same shape. GMAIL is the platform
# that polls (an outbound call like discord/slack dial out) and whose
# credentials are FILES (paths, not secrets in the environment), so this
# fixture is also what pins the .gitignore side of the render.
GMAIL_ANSWERS: dict[str, Any] = {"use_recommended_bot": False, "bot_platform": "gmail"}

# The non-recommended platform answer sets, for the tests that must hold
# for every platform rather than for one of them. The recommended one
# (discord) is left out on purpose: `bot_discord_effective` is keyed on
# `use_recommended_bot or bot_platform == 'discord'`, so it is not the same
# branch as the custom ones.
CUSTOM_PLATFORMS: list[dict[str, Any]] = [SLACK_ANSWERS, LINE_ANSWERS, GMAIL_ANSWERS]


def copy_project(project_path: Path, **kwargs: Any) -> None:
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
    # the recommended path renders the recommended platform and nothing else
    assert not (pkg / "bot_slack.py").exists()
    assert not (pkg / "bot_line.py").exists()
    assert not (pkg / "bot_gmail.py").exists()
    assert "bot-line-bot-example" not in scripts_of(tmp_path)
    assert "bot-gmail-bot-example" not in scripts_of(tmp_path)
    # the CLI contract is untouched: the console script stays the package's
    assert scripts_of(tmp_path)["bot-example"] == "bot_example.__main__:main"


def test_env_example_gate_and_readme_section_agree(tmp_path: Path):
    """The README's "Environment variables" section and `.env.example` are two
    renderings of one gate: a render that ships the env file must document it,
    and a render with no env consumers must ship neither. The two conditions
    drifted once -- a bot-only render shipped `.env.example` with the bot
    tokens but no README section documenting them, because the README
    condition lagged the file-name condition by `bot_effective`."""
    copy_project(tmp_path, project_type="cli", include_bot=True)
    assert (tmp_path / ".env.example").is_file()
    assert "### Environment variables" in (tmp_path / "README.md").read_text()
    # A plain library has no env-var consumers: neither side of the gate fires.
    plain = tmp_path / "plain_library"
    copy_project(plain, project_type="library")
    assert not (plain / ".env.example").exists()
    assert "### Environment variables" not in (plain / "README.md").read_text()


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
    assert not (pkg / "bot_gmail.py").exists()
    assert not (tmp_path / "tests" / "test_bot_discord.py").exists()
    assert not any(d.startswith(("discord", "google")) for d in pyproject["project"]["dependencies"])
    assert "bot-discord-bot-example" not in scripts_of(tmp_path)
    assert "bot-gmail-bot-example" not in scripts_of(tmp_path)
    # the CLI contract is untouched: the console script stays the package's
    assert scripts_of(tmp_path)["bot-example"] == "bot_example.__main__:main"


def test_bot_line_scaffold_on_cli(tmp_path: Path):
    """No + bot_platform=line on a cli base: the line module rides the
    src-layout package with its own console script, its in-process test, the
    line-bot-sdk dependency (plus the ASGI stack its webhook server runs on,
    because a cli base has neither) and both credential variables — and no
    part of either sibling platform."""
    copy_project(tmp_path, project_type="cli", include_bot=True, **LINE_ANSWERS)
    pkg = tmp_path / "src" / "bot_example"
    assert (pkg / "bot_line.py").is_file()
    assert (tmp_path / "tests" / "test_bot_line.py").is_file()
    pyproject = pyproject_deps(tmp_path)
    deps = pyproject["project"]["dependencies"]
    assert "line-bot-sdk>=3,<4" in deps
    # the webhook app is this platform's own server, and only this one needs it
    assert "fastapi>=0.115,<1" in deps
    assert "uvicorn[standard]>=0.30,<1" in deps
    assert scripts_of(tmp_path)["bot-line-bot-example"] == "bot_example.bot_line:main"
    bot_module = (pkg / "bot_line.py").read_text()
    # the startup env check for both credentials, the build_app()/main() split,
    # the signature-verified route, logging through the generated logging_setup
    assert "LINE_CHANNEL_SECRET" in bot_module
    assert "LINE_CHANNEL_ACCESS_TOKEN" in bot_module
    assert "def build_app(" in bot_module
    assert '"/callback"' in bot_module
    assert "X-Line-Signature" in bot_module
    assert "from bot_example.logging_setup import logger" in bot_module
    # .env.example documents both credentials and the port they are served on
    env_example = (tmp_path / ".env.example").read_text()
    assert "LINE_CHANNEL_SECRET=" in env_example
    assert "LINE_CHANNEL_ACCESS_TOKEN=" in env_example
    assert "BOT_PORT=" in env_example
    # the in-process test drives the route, not just the seed: the dev group
    # carries the transport (httpx) and the async runner (anyio) it needs
    assert "httpx>=0.27,<1" in pyproject["dependency-groups"]["dev"]
    assert "anyio" in pyproject["dependency-groups"]["dev"]
    # the README advertises the platform that was selected
    assert "bot-line-bot-example" in (tmp_path / "README.md").read_text()
    # one platform per render: nothing from the other two is generated
    assert not (pkg / "bot_discord.py").exists()
    assert not (pkg / "bot_slack.py").exists()
    assert not (pkg / "bot_gmail.py").exists()
    assert not (tmp_path / "tests" / "test_bot_discord.py").exists()
    assert not (tmp_path / "tests" / "test_bot_slack.py").exists()
    assert not any(d.startswith(("discord", "slack", "google")) for d in deps)
    assert "bot-discord-bot-example" not in scripts_of(tmp_path)
    assert "bot-slack-bot-example" not in scripts_of(tmp_path)
    assert "bot-gmail-bot-example" not in scripts_of(tmp_path)
    # the CLI contract is untouched: the console script stays the package's
    assert scripts_of(tmp_path)["bot-example"] == "bot_example.__main__:main"


def test_bot_gmail_scaffold_on_cli(tmp_path: Path):
    """No + bot_platform=gmail on a cli base: the gmail module rides the
    src-layout package with its own console script, its in-process test, the
    google dependencies and both credential-path variables — and no part of
    any sibling platform. Gmail is the platform whose credentials are FILES,
    so the generated .gitignore covers the two JSON files the way it covers
    CTF flag* files."""
    copy_project(tmp_path, project_type="cli", include_bot=True, **GMAIL_ANSWERS)
    pkg = tmp_path / "src" / "bot_example"
    assert (pkg / "bot_gmail.py").is_file()
    assert (tmp_path / "tests" / "test_bot_gmail.py").is_file()
    pyproject = pyproject_deps(tmp_path)
    deps = pyproject["project"]["dependencies"]
    assert "google-api-python-client>=2,<3" in deps
    assert "google-auth>=2,<3" in deps
    assert "google-auth-oauthlib>=1,<2" in deps
    # polling dials out: no ASGI stack is needed (that is line's)
    assert not any(d.startswith(("fastapi", "uvicorn")) for d in deps)
    assert scripts_of(tmp_path)["bot-gmail-bot-example"] == "bot_example.bot_gmail:main"
    bot_module = (pkg / "bot_gmail.py").read_text()
    # the startup env check for both credential paths, the build_service()/
    # main() split, the poll loop, logging through the generated logging_setup
    assert "GMAIL_CREDENTIALS_JSON" in bot_module
    assert "GMAIL_TOKEN_JSON" in bot_module
    assert "GMAIL_POLL_SECONDS" in bot_module
    assert "def build_service(" in bot_module
    assert "def poll_once(" in bot_module
    assert "from bot_example.logging_setup import logger" in bot_module
    # .env.example documents both credential paths and the polling interval
    env_example = (tmp_path / ".env.example").read_text()
    assert "GMAIL_CREDENTIALS_JSON=" in env_example
    assert "GMAIL_TOKEN_JSON=" in env_example
    assert "GMAIL_POLL_SECONDS=" in env_example
    # the credentials are files: the gitignore covers them like the CTF flags
    gitignore = (tmp_path / ".gitignore").read_text()
    assert "/credentials.json" in gitignore
    assert "/token.json" in gitignore
    # the README advertises the platform that was selected
    assert "bot-gmail-bot-example" in (tmp_path / "README.md").read_text()
    # one platform per render: nothing from the siblings is generated
    assert not (pkg / "bot_discord.py").exists()
    assert not (pkg / "bot_slack.py").exists()
    assert not (pkg / "bot_line.py").exists()
    assert not (tmp_path / "tests" / "test_bot_discord.py").exists()
    assert not (tmp_path / "tests" / "test_bot_slack.py").exists()
    assert not (tmp_path / "tests" / "test_bot_line.py").exists()
    assert not any(d.startswith(("discord", "slack", "line-bot")) for d in deps)
    assert "bot-discord-bot-example" not in scripts_of(tmp_path)
    assert "bot-slack-bot-example" not in scripts_of(tmp_path)
    assert "bot-line-bot-example" not in scripts_of(tmp_path)
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


def test_bot_line_scaffold_on_web_api(tmp_path: Path):
    """A web_api base hosts the line module in the top-level app/ package too,
    and still runs it as its own process: the file moves, but it is not
    mounted into the generated API (it owns its uvicorn). The ASGI stack is
    declared once — the web_api base already has it — and the entry point
    points at the app import root."""
    copy_project(tmp_path, project_type="web_api", include_bot=True, **LINE_ANSWERS)
    pyproject = pyproject_deps(tmp_path)
    deps = pyproject["project"]["dependencies"]
    assert "line-bot-sdk>=3,<4" in deps
    # fastapi / uvicorn come from the web_api base: the line platform must not
    # declare a second copy of either
    assert deps.count("fastapi>=0.115,<1") == 1
    assert deps.count("uvicorn[standard]>=0.30,<1") == 1
    assert (tmp_path / "app" / "bot_line.py").is_file()
    assert not list(tmp_path.rglob("src/*/bot_line.py"))
    assert scripts_of(tmp_path)["bot-line-bot-example"] == "app.bot_line:main"
    assert "from app import bot_line" in (tmp_path / "tests" / "test_bot_line.py").read_text()
    # no console script for the web_api CLI (there is no <pkg> CLI at all)
    assert "bot-example" not in scripts_of(tmp_path)


def test_bot_gmail_scaffold_on_web_api(tmp_path: Path):
    """A web_api base hosts the gmail module in the top-level app/ package too,
    and it stays a poller: unlike the line platform it drags no ASGI stack in
    (the poll dials out), and the entry point points at the app import root."""
    copy_project(tmp_path, project_type="web_api", include_bot=True, **GMAIL_ANSWERS)
    pyproject = pyproject_deps(tmp_path)
    deps = pyproject["project"]["dependencies"]
    assert "google-api-python-client>=2,<3" in deps
    assert "google-auth>=2,<3" in deps
    assert "google-auth-oauthlib>=1,<2" in deps
    # the google deps are the ONLY new runtime deps: fastapi/uvicorn count
    # comes from the web_api base itself, untouched
    assert deps.count("fastapi>=0.115,<1") == 1
    assert deps.count("uvicorn[standard]>=0.30,<1") == 1
    assert (tmp_path / "app" / "bot_gmail.py").is_file()
    assert not list(tmp_path.rglob("src/*/bot_gmail.py"))
    assert scripts_of(tmp_path)["bot-gmail-bot-example"] == "app.bot_gmail:main"
    assert "from app import bot_gmail" in (tmp_path / "tests" / "test_bot_gmail.py").read_text()
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


def test_bot_line_flat_layout(tmp_path: Path):
    """The flat-layout package variant also ships the line module and its script."""
    copy_project(tmp_path, project_type="cli", layout="flat", include_bot=True, **LINE_ANSWERS)
    pyproject = pyproject_deps(tmp_path)
    assert "line-bot-sdk>=3,<4" in pyproject["project"]["dependencies"]
    assert (tmp_path / "bot_example" / "bot_line.py").is_file()
    assert (tmp_path / "tests" / "test_bot_line.py").is_file()
    assert not (tmp_path / "src").exists()


def test_bot_gmail_flat_layout(tmp_path: Path):
    """The flat-layout package variant also ships the gmail module and its script."""
    copy_project(tmp_path, project_type="cli", layout="flat", include_bot=True, **GMAIL_ANSWERS)
    pyproject = pyproject_deps(tmp_path)
    assert "google-api-python-client>=2,<3" in pyproject["project"]["dependencies"]
    assert (tmp_path / "bot_example" / "bot_gmail.py").is_file()
    assert (tmp_path / "tests" / "test_bot_gmail.py").is_file()
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
    assert not (tmp_path / "src" / "bot_example" / "bot_gmail.py").exists()
    assert not any(d.startswith(("slack", "google")) for d in pyproject["project"]["dependencies"])
    assert "bot-slack-bot-example" not in scripts_of(tmp_path)
    assert "bot-line-bot-example" not in scripts_of(tmp_path)
    assert "bot-gmail-bot-example" not in scripts_of(tmp_path)
    assert "line-bot-sdk" not in pyproject["project"]["dependencies"]
    env_example = (tmp_path / ".env.example").read_text()
    assert "SLACK_BOT_TOKEN" not in env_example
    assert "LINE_CHANNEL_SECRET" not in env_example
    assert "GMAIL_CREDENTIALS_JSON" not in env_example


def test_bot_absent_by_default(tmp_path: Path):
    """Without the layer: no module, no test, no dependency, no env gate."""
    copy_project(tmp_path, project_type="cli")
    assert not (tmp_path / "src" / "bot_example" / "bot_discord.py").exists()
    assert not (tmp_path / "src" / "bot_example" / "bot_slack.py").exists()
    assert not (tmp_path / "src" / "bot_example" / "bot_line.py").exists()
    assert not (tmp_path / "src" / "bot_example" / "bot_gmail.py").exists()
    assert not (tmp_path / "tests" / "test_bot_discord.py").exists()
    assert not (tmp_path / "tests" / "test_bot_slack.py").exists()
    assert not (tmp_path / "tests" / "test_bot_line.py").exists()
    assert not (tmp_path / "tests" / "test_bot_gmail.py").exists()
    deps = pyproject_deps(tmp_path)["project"]["dependencies"]
    assert not any(d.startswith(("discord", "slack", "line-bot", "google")) for d in deps)
    assert "bot-discord-bot-example" not in scripts_of(tmp_path)
    assert "bot-slack-bot-example" not in scripts_of(tmp_path)
    assert "bot-line-bot-example" not in scripts_of(tmp_path)
    assert "bot-gmail-bot-example" not in scripts_of(tmp_path)
    assert not (tmp_path / ".env.example").exists()


@pytest.mark.parametrize("platform_answers", CUSTOM_PLATFORMS, ids=["slack", "line", "gmail"])
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
def test_bot_not_offered_to_other_types(
    tmp_path: Path,
    project_type: str,
    extra: dict,
    platform_answers: dict,
):
    """Forcing the layer on the types that must not be offered it must not
    leak a module, a dependency or an entry point anywhere.

    A custom platform is forced alongside include_bot on purpose: what keeps
    the layer out of these bases is ``bot_effective``'s base guard, not the
    platform selection, so the sharpest fixture is the one that would leak if
    the guard were wired to a platform condition instead. All three custom
    platforms are exercised — slack (an outbound client), line (a module that
    would also drag fastapi/uvicorn in) and gmail (whose dependency trio would
    collide with a gcp cloud_provider's google-* deps) — because a guard wired
    to a platform condition would leak differently for each.
    """
    project_path = tmp_path / project_type
    copy_project(project_path, project_type=project_type, include_bot=True, **platform_answers, **extra)
    assert not list(project_path.rglob("bot_discord.py"))
    assert not list(project_path.rglob("bot_slack.py"))
    assert not list(project_path.rglob("bot_line.py"))
    assert not list(project_path.rglob("bot_gmail.py"))
    assert not (project_path / "tests" / "test_bot_discord.py").exists()
    assert not (project_path / "tests" / "test_bot_slack.py").exists()
    assert not (project_path / "tests" / "test_bot_line.py").exists()
    assert not (project_path / "tests" / "test_bot_gmail.py").exists()
    deps = pyproject_deps(project_path)["project"]["dependencies"]
    assert not any(d.startswith(("discord", "slack", "line-bot", "google")) for d in deps)
    scripts = scripts_of(project_path)
    assert "bot-discord-bot-example" not in scripts
    assert "bot-slack-bot-example" not in scripts
    assert "bot-line-bot-example" not in scripts
    assert "bot-gmail-bot-example" not in scripts
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
        (LINE_ANSWERS, "bot-line-bot-example", ("LINE_CHANNEL_SECRET", "LINE_CHANNEL_ACCESS_TOKEN"), "8000:8000"),
        (GMAIL_ANSWERS, "bot-gmail-bot-example", ("GMAIL_CREDENTIALS_JSON", "GMAIL_TOKEN_JSON"), "read-only"),
    ],
    ids=["discord", "slack", "line", "gmail"],
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
    its credentials, and the Dockerfile documents the same run. The container
    differences are the platform's: Slack opens no port (nothing is EXPOSEd
    for it), LINE serves its webhook, so both its task recipe and the
    Dockerfile's example publish 8000, and Gmail is the one whose credentials
    are files, so its task recipe and Dockerfile bind them read-only."""
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
        (LINE_ANSWERS, ("bot_line", "bot-line-bot-example", "line-bot-sdk", "LINE_CHANNEL_SECRET")),
        (GMAIL_ANSWERS, ("bot_gmail", "bot-gmail-bot-example", "google-api-python-client", "GMAIL_CREDENTIALS_JSON")),
    ],
    ids=["discord", "slack", "line", "gmail"],
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


def test_include_bot_and_include_mcp_gates_stay_in_sync():
    """The two long-running layers share one base set: `include_bot.when` must
    offer the layer wherever `include_mcp.when` offers its.

    Both gates are the ask-time half of the same base guard — the
    `bot_effective` / `mcp_effective` base guards (questions/_internal.yml)
    accept `project_type == 'cli'`, `project_type == 'web_api'` and the
    library+`include_web_api` combo. include_mcp grew its `or include_web_api`
    clause by hand before include_bot did, so one effective configuration (a
    library base that opted into the web_api layer) was asked about MCP but
    not about the bot. Pin the gates' base literals and combo reference so a
    future base or layer changes both or neither; a drift here would open the
    same hole `bot_effective`'s use of the effective `web_api` cannot paper
    over, because the unasked question stays at its default.
    """
    questions, _ = when_model.load_questions()
    bot = questions["include_bot"]["when"]
    mcp = questions["include_mcp"]["when"]
    for gate, when in (("include_bot", bot), ("include_mcp", mcp)):
        bases = set(re.findall(r"'([a-z0-9_]+)'", when))
        assert bases == {"cli", "web_api"}, (
            f"{gate}.when's base literals drifted from the long-running layer's base set "
            f"({sorted(bases)} != ['cli', 'web_api']); keep it in sync with include_bot / "
            "include_mcp and the bot_effective / mcp_effective base guards"
        )
        assert "include_web_api" in when, (
            f"{gate}.when lost the library+include_web_api combo — the effective "
            "configuration cli/web_api bases see must see the layer question too"
        )


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


@pytest.mark.heavy
@pytest.mark.network
def test_bot_line_runs_in_process(tmp_path: Path):
    """The line scaffold must work the same way: sync the project and run its
    own pytest (tests/test_bot_line.py drives the signed POST /callback route
    over httpx's ASGITransport with a recording reply — a signed ping in, pong
    out, and an unsigned or wrongly signed body rejected without a reply, no
    token, no client, no network), then type-check and lint the line module
    with no exclusions."""
    copy_project(tmp_path, project_type="cli", include_bot=True, **LINE_ANSWERS)
    run = make_venv(tmp_path)
    run("uv run --locked pytest -q")
    run("uv run --locked basedpyright src tests")
    run("uv run --locked ruff check src tests")
    _refusal_output(
        tmp_path,
        tmp_path / ".venv",
        "bot_example.bot_line",
        ("LINE_CHANNEL_SECRET", "LINE_CHANNEL_ACCESS_TOKEN"),
    )


@pytest.mark.heavy
@pytest.mark.network
def test_bot_gmail_runs_in_process(tmp_path: Path):
    """The gmail scaffold must work the same way: sync the project and run its
    own pytest (tests/test_bot_gmail.py drives poll_once() with a recording
    stand-in for the Gmail discovery client — a `/ping` subject in, the pong
    reply sent on the message's thread and the message marked read, and mail
    without the trigger left unread; the raw RFC 2822 reply is decoded right
    in the test, with no OAuth, no browser, no network, no mailbox), then
    type-check and lint the gmail module with no exclusions."""
    copy_project(tmp_path, project_type="cli", include_bot=True, **GMAIL_ANSWERS)
    run = make_venv(tmp_path)
    run("uv run --locked pytest -q")
    run("uv run --locked basedpyright src tests")
    run("uv run --locked ruff check src tests")
    _refusal_output(
        tmp_path,
        tmp_path / ".venv",
        "bot_example.bot_gmail",
        ("GMAIL_CREDENTIALS_JSON", "GMAIL_TOKEN_JSON"),
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
        if key
        not in {
            "DISCORD_BOT_TOKEN",
            "SLACK_BOT_TOKEN",
            "SLACK_APP_TOKEN",
            "LINE_CHANNEL_SECRET",
            "LINE_CHANNEL_ACCESS_TOKEN",
            "GMAIL_CREDENTIALS_JSON",
            "GMAIL_TOKEN_JSON",
        }
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
