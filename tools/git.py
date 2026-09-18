#!/usr/bin/env python3
"""Run git for the driver-layer tools that act on this repository's trees.

One discovery (`GIT`) and one runner (`run`) for the tools that shell out to
git: batch, detect and update_rehearsal. `run` captures output, never checks
the exit code, and never touches a shell -- what a failure *means* is each
caller's policy (batch returns the CompletedProcess for the caller to judge,
detect turns any failure into None, update_rehearsal asserts), which is why
those three wrappers stay distinct above this one runner.

The standalone maintenance scripts (check_questionnaire_diff,
check_upstream_fork) deliberately keep their own runners: a pristine checkout
or a released tarball is their world, so they import nothing from tools/
(tests/test_tool_layers.py's `standalone` layer).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

#: The git binary, resolved once at import, with the plain-name fallback so a
#: git-less machine fails with a readable message at call time (and S607 is
#: clean: the argv never goes near a shell).
GIT = shutil.which("git") or "git"


def run(where: Path, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    """Run `git -C <where> <args>`, capturing output; the exit code is the caller's business."""
    return subprocess.run(  # noqa: S603  WHYNOT: fixed git argv of our own checkout, never user input.
        [GIT, "-C", str(where), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
