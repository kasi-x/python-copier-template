#!/bin/sh
# One-time worktree setup: install locked deps so build/test results are real.
# Future worktrees source this instead of paying the install tax per session.
set -eu
uv sync --locked
