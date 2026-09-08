#!/usr/bin/env bash
# Sanity-check a patch against a copier checkout without applying it.
# Usage: ./scripts/verify-patch.sh patches/<area>-<slug>.patch [/path/to/copier]
set -euo pipefail

PATCH="${1:?usage: verify-patch.sh <patch> [copier-checkout]}"
CHECKOUT="${2:-$HOME/dev/copier}"

if [ ! -f "$PATCH" ]; then
    echo "error: patch not found: $PATCH" >&2
    exit 1
fi
if [ ! -d "$CHECKOUT/.git" ]; then
    echo "error: not a git checkout: $CHECKOUT (run scripts/fork-setup.sh first)" >&2
    exit 1
fi

cd "$CHECKOUT"
git apply --check --verbose "$OLDPWD/$PATCH"
echo "--- files touched ---"
git apply --stat "$OLDPWD/$PATCH"
echo "--- next: run the upstream tests covering these files per CONTRIBUTING.md, then file the PR yourself ---"
