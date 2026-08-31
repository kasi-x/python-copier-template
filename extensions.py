"""Custom Jinja extensions used while *generating* a project from this template.

Referenced from `copier.yml` via `_jinja_extensions`. These only run inside
`copier copy`/`copier update` itself (which is why `copier-template-extensions`
is a dev dependency of this repo, not of generated projects) — none of this
code ends up in a generated project.
"""

from __future__ import annotations

import subprocess
from datetime import UTC
from datetime import datetime
from typing import Any
from typing import cast

from jinja2 import Environment
from jinja2.ext import Extension


def _run(cmd: list[str], timeout: float = 2.0) -> str:
    """Best-effort run of a local CLI, returning "" on any failure."""
    try:
        result = subprocess.run(  # noqa: S603
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def git_user_name() -> str:
    """Local `git config user.name`, or "" if unset/unavailable."""
    return _run(["git", "config", "--get", "user.name"])


def git_user_email() -> str:
    """Local `git config user.email`, or "" if unset/unavailable."""
    return _run(["git", "config", "--get", "user.email"])


def github_username() -> str:
    """Best-effort GitHub username: the logged-in `gh` user, else `git config github.user`."""
    return _run(["gh", "api", "user", "-q", ".login"], timeout=3.0) or _run(["git", "config", "--get", "github.user"])


class GitExtension(Extension):
    """Adds `git_user_name()`, `git_user_email()` and `github_username()` globals.

    Used only as smart defaults for the author/GitHub-org questions in
    copier.yml — the user is always shown the prompt and can override them.
    """

    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        # jinja2's stubs only type `globals`'s well-known built-in keys
        # (range, dict, cycler, ...), not arbitrary custom ones.
        globals_ = cast(dict[str, Any], environment.globals)
        globals_["git_user_name"] = git_user_name
        globals_["git_user_email"] = git_user_email
        globals_["github_username"] = github_username


class CurrentYearExtension(Extension):
    """Adds a `current_year()` global, used for the LICENSE copyright year."""

    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        cast(dict[str, Any], environment.globals)["current_year"] = lambda: str(datetime.now(tz=UTC).year)
