#!/usr/bin/env python3
"""Project surface: inspection, checkout status, adoption.

Responsibility: the tools that look at a project on disk or at this checkout
-- `inspect_project` (what the target has, which operation fits),
`template_status` (this checkout's own git + questionnaire state),
`adopt_project` (the transactional adoption) -- plus the one helper
(`_run_adoption`) that executes `adopt.adopt` inside stream isolation with
error conversion. Ethics matching lives in the `daimonion` linter, not here.
"""

# WHYNOT: the functions below are registered through @mcp_interface.tool(server)
# inside register_*(); their call edge is the decorator, invisible to
# the checker.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any
from typing import Literal

import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from architekton import adopt_run  # noqa: E402
from architekton import adopt_types  # noqa: E402
from architekton import batch  # noqa: E402
from architekton import detect  # noqa: E402
from architekton import mcp_interface  # noqa: E402
from architekton import questionnaire  # noqa: E402
from architekton.mcp_shared import repo_root  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402


def run_adoption(
    target_dir: Path,
    ref: str | None,
    answers: dict[str, Any] | None,
    *,
    dry_run: bool,
    merge: bool,
) -> adopt_types.Adoption:
    """Execute the adoption transaction wrapped in stream isolation and tool error conversion."""
    if not target_dir.is_dir():
        msg = f"not a directory: {target_dir}"
        raise ToolError(msg)
    try:
        with batch.report_stream_only():
            return adopt_run.adopt(
                target_dir,
                ref=ref,
                answers=answers or {},
                dry_run=dry_run,
                merge_generated=merge,
            )
    except adopt_types.OwnershipError as exc:
        raise ToolError(str(exc)) from exc
    except (adopt_types.AdoptError, OSError) as exc:
        raise ToolError(str(exc)) from exc


def run_update(
    target: Path, ref: str | None, answers: dict[str, Any] | None, *, dry_run: bool, conflict: str
) -> dict[str, Any]:
    """Update `target` (or, for a dry run, a throwaway clone of it) and report what changed."""
    try:
        mode = detect.detect_mode(target)
    except detect.DetectError as exc:
        raise ToolError(str(exc)) from exc
    if mode != "update":
        msg = f"{target} is mode {mode!r}, not 'update'; call {mcp_interface.next_for_mode(mode)}"
        raise ToolError(msg)
    # copier update reads `.copier-answers.yml` -- not whichever answers file
    # made detect_mode say "update" -- and runs that template's tasks.
    recorded = _recorded_src(target)
    if recorded is None or not detect.src_is_trusted_for_update(recorded, repo_root()):
        msg = (
            f"{target}/.copier-answers.yml records the template source {recorded!r}, which is not this "
            "template's upstream URL or this checkout; refusing to run its tasks. Check it with the user."
        )
        raise ToolError(msg)
    status = batch.git(target, "status", "--porcelain")
    if status.returncode != 0:
        msg = f"{target} is not a git repository: copier updates only committed projects; commit it first"
        raise ToolError(msg)
    if status.stdout.strip():
        msg = (
            f"{target} has uncommitted changes; commit or stash them first (the update merges against the last commit)"
        )
        raise ToolError(msg)
    where = target
    if dry_run:
        where = Path(tempfile.mkdtemp(prefix="mcp-update-")) / target.name
        cloned = batch.git(target.parent, "clone", "--quiet", str(target), str(where))
        if cloned.returncode != 0:
            msg = f"cannot clone {target} for the dry run: {cloned.stderr.strip()}"
            raise ToolError(msg)
    from_commit = _recorded_commit(where)
    try:
        with batch.report_stream_only():
            batch.update(where, dict(answers or {}), ref, conflict="rej" if conflict == "rej" else "inline")
    except Exception as exc:  # noqa: BLE001  WHYNOT: the tool must report copier's refusal, not crash the session.
        msg = f"update failed: {type(exc).__name__}: {exc}"
        raise ToolError(msg) from exc
    changed = batch.git(where, "status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
    conflicts = batch.conflict_residue(where)
    return {
        "applied": not dry_run,
        "path": str(target),
        "work": str(where) if dry_run else None,
        "from_commit": from_commit,
        "to_commit": _recorded_commit(where),
        "changed": [{"path": line[3:], "status": line[:2].strip()} for line in changed if line.strip()],
        "conflicts": conflicts,
        "next": _after_update(dry_run=dry_run, conflicts=bool(conflicts)),
    }


def _after_update(*, dry_run: bool, conflicts: bool) -> str:
    """What the agent does after an update_project call."""
    if dry_run:
        return "show the user `changed` and `conflicts`, then call again with dry_run=False"
    if conflicts:
        return "resolve the conflicts, then commit"
    return "review `git diff`, run the project's checks, then commit"


def _recorded_src(project: Path) -> str | None:
    """The `_src_path` in the answers file copier update reads."""
    try:
        data = yaml.safe_load((project / batch.ANSWERS_FILE).read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None
    src = data.get("_src_path") if isinstance(data, dict) else None
    return src if isinstance(src, str) else None


def _recorded_commit(project: Path) -> str | None:
    """The template revision the project's .copier-answers.yml records."""
    for answers in sorted(project.glob(".copier-answers*.yml")):
        try:
            data = yaml.safe_load(answers.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError):
            continue
        if isinstance(data, dict) and data.get("_commit"):
            return str(data["_commit"])
    return None


def register_project(server: Any) -> None:
    """Register the project tools on `server`."""

    @mcp_interface.tool(server)
    def inspect_project(path: str, *, takeover: bool = False) -> dict[str, Any]:
        """What a directory already holds, and which generate tool fits it.

        Returns `mode` (fresh / adopt / update / foreign), `next` (the tool to
        call for that mode), the facts found, `collisions` (files a render would
        overwrite) and `suggested_answers`. `foreign` is refused unless
        `takeover=True`; ask the user first. Cost: filesystem only.
        """
        try:
            detection = detect.detect(Path(path).resolve(), takeover=takeover)
        except (detect.DetectError, OSError) as exc:
            raise ToolError(str(exc)) from exc
        return {**detection.as_dict(), "next": mcp_interface.next_for_mode(detection.mode)}

    @mcp_interface.tool(server)
    def template_status() -> dict[str, Any]:
        """Which template revision a render would use, and whether the checkout is dirty.

        Returns repo, template_dir, question counts, latest_tag, head,
        commits_behind_latest_tag and dirty (uncommitted template changes are
        included in renders from this checkout). Cost: git and filesystem, ~50 ms.
        """
        top = repo_root()
        describe = batch.git(top, "describe", "--tags", "--abbrev=0").stdout.strip()
        head = batch.git(top, "rev-parse", "--short", "HEAD").stdout.strip()
        behind = batch.git(
            top, *(["rev-list", "--count", f"{describe}..HEAD"] if describe else ["--version"])
        ).stdout.strip()
        total, asked_total, setting_names = questionnaire.counts()
        return {
            "repo": str(top),
            "template_dir": str(detect.TEMPLATE_DIR),
            "questions": total,
            "asked_questions": asked_total,
            "settings": setting_names,
            "latest_tag": describe or None,
            "head": head or None,
            "commits_behind_latest_tag": int(behind) if behind.isdigit() else None,
            "dirty": bool(batch.git(top, "status", "--porcelain").stdout.strip()),
        }

    @mcp_interface.tool(server)
    def adopt_project(
        path: str,
        *,
        ref: str | None = None,
        answers: dict[str, Any] | None = None,
        dry_run: bool = True,
        merge: bool = True,
    ) -> dict[str, Any]:
        """Add the template to an existing project it did not make (inspect_project mode `adopt`).

        `dry_run=True` (default) writes nothing and returns the plan; call it
        first, show the user, then call again with `dry_run=False`. Existing
        files are never overwritten (`skip`); with `merge=True` (default)
        dependencies, tool settings, .gitignore patterns and recipes are added
        to the files the project has, never rewriting a value. A failed run is
        rolled back. `answers` overrides what inspect_project suggested.
        Returns ok, applied, created_count, skip, ref, ref_reason,
        merged_dependencies, merged_tool_config. Cost: one render; network for
        the template's post-generation tasks.
        """
        result = run_adoption(Path(path).resolve(), ref, answers, dry_run=dry_run, merge=merge)
        if not result.ok:
            msg = f"adoption failed and was rolled back: {result.error}"
            raise ToolError(msg)
        return result.as_dict()

    @mcp_interface.tool(server)
    def update_project(
        path: str,
        *,
        ref: str | None = None,
        answers: dict[str, Any] | None = None,
        dry_run: bool = True,
        conflict: Literal["inline", "rej"] = "inline",
    ) -> dict[str, Any]:
        """Update a project this template made to a newer template revision (mode `update`).

        The project must be a git repository with no uncommitted changes.
        `dry_run=True` (default) updates a throwaway clone and returns what would
        change; call it first, show the user, then call with `dry_run=False` to
        update the project itself (undo with git). `ref` is the template
        revision (default: the newest release); `answers` changes answers on the
        way. Returns applied, from_commit, to_commit, changed ({path, status}),
        conflicts (files with conflict markers or .rej hunks: resolve them before
        committing) and next. Cost: one update render; network to fetch the
        template.
        """
        return run_update(Path(path).resolve(), ref, answers, dry_run=dry_run, conflict=conflict)
