Title: Hook environment installs into the shared store are not protected by a cross-process lock (races under parallel CI)

> Note for our own tracking: this one targets **pre-commit** (pre-commit/pre-commit),
> not copier — filed here because the diagnosis was done for this repository's
> flaky test. Draft below.

## Summary

pre-commit protects store *repo clones* with an `flock` (`exclusive_lock`), but hook **environment installs** (`py_env-*` / nodeenv / etc. inside the shared store) have no cross-process lock. When many pre-commit processes run in parallel against the same `PRE_COMMIT_HOME` — e.g. pytest-xdist with one worker per generated project, or matrix CI shards sharing a cached store — a cold window (right after a hook `rev:` bump, or after cache cleanup) makes every process rebuild the same hook environment simultaneously. They rmtree and reinstall the same `py_env-*` path concurrently, and one of them fails on a partial install (`ENOTEMPTY`, "binary not found", truncated venv) — a rare, unreproducible-looking flake.

## Current behavior (v3.x, `pre_commit/repository.py`)

- `_hook_install` (repository.py:81-87): `if os.path.exists(venv): rmtree(venv)` followed by the install, with no `exclusive_lock` around it.
- `installed()` (repository.py:46-62): evaluated per-process, so a stale/partial install by one process is not seen by others in time.

## Reproduction sketch

1. Put a repo with a remote hook (e.g. `typos`, `conventional-pre-commit`) under a shared `PRE_COMMIT_HOME`.
2. Bump the hook's `rev:` to a new SHA (forcing a cold env).
3. Launch N (say 32) `pre-commit run` processes in parallel against the same store.
4. Observe intermittent install failures in one or more processes.

## Expected behavior

Hook environment creation should hold the same kind of per-environment lock the clone step already uses (e.g. `exclusive_lock` around the rmtree+install, keyed by the env directory), so parallel processes wait instead of racing. Alternatively, install into a temp dir and atomically `os.replace` it into place.

## Environment

pre-commit 4.x-line behavior inspected from `pre_commit/repository.py` (2026-09); observed as a one-off flake in a copier template test suite running `-n auto` (~32 workers), solo re-run always green.
