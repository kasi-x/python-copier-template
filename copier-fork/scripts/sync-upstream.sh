#!/usr/bin/env bash
# Sync a copier fork checkout with upstream master.
# Usage: cd /path/to/copier && /path/to/python-copier-template/copier-fork/scripts/sync-upstream.sh
set -euo pipefail

git fetch upstream
git checkout master
git merge --ff-only upstream/master
echo "synced to $(git rev-parse --short HEAD) — re-verify FEATURES.md source-line refs past 9.18.1"
