#!/usr/bin/env python3
"""Render-loop surface: render, diff two renders, lint a render, run a batch.

Responsibility: the tools that render the real template -- `render_project`
(one render plus an optional manifest comparison and an optional install),
`render_diff` (two renders compared file by file), `lint_render` (one render
plus the generated project's own ruff), `list_batch_requests` / `run_batch`
(the batch verdict loop) -- plus the small helpers each one narrows to
(`_validate_diff_target`, `_render_and_prepare`,
`_build_rendered_files_inventory`, `_manifest_diff`, `_lint_checks`). The
 render itself and the byte comparison live in `architekton/mcp_render.py`; this
module owns only the tool shapes around them.
"""

# WHYNOT: the functions below are registered through @mcp_interface.tool(server)
# inside register_*(); their call edge is the decorator, invisible to
# the checker.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import hashlib
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))
from architekton import batch  # noqa: E402
from architekton import detect  # noqa: E402
from architekton import mcp_interface  # noqa: E402
from architekton import mcp_render  # noqa: E402
from architekton import suggest  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402


def validate_diff_target(diff_against: str | None) -> Path | None:
    """Resolve and validate the optional diff-against directory."""
    if not diff_against:
        return None
    previous = Path(diff_against).resolve()
    if not previous.is_dir():
        msg = f"diff_against is not a directory: {diff_against}"
        raise ToolError(msg)
    return previous


def render_and_prepare(answers: dict[str, Any], work: Path, *, prepare: bool) -> None:
    """Render template into work directory and optionally execute prepare_environment."""
    mcp_render.render_into(answers, work)
    if not prepare:
        return
    with batch.report_stream_only():
        checks = [batch.prepare_environment(work, "render")]
    failed = [check for check in checks if not check.ok]
    if failed:
        msg = f"render succeeded but prepare failed: {failed[0].detail}"
        raise ToolError(msg)


def refuse_invalid(answers: dict[str, Any]) -> None:
    """Raise validate_answers' errors as one tool error the caller can act on."""
    with batch.report_stream_only():
        verdict = suggest.validate_answers(dict(answers))
    if verdict.ok:
        return
    reasons = "; ".join(f"{error['question']}: {error['reason']}" for error in verdict.errors)
    msg = f"answers rejected, nothing rendered; fix each and call again -- {reasons}"
    raise ToolError(msg)


def refuse_occupied(dest: Path) -> None:
    """A render only fills a missing or empty directory; anything else has its own tool."""
    try:
        mode = detect.detect_mode(dest)
    except detect.DetectError as exc:
        raise ToolError(str(exc)) from exc
    if mode != "fresh":
        msg = f"dest {dest} is not empty (mode {mode!r}); call {mcp_interface.next_for_mode(mode)}"
        raise ToolError(msg)


def build_rendered_files_inventory(rendered: dict[str, Path]) -> tuple[list[dict[str, str]], list[str]]:
    """Build list of {path, sha256} records and sorted top-level directory names."""
    files = [
        {"path": name, "sha256": hashlib.sha256(body.read_bytes()).hexdigest()}
        for name, body in sorted(rendered.items())
    ]
    top_level = sorted({entry["path"].split("/")[0] for entry in files})
    return files, top_level


def manifest_diff(target: Path, rendered: dict[str, Path]) -> dict[str, Any]:
    """Manifest comparison of a previous render's directory and this render.

    The `render_diff` shape narrowed to what "render again and diff against
    the tree I already have" needs: `a` is the diff target, `b` this render,
    files equal under the stamp-masked comparison count as `same_count`, and
    the changed entries carry both sides' digests of the compared bytes. Only
    paths present on both sides can differ -- one-sided paths are listed as
    `only_in_a` / `only_in_b`, never as changes.
    """
    tree_a = mcp_render.tree(target)
    changed: list[dict[str, Any]] = []
    same = 0
    for name in sorted(set(tree_a) & set(rendered)):
        body_a, body_b = mcp_render.compared(tree_a[name], name), mcp_render.compared(rendered[name], name)
        if body_a == body_b:
            same += 1
        else:
            changed.append(
                {
                    "path": name,
                    "sha256_a": hashlib.sha256(body_a).hexdigest(),
                    "sha256_b": hashlib.sha256(body_b).hexdigest(),
                }
            )
    return {
        "same_count": same,
        "changed": changed,
        "only_in_a": sorted(set(tree_a) - set(rendered)),
        "only_in_b": sorted(set(rendered) - set(tree_a)),
    }


def lint_checks(dest: Path) -> list[batch.Check]:
    """The ruff verdicts for a rendered tree (the machinery lives in batch.ruff_checks)."""
    return batch.ruff_checks(dest)


def register_render_loop(server: Any) -> None:  # noqa: C901  -- registers render_project, then delegates to the batch and diff helpers below.
    """Register the render-loop tools on `server`."""

    @mcp_interface.tool(server)
    def render_project(
        answers: dict[str, Any],
        *,
        dest: str | None = None,
        prepare: bool = False,
        diff_against: str | None = None,
        validate: bool = True,
    ) -> dict[str, Any]:
        """Generate a new project from `answers` (inspect_project mode `fresh`).

        Unset questions take their defaults. The answers are validated first;
        an invalid set is refused with validate_answers' errors (`validate=False`
        skips that, for forcing a combination on purpose). `dest` must be
        missing or empty (default: a new temporary directory).
        `prepare=True` also installs the project's environment. `diff_against`
        names a previous render to compare with. Returns dest, file_count,
        top_level, files ({path, sha256}) and, with diff_against, diff
        (same_count, changed, only_in_a, only_in_b). Cost: one render; network
        for the post-generation tasks and for `prepare`.
        """
        previous = validate_diff_target(diff_against)
        if validate:
            refuse_invalid(answers)
        if dest:
            refuse_occupied(Path(dest).resolve())
        work = Path(dest).resolve() if dest else Path(tempfile.mkdtemp(prefix="mcp-render-"))
        work.mkdir(parents=True, exist_ok=True)
        render_and_prepare(answers, work, prepare=prepare)
        rendered = mcp_render.tree(work)
        files, top_level = build_rendered_files_inventory(rendered)
        payload: dict[str, Any] = {
            "dest": str(work),
            "file_count": len(files),
            "files": files,
            "top_level": top_level,
        }
        if previous is not None:
            payload["diff"] = manifest_diff(previous, rendered)
        return payload

    _register_batch_tools(server)


def _register_batch_tools(server: Any) -> None:  # noqa: C901  -- two batch tools; the bodies are the pre-split implementations.
    """Register the batch listing/runner tools on `server`."""

    @mcp_interface.tool(server)
    def list_batch_requests(jsonl: str) -> dict[str, Any]:
        """The requests in a batch file (docs/how-to/batch.md), without running them.

        Returns {"count", "requests"}: each id, note, dest, has_update and the
        number of checks, so `run_batch(only=...)` can pick some.
        Cost: filesystem only.
        """
        try:
            requests = batch.load_requests([Path(jsonl)])
        except (batch.SpecError, OSError) as exc:
            msg = f"cannot read {jsonl}: {exc}"
            raise ToolError(msg) from exc
        listed = [
            {
                "id": request.id,
                "note": request.note,
                "dest": request.dest,
                "has_update": request.update is not None,
                "checks": len(request.commands),
            }
            for request in requests
        ]
        return {"count": len(listed), "requests": listed}

    @mcp_interface.tool(server)
    def run_batch(
        jsonl: str, *, only: str | None = None, prepare: bool = False, keep: bool = False, jobs: int = 1
    ) -> dict[str, Any]:
        """Run a batch file's requests and return the verdict.

        `only` is a regular expression over request ids; `jobs` renders in
        parallel; `prepare=True` installs each project; `keep=True` keeps the
        renders. Returns ok (every selected line passed), work and lines
        (each with checks {name, ok, detail}). Cost: one render per line;
        network with `prepare`.
        """
        try:
            requests = batch.load_requests([Path(jsonl)])
        except (batch.SpecError, OSError) as exc:
            msg = f"cannot read {jsonl}: {exc}"
            raise ToolError(msg) from exc
        if only:
            pattern = re.compile(only)
            requests = [request for request in requests if pattern.search(request.id)]
            if not requests:
                msg = f"no request id matches {only!r}"
                raise ToolError(msg)

        work = Path(tempfile.mkdtemp(prefix="mcp-batch-"))
        with batch.report_stream_only():
            results = batch.run_requests(requests, work, TOP, jobs=jobs, prepare=prepare)
        return {
            "ok": all(result.ok for result in results),
            "work": str(work) if keep else None,
            "lines": [result.as_dict() for result in results],
        }

    _register_diff_tools(server)


def _register_diff_tools(server: Any) -> None:  # noqa: C901  -- two comparison tools; the bodies are the pre-split implementations.
    """Register the render-comparison tools on `server`."""

    @mcp_interface.tool(server)
    def render_diff(answers_a: dict[str, Any], answers_b: dict[str, Any], *, keep: bool = False) -> dict[str, Any]:
        """Render two answer sets and compare the trees file by file.

        Returns identical, file_count, identical_count, changed_count,
        only_in_a / only_in_b, answers_commit and changed (per differing file:
        sizes, sha256 digests and a unified diff, capped). Copier's per-render
        stamp in .copier-answers.yml is ignored. `keep=True` keeps both renders.
        Cost: two renders, no install.
        """
        work = Path(tempfile.mkdtemp(prefix="mcp-diff-"))
        first, second = work / "a", work / "b"
        for dest, answers in ((first, answers_a), (second, answers_b)):
            dest.mkdir(parents=True, exist_ok=True)
            mcp_render.render_into(answers, dest)

        tree_a, tree_b = mcp_render.tree(first), mcp_render.tree(second)
        only_in_a = sorted(set(tree_a) - set(tree_b))
        only_in_b = sorted(set(tree_b) - set(tree_a))
        identical, changed = mcp_render.compare_shared_files(tree_a, tree_b)
        return {
            "identical": not (only_in_a or only_in_b or changed),
            "dest_a": str(first) if keep else None,
            "dest_b": str(second) if keep else None,
            "file_count": {"a": len(tree_a), "b": len(tree_b)},
            "identical_count": identical,
            "changed_count": len(changed),
            "changed": changed,
            "only_in_a": only_in_a,
            "only_in_b": only_in_b,
            "answers_commit": {
                "a": mcp_render.checkout_stamp(tree_a[batch.ANSWERS_FILE]) if batch.ANSWERS_FILE in tree_a else None,
                "b": mcp_render.checkout_stamp(tree_b[batch.ANSWERS_FILE]) if batch.ANSWERS_FILE in tree_b else None,
            },
        }

    @mcp_interface.tool(server)
    def lint_render(answers: dict[str, Any]) -> dict[str, Any]:
        """Render `answers` and run the generated project's ruff format and ruff check.

        Returns checked (false when the render has no Python or no ruff
        config, with `note`), ok, dest, seconds, error and checks
        ({name, ok, detail}). Cost: one render plus two ruff runs, no venv.
        """
        work = Path(tempfile.mkdtemp(prefix="mcp-lint-"))
        work.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        mcp_render.render_into(answers, work)
        checks = lint_checks(work)
        note = "" if checks else "no Python or no [tool.ruff] section in the render; nothing to lint"
        result = batch.LineResult(
            id="lint_render", index=0, checks=checks, seconds=time.monotonic() - started, dest=str(work), note=note
        )
        return {**result.as_dict(), "checked": bool(checks)}
