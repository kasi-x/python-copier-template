#!/usr/bin/env bash
# Fork copier-org/copier and clone it for contribution work.
# Usage: ./scripts/fork-setup.sh [DEST_DIR]
# Requires: gh, git. Upstream branch convention: master.
set -euo pipefail

DEST="${1:-$HOME/dev/copier}"

if ! command -v gh >/dev/null 2>&1; then
    echo "error: gh is not installed (https://cli.github.com)" >&2
    exit 1
fi

if [ -e "$DEST" ]; then
    echo "error: $DEST already exists (pass another dir or resume it)" >&2
    exit 1
fi

gh repo fork copier-org/copier --clone -- "$DEST"
cd "$DEST"
git remote add upstream https://github.com/copier-org/copier.git 2>/dev/null || true
git fetch upstream
echo "forked into $DEST (origin = your fork, upstream = copier-org/copier)"
git remote -v
