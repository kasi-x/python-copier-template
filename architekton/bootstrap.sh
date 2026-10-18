#!/usr/bin/env bash
# architekton-py bootstrap — fetch a rendered preset from the `dist` branch
# and rewrite the few things that vary locally (names, log library).
#
#   curl -fsSL https://raw.githubusercontent.com/politeuma/architekton-py/dist/bootstrap.sh | bash
#   # or, offline:  REPO=... ./bootstrap.sh
#
# Questions it asks (with sensible defaults): preset, project name, package
# name, log library. Everything else is already decided in the rendered
# preset tree; if you need more knobs, use `copier copy` against the
# template on `main` — the same render produced these files.
set -euo pipefail

REPO="${REPO:-politeuma/architekton-py}"
BRANCH="${BRANCH:-dist}"
BASE_URL="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz"

say() { printf '\033[1m%s\033[0m\n' "$*"; }
ask() { # ask <var> <prompt> <default>; an env var of the same name wins
    local var=$1 prompt=$2 default=$3
    if [ -n "${!var:-}" ]; then return; fi
    if [ -t 0 ]; then
        read -r -p "$prompt [$default]: " REPLY
        printf -v "$var" '%s' "${REPLY:-$default}"
    else
        printf -v "$var" '%s' "$default"
    fi
}

# --- which presets exist ---------------------------------------------------
if [ -n "${DIST_DIR:-}" ]; then
    INDEX_JSON="$(cat "$DIST_DIR/index.json")"
else
    INDEX_JSON="$(curl -fsSL "$BASE_URL/index.json")"
fi
PRESETS="$(printf '%s' "$INDEX_JSON" | grep -o '"[^"]*": {' | sed 's/": {//;s/"//' | grep -v '^variants$' || true)"
if [ -z "$PRESETS" ]; then PRESETS="bare bot cli data-science library mcp-server micropython online-judge-atcoder online-judge-codeforces online-judge-kattis ros2 web-api"; fi

say "architekton-py bootstrap"
printf 'presets: %s\n' "$(printf '%s' "$PRESETS" | tr '\n' ' ')"
ask PRESET "project preset" "library"
ask PROJECT "project name (repo / distribution)" "my-project"
PKG_DEFAULT="$(printf '%s' "$PROJECT" | tr '-' '_')"
ask PACKAGE "package name (import)" "$PKG_DEFAULT"
ask LOG_LIB "log library (structlog / loguru / picologging / logging)" "structlog"

# --- fetch -----------------------------------------------------------------
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [ -n "${DIST_DIR:-}" ]; then
    say "copying ${PRESET} from local dist at ${DIST_DIR}"
    cp -a "$DIST_DIR/." "$TMP/"
else
    say "fetching ${PRESET} from ${REPO}@${BRANCH}"
    curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$TMP" --strip-components=1
fi
SRC="$TMP/$PRESET"
[ -d "$SRC" ] || { echo "no such preset: $PRESET" >&2; exit 1; }

DEST="$PWD/$PROJECT"
[ -e "$DEST" ] && { echo "exists: $DEST" >&2; exit 1; }
mkdir -p "$DEST"
cp -a "$SRC/." "$DEST/"

# --- rename ----------------------------------------------------------------
# The presets are rendered with smoke-example / smoke_example placeholders.
find "$DEST" -depth -name '*smoke_example*' | while read -r p; do
    mv "$p" "${p%smoke_example*}${PACKAGE}${p##*smoke_example}"
done
find "$DEST" -type f -exec grep -l 'smoke' {} + 2>/dev/null | while read -r f; do
    sed -i "s/smoke_example/${PACKAGE}/g; s/smoke-example/${PROJECT}/g" "$f"
done
mv "$DEST" "$DEST.tmp" && mv "$DEST.tmp" "$DEST" 2>/dev/null || true

# --- log library -----------------------------------------------------------
VARIANT="$TMP/variants/logging_setup/${PRESET}/${LOG_LIB}.py"
if [ -f "$VARIANT" ]; then
    SETUP="$(find "$DEST" -name logging_setup.py | head -1)"
    if [ -n "$SETUP" ]; then cp "$VARIANT" "$SETUP"; fi
    # dependency line: swap structlog for the choice ("logging" = stdlib: drop it)
    if [ "$LOG_LIB" = "logging" ]; then
        sed -i 's/"structlog", //; s/"structlog",//; s/"structlog"//' "$DEST/pyproject.toml"
    elif [ "$LOG_LIB" != "structlog" ]; then
        sed -i "s/\"structlog\"/\"${LOG_LIB}\"/g" "$DEST/pyproject.toml"
    fi
fi

# --- answers record --------------------------------------------------------
sed -i "s/structlog/${LOG_LIB}/" "$DEST/.copier-answers.yml" 2>/dev/null || true

say "done: $DEST"
echo "next: cd $DEST && git init && git add -A"
