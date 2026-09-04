"""Custom Jinja extensions used while *generating* a project from this template.

Referenced from `copier.yml` via `_jinja_extensions`. These only run inside
`copier copy`/`copier update` itself (which is why `copier-template-extensions`
is a dev dependency of this repo, not of generated projects) — none of this
code ends up in a generated project.
"""

from __future__ import annotations

import re
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


def cuda_hint() -> str:
    """One-line GPU recommendation from `nvidia-smi`, or "" without a GPU.

    Shown in the use_gpu help text so the user can sanity-check the CUDA
    choice at generation time. Never blocks or decides anything: the
    generated project always pins the template's CUDA (currently 12.6),
    and a missing/old driver just yields "" or a driver-update nudge.
    """
    out = _run(["nvidia-smi"])
    if not out:
        return ""
    cuda_m = re.search(r"CUDA Version: (\d+)\.(\d+)", out)
    gpu_m = re.search(r"^\| *\d+ +(.+?) +Off \|", out, re.MULTILINE)
    gpu = gpu_m.group(1).strip() if gpu_m else "NVIDIA GPU"
    if not cuda_m:
        return f"Detected {gpu}, but the driver CUDA version is unreadable."
    major, minor = int(cuda_m.group(1)), int(cuda_m.group(2))
    if (major, minor) >= (12, 6):
        return f"Detected {gpu} (driver CUDA {major}.{minor}): the pinned CUDA 12.6 image works here."
    return (
        f"Detected {gpu} (driver CUDA {major}.{minor}): older than the pinned "
        "CUDA 12.6 — update the NVIDIA driver, or the GPU container will not start."
    )


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
        globals_["cuda_hint"] = cuda_hint


class CurrentYearExtension(Extension):
    """Adds a `current_year()` global, used for the LICENSE copyright year."""

    def __init__(self, environment: Environment) -> None:
        super().__init__(environment)
        cast(dict[str, Any], environment.globals)["current_year"] = lambda: str(datetime.now(tz=UTC).year)
