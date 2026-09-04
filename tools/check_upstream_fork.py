#!/usr/bin/env python3
"""Report new commits on the upstream fork parent's main.

DiamondLightSource/python-copier-template is this fork's parent. This is a
*different* concern from tools/check_upstream.py (which tracks hardcoded
version pins like MicroPython/CUDA/ROS2 EOL): this script tracks the git
history of the upstream fork relationship itself. Exits 1 when
upstream/main has commits not reachable from HEAD (see
.github/workflows/check-upstream-fork.yml, which opens an issue on drift).

Runs from a pristine checkout every time: it fetches straight from the
upstream URL into FETCH_HEAD instead of adding or removing a named remote.
"""

from __future__ import annotations

import subprocess
import sys

UPSTREAM_URL = "https://github.com/DiamondLightSource/python-copier-template.git"


def run(*args: str) -> str:
    # args is a fixed literal argv built by this script, never user input.
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout  # noqa: S603


def main() -> int:
    run("git", "fetch", UPSTREAM_URL, "main", "--quiet")
    commits = run("git", "log", "--oneline", "HEAD..FETCH_HEAD").strip()
    if commits:
        print("Upstream has new commits not yet reviewed:\n")
        print(commits)
        print(f"\nReview with: git fetch {UPSTREAM_URL} main && git log HEAD..FETCH_HEAD")
        return 1
    print("Up to date with upstream/main.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
