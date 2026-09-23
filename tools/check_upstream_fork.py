#!/usr/bin/env python3
"""Report new commits on the upstream fork parent's main.

DiamondLightSource/python-copier-template is this fork's parent. This is a
*different* concern from tools/check_upstream.py (which tracks hardcoded
version pins like MicroPython/CUDA/ROS2 EOL): this script tracks the git
history of the upstream fork relationship itself.

The fork deliberately diverged (own tags, own questionnaire), so upstream
commits are never merged wholesale -- they are *reviewed* and selectively
adopted. The comparison is therefore not HEAD..FETCH_HEAD (which would flag
the same reviewed commits forever) but "commits on upstream/main newer than
the reviewed marker" in `.upstream-fork-reviewed` -- a one-line file holding
the upstream SHA a human last reviewed. Exits 1 when upstream has commits
past that marker (see .github/workflows/check-upstream-fork.yml, which opens
an issue on drift). After reviewing, commit the new upstream SHA into the
marker file.

Runs from a pristine checkout every time: it fetches straight from the
upstream URL into FETCH_HEAD instead of adding or removing a named remote.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
UPSTREAM_URL = "https://github.com/DiamondLightSource/python-copier-template.git"
MARKER = TOP / ".upstream-fork-reviewed"


def run(*args: str) -> str:
    # args is a fixed literal argv built by this script, never user input.
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout  # noqa: S603


def main() -> int:
    run("git", "fetch", UPSTREAM_URL, "main", "--quiet")
    upstream_head = run("git", "rev-parse", "FETCH_HEAD").strip()
    if not MARKER.exists():
        print(
            f"No reviewed marker at {MARKER.name}: record the upstream SHA the "
            "fork's history was last reviewed against (one line, full sha).\n"
            f"Current upstream/main: {upstream_head}",
            file=sys.stderr,
        )
        return 2
    reviewed = MARKER.read_text(encoding="utf-8").strip()
    if reviewed == upstream_head:
        print(f"Up to date with upstream/main (reviewed at {reviewed[:10]}).")
        return 0
    probe = subprocess.run(  # noqa: S603  # fixed literal argv, never user input
        ["git", "merge-base", "--is-ancestor", reviewed, "FETCH_HEAD"],  # noqa: S607
        check=False,
        capture_output=True,
    )
    if probe.returncode != 0:
        # Marker names a commit upstream rewrote away (force-push), one that
        # is not an ancestor of upstream/main, or a SHA that does not resolve
        # at all -- flag it rather than silently passing on an empty range.
        print(
            f"The reviewed marker {reviewed[:10]} is not an ancestor of "
            f"upstream/main ({upstream_head[:10]}): upstream history was "
            "rewritten or the marker is wrong. Re-review and update "
            f"{MARKER.name}.",
            file=sys.stderr,
        )
        return 1
    commits = run("git", "log", "--oneline", f"{reviewed}..FETCH_HEAD").strip()
    print("Upstream has new commits not yet reviewed:\n")
    print(commits)
    print(
        f"\nReview with: git fetch {UPSTREAM_URL} main && git log {reviewed[:10]}..FETCH_HEAD\n"
        f"Then record the review: echo {upstream_head} > {MARKER.name} && git commit"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
