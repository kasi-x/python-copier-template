#!/usr/bin/env python3
"""Repository hygiene checks, shared by `task hygiene` and the `_hygiene.yml` CI job.

The four checks used to live as inline shell/python heredocs inside
`.github/workflows/_hygiene.yml`, which made them invisible to every local
run: a missing trailing newline or an unparsable YAML file only surfaced on
the first CI push. They now live here once, and both surfaces call this
module -- `uv run --locked python -m architekton.hygiene` locally, the same
command in the workflow.

The checks, in order:

- merge-conflict markers: a `<<<<<<< ` line at the start of any file, with
  binary files skipped the way `grep -I` does;
- oversized files: any file over 10 MiB, lockfiles excepted;
- trailing newline: every text file ends with exactly one newline
  (empty files pass -- there is no newline to miss);
- YAML validity: every `*.yml` / `*.yaml` parses via `yaml.safe_load_all`.

Two deliberate differences from the shell version:

- the candidate files come from `git ls-files --cached --others
  --exclude-standard` instead of `grep -r` / `rglob` over the whole tree, so
  the checks respect `.gitignore` / `.git/info/exclude` and never walk
  `.git/`, a rendered `.cache/` or a generated `site/` build -- exactly the
  set CI sees in a fresh checkout, and 787 files instead of 57k locally;
  outside a work tree the walk falls back to every regular file, so the
  module still runs on a bare tarball;
- the size check reads `st_size` rather than `du`'s allocated blocks: a
  sparse file (what `truncate` and several test fixtures produce) allocates
  nothing on disk but is still an oversized commit.

`yaml` is imported lazily inside the YAML check (and its absence degrades to
a printed skip): the generated project's workflow twin calls this file with
the runner's own `python3`, which has no pyyaml until setup-uv runs, and a
hard import would turn that into a crash instead of a skipped check. The
custom `!include` tags in `copier.yml`, unrendered `{% ... %}` Jinja sources
and the checkout/build directories are skipped there as well.

Usage:
    uv run --locked python -m architekton.hygiene
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

# Absolute path where available (readable failure when git is absent, and S607-clean).
# `worktree_files` falls back to a plain walk when this is None or the directory
# is no work tree.
GIT = shutil.which("git")

# A file over this many bytes is refused (the workflow's `du -m` said 10 MiB).
SIZE_LIMIT = 10 * 1024 * 1024

# Lockfiles are large by nature and nobody edits them: exempt from the size check.
SIZE_SKIP = re.compile(r"(^|/)(uv|pixi|poetry)\.lock$")

# Files whose trailing newline nobody controls (generated) or that end without
# one on purpose (`.jinja` partials, trimmed exactly so the render ends with
# one newline), plus the shared CI helpers this repo does not run.
NEWLINE_SKIP_SUFFIXES = ("uv.lock", "pixi.lock", "poetry.lock", "pyproject.toml", ".jinja")
NEWLINE_SKIP_PREFIX = ".github/pages"

YAML_SUFFIXES = (".yml", ".yaml")
# copier.yml carries custom `!include` tags; the rest are checkout/build output.
YAML_SKIP_DIRS = frozenset({".git", ".venv", "site", "build", "dist", "node_modules"})

# `grep -I` and the heredoc both sniffed only the first 8 KiB for a NUL byte.
BINARY_SNIFF = 8192


def _git_ls_files(root: Path) -> list[str] | None:
    """Git's own file list, or None when git is missing or this is no work tree."""
    if GIT is None:
        return None
    try:
        listed = subprocess.check_output(  # noqa: S603  WHYNOT: fixed git argv in our own checkout; the walk below covers a missing git.
            [GIT, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [name for name in listed.split("\0") if name]


def worktree_files(root: Path) -> list[Path]:
    """Every file the checks look at: tracked plus untracked-unignored, by `root`-relative path.

    This is what `grep -rI ... .` saw, minus `.git/` and minus everything
    git's exclude rules hide. Outside a work tree (a released tarball) the
    tree is walked instead. Paths stay relative to `root` -- git prints them
    that way, the reported findings read that way, and the checks run from
    `root` (`main` always passes the working directory).
    """
    listed = _git_ls_files(root)
    if listed is None:
        return [
            path.relative_to(root) for path in sorted(root.rglob("*")) if path.is_file() and ".git" not in path.parts
        ]
    return [Path(name) for name in listed]


def _read_bytes(path: Path) -> bytes | None:
    """The file's bytes, or None when they cannot be read (dangling symlink, race)."""
    try:
        return path.read_bytes()
    except OSError:
        return None


def conflict_markers(files: list[Path]) -> list[str]:
    """`path:line` for every `<<<<<<< ` line, binary files skipped like `grep -I`."""
    found: list[str] = []
    for path in files:
        data = _read_bytes(path)
        if data is None or b"\0" in data[:BINARY_SNIFF]:
            continue
        for number, line in enumerate(data.split(b"\n"), start=1):
            if line.startswith(b"<<<<<<< "):
                found.append(f"{path.as_posix()}:{number}")
    return found


def oversized(files: list[Path]) -> list[str]:
    """`path (bytes)` for every file over `SIZE_LIMIT`, lockfiles excepted."""
    big: list[str] = []
    for path in files:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > SIZE_LIMIT and not SIZE_SKIP.search(path.as_posix()):
            big.append(f"{path.as_posix()} ({size} bytes)")
    return big


def missing_trailing_newline(files: list[Path]) -> list[str]:
    """Paths that do not end with a newline; empty files and binary files pass."""
    bad: list[str] = []
    for path in files:
        name = path.as_posix()
        if name.endswith(NEWLINE_SKIP_SUFFIXES) or name.startswith(NEWLINE_SKIP_PREFIX) or not path.is_file():
            continue  # directory symlinks and other non-regular entries too
        data = _read_bytes(path)
        if data is None or b"\0" in data[:BINARY_SNIFF]:
            continue
        if data and not data.endswith(b"\n"):
            bad.append(name)
    return bad


def invalid_yaml(files: list[Path]) -> list[str]:
    """`path: error` for every candidate YAML file that no longer parses.

    `files` is the same candidate set the other checks read (`worktree_files`),
    so a rendered `.cache/` or a built `site/` -- git-ignored, and absent from
    CI's fresh checkout -- is never walked.

    `yaml` is imported here, not at module level: the generated project's
    workflow runs this file with the runner's bare python3, where pyyaml only
    exists after setup-uv. A missing pyyaml prints a notice and skips the
    check rather than failing the run.
    """
    try:
        import yaml  # noqa: PLC0415  WHYNOT: the generated project's workflow runs this file on a bare python3 where pyyaml arrives only with setup-uv; a top-level import would crash instead of skipping.
    except ImportError:
        print("hygiene: pyyaml unavailable -- YAML parse check skipped", file=sys.stderr)  # noqa: T201
        return []
    bad: list[str] = []
    for path in sorted(files):
        if path.suffix not in YAML_SUFFIXES or path.name == "copier.yml" or not path.is_file():
            continue
        if YAML_SKIP_DIRS & set(path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            bad.append(f"{path.as_posix()}: {exc}")
            continue
        if "{%" in text:
            continue  # unrendered Jinja template source
        try:
            list(yaml.safe_load_all(text))
        except yaml.YAMLError as exc:
            bad.append(f"{path.as_posix()}: {exc}")
    return bad


def main() -> int:
    """Run all four checks against the current directory; 0 when clean, else 1."""
    root = Path.cwd()
    files = worktree_files(root)
    failures = [
        ("merge-conflict markers", conflict_markers(files)),
        (f"files over {SIZE_LIMIT // (1024 * 1024)}MB", oversized(files)),
        ("missing trailing newline", missing_trailing_newline(files)),
        ("invalid YAML", invalid_yaml(files)),
    ]
    failed = False
    for label, bad in failures:
        if not bad:
            continue
        failed = True
        print(f"hygiene: {label}")  # noqa: T201
        for item in bad:
            print(f"  {item}")  # noqa: T201
    if failed:
        return 1
    print("hygiene: clean")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
