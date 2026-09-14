#!/usr/bin/env python3
"""MCP server exposing this template's own tooling to an agent.

`tools/batch.py`, `tools/detect.py` and `tools/questionnaire.py` are already
the machine-readable layer over this repository; this server is how an MCP
host (Claude Desktop, an IDE agent, the MCP Inspector) calls them instead of
shelling out and parsing text.

Run it over stdio (how an MCP host launches a server):

    uv run python tools/mcp_server.py

Or serve it over HTTP, for a host that connects to a URL:

    uv run python tools/mcp_server.py --transport streamable-http

Debug it with the MCP Inspector:

    uv run mcp dev tools/mcp_server.py

Editing this repository needs no setup: the root `.mcp.json` registers the
stdio command below (the same one `task mcp` runs), and
docs/how-to/mcp-tools.md is the one-page tour of the tools.

Binding to a non-local address (--host 0.0.0.0) requires MCP_ALLOWED_HOSTS:
the SDK arms its DNS-rebinding protection only while the server binds to
localhost, so a publicly bound server would accept any Host header without an
explicit allowlist. This server refuses to start in that state. GET /health is
the liveness probe for an orchestrator; like every SDK custom route it is
unauthenticated and bypasses the host allowlist, and exposes no data.
tests/test_mcp_server.py runs the real server and pins both halves: a foreign
Host gets 421 on /mcp, and /health stays 200.

Two protocol facts shape the implementation:

- **stdout belongs to the protocol.** Copier prints progress to stdout, so
  every render here runs inside `batch.report_stream_only()` (fd 1 redirected
  to stderr). A stray print would corrupt the session.
- **Tools are the contract.** Each docstring below is what the model reads to
  decide when to call it, so they state the cost (rendering, installing,
  network) and what is returned.
  tests/test_mcp_server.py fails when a tool's docstring stops saying both.

The generated scaffold's MCP server (`_shared/mcp_server.py.jinja`, rendered
into a `cli` / `web_api` project when `include_mcp` is on) is a **separate
server on purpose**. That one is the worked example a generated project
starts from -- typed tools, a `ToolError`, resources, a prompt, the
`mcp-server-<name>` console script -- while this one serves the template's
maintenance loop: render, inspect, adopt, verdict a batch, list witnesses.
They share no code and import nothing from each other, because a generated
project must never depend on this repository. The single idea that appears in
both is the MCP_ALLOWED_HOSTS rule plus /health, ~30 lines of SDK glue
re-derived from the SDK API in each; keeping the second copy is what lets
either side change its transport settings without a release coupling. Fix a
generated server in the scaffold, fix a template tool here -- see
docs/how-to/mcp-tools.md.

None of these tools guess the questionnaire: the shape questions
(`project_type`, `include_*`, ...) stay the caller's decision, per
notes/SPEC-adoption.md section 12.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import Literal
from typing import cast

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from mcp.server import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402
from tools import adopt  # noqa: E402
from tools import batch  # noqa: E402
from tools import detect  # noqa: E402
from tools import gen_docs  # noqa: E402
from tools import questionnaire  # noqa: E402
from tools.render_inputs import RENDER_INPUT_DIRS  # noqa: E402
from tools.render_inputs import RENDER_INPUT_FILES  # noqa: E402
from tools.render_inputs import render_fingerprint  # noqa: E402

GIT = batch.GIT
OUTPUT_LIMIT = batch.OUTPUT_LIMIT
server = MCPServer("python-copier-template")

__all__ = ["main", "server"]


@server.tool()
def list_questions(*, asked_only: bool = True) -> dict[str, Any]:
    """List this template's questionnaire in ask order.

    Returns {"count", "questions"}; each entry has name, type, default (as written -- defaults are Jinja
    expressions), when, help, choices and source file. `internal` marks the
    derived `when: false` variables, which `asked_only=True` (the default)
    excludes. Call this before `render_project`: it is the only way to know
    which answers are valid and what each question defaults to. Two questions
    (`package_manager`, `oj_kind`) carry a `choices_template` instead of a
    resolved list, because their choices narrow themselves from earlier
    answers.
    """
    questions, _settings = questionnaire.load_questions()
    selected = [question.as_dict() for question in questions if not (asked_only and question.internal)]
    return {"count": len(selected), "questions": selected}


@server.tool()
def inspect_project(path: str, *, takeover: bool = False) -> dict[str, Any]:
    """Report what a project already has, and which operation fits it.

    Returns `mode` (fresh / adopt / update / foreign), the facts found on
    disk, the template outputs that would overwrite existing files
    (`collisions`), and `suggested_answers` for a copy or an adoption.

    Read `mode` before rendering anything: `update` means this project was
    already generated by this template (run `copier update`, not a copy),
    `foreign` means another template owns it and the call is refused unless
    `takeover=True`. Filesystem only -- no render, no network.
    """
    try:
        detection = detect.detect(Path(path).resolve(), takeover=takeover)
    except (detect.DetectError, OSError) as exc:
        raise ToolError(str(exc)) from exc
    return detection.as_dict()


@server.tool()
def template_status() -> dict[str, Any]:
    """Report this template checkout's own state.

    Returns `repo`, `template_dir`, the question counts, `latest_tag`, `head`,
    `commits_behind_latest_tag` and `dirty`. `latest_tag` and `head` come from
    git. The fork tags its own releases
    since the 6.0.0 detach, so `copier copy` without `--vcs-ref` expands the
    newest release tag; `commits_behind_latest_tag` says how far that tag
    trails the working tree, which is what an explicit ref (or the local
    `--ref HEAD` render) exists for. `dirty` means uncommitted template
    changes are included in any render done from this checkout.

    Reads git and the questionnaire only -- no render, no network (~50 ms),
    so it is the cheap first call.
    """
    describe = batch.git(TOP, "describe", "--tags", "--abbrev=0").stdout.strip()
    head = batch.git(TOP, "rev-parse", "--short", "HEAD").stdout.strip()
    behind = batch.git(
        TOP, *(["rev-list", "--count", f"{describe}..HEAD"] if describe else ["--version"])
    ).stdout.strip()
    questions, settings = questionnaire.load_questions()
    return {
        "repo": str(TOP),
        "template_dir": str(detect.TEMPLATE_DIR),
        "questions": len(questions),
        "asked_questions": sum(1 for question in questions if not question.internal),
        "settings": sorted(settings),
        "latest_tag": describe or None,
        "head": head or None,
        "commits_behind_latest_tag": int(behind) if behind.isdigit() else None,
        "dirty": bool(batch.git(TOP, "status", "--porcelain").stdout.strip()),
    }


@server.tool()
def adopt_project(
    path: str,
    *,
    ref: str | None = None,
    answers: dict[str, Any] | None = None,
    dry_run: bool = True,
    merge: bool = True,
) -> dict[str, Any]:
    """Adopt the template into an existing project, transactionally.

    Returns `ok`, `applied`, `created_count`, `skip` (existing files left
    alone), `ref` and `ref_reason`, the added `deps`, the `tool_config` merge
    and `error` when the run was rolled back.

    `dry_run=True` (the default) only plans: nothing is written, and the
    result reports which existing files would be left alone (`skip`), which
    revision would be expanded (`ref`, `ref_reason`), what would be added, and
    which dependencies `deps` would add to the project's pyproject.toml. Call
    it first.

    `merge` (default true) adds what the template generated to the files the
    project already has, always additively: dependencies and `[tool.*]` keys
    in pyproject.toml (an existing value is never rewritten — a difference
    lands in `deps.differing` / `tool_config.kept`, and a value that names
    *this* project, like `src/<pkg>`, is reported in
    `tool_config.needs_your_value` instead of copied), missing `.gitignore`
    patterns, missing Makefile/justfile recipes, and the template's
    read-only CI as a second `copier-ci.yml` when `ci.yml` is taken. Pass
    false to touch nothing but the render.

    With `dry_run=False` the adoption is verified: if any existing file
    changed or disappeared -- a collision the plan did not cover -- the run is
    rolled back (originals restored, everything it created deleted) and
    `error` says why, so a failed adoption leaves the project exactly as it
    was. `ref` defaults to the latest tag *only* when that tag carries this
    questionnaire, otherwise the default branch; `answers` overrides what
    `inspect_project` derived. Files under `skip` are never written over, and
    everything the project does not have yet is still added.
    """
    if not Path(path).is_dir():
        msg = f"not a directory: {path}"
        raise ToolError(msg)
    try:
        with batch.report_stream_only():
            result = adopt.adopt(
                Path(path).resolve(),
                ref=ref,
                answers=answers or {},
                dry_run=dry_run,
                merge_generated=merge,
            )
    except adopt.OwnershipError as exc:
        raise ToolError(str(exc)) from exc
    except (adopt.AdoptError, OSError) as exc:
        raise ToolError(str(exc)) from exc
    if not result.ok:
        msg = f"adoption failed and was rolled back: {result.error}"
        raise ToolError(msg)
    return result.as_dict()


@server.tool()
def render_project(answers: dict[str, Any], *, dest: str | None = None, prepare: bool = False) -> dict[str, Any]:
    """Render the template with `answers` and report what it produced.

    `answers` are the copier answers; unset questions fall back to their
    defaults (this is `--defaults`), so usually only `project_type` and the
    Project Details are needed. The render happens from this checkout, so
    uncommitted template changes are included -- run `inspect_project` first
    if the target may be an existing project.

    `dest` defaults to a fresh temporary directory. `prepare=True` also runs
    the project's install command (`uv sync` / `pixi install` / `poetry
    install`, chosen from what was rendered), which needs the network on a
    cold cache. Returns the destination path, the file count and the paths
    (relative) so a caller can read the files it needs.
    """
    work = Path(dest).resolve() if dest else Path(tempfile.mkdtemp(prefix="mcp-render-"))
    work.mkdir(parents=True, exist_ok=True)
    _render_into(answers, work)
    with batch.report_stream_only():
        checks = [batch.prepare_environment(work, "render")] if prepare else []
    failed = [check for check in checks if not check.ok]
    if failed:
        msg = f"render succeeded but prepare failed: {failed[0].detail}"
        raise ToolError(msg)
    files = sorted(str(path.relative_to(work)) for path in work.rglob("*") if path.is_file())
    return {
        "dest": str(work),
        "file_count": len(files),
        "files": files,
        "top_level": sorted({name.split("/")[0] for name in files}),
    }


@server.tool()
def list_batch_requests(jsonl: str) -> dict[str, Any]:
    """List the requests in a batch file (see docs/how-to/batch.md).

    Returns {"count", "requests"}: each request's id, note, destination and
    whether it carries an `update` phase, so a caller can pick one to run
    instead of running all of them. Filesystem only -- no render, no network,
    while `run_batch` on the same file renders every request it selects. A
    malformed request list raises rather than returning a partial listing.
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


@server.tool()
def run_batch(jsonl: str, *, only: str | None = None, prepare: bool = False, keep: bool = False) -> dict[str, Any]:
    """Run a batch of generation requests and return the verdict.

    `jsonl` is a request list (docs/how-to/batch.md); `only` is a regular
    expression selecting ids. Each line renders with the real template, runs
    its commands and judges its `expect` block, so this is the "did the
    change break a combination" check. `ok` is true only when every selected
    line passed; `lines[].checks[].detail` carries the observed value for a
    failure. Renders are real (uncommitted template changes included) and
    `prepare=True` additionally installs each project (network on a cold
    cache). `keep=True` leaves the rendered projects on disk and reports
    their directory.
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
        results = [batch.run_request(request, work, TOP, prepare=prepare) for request in requests]
    return {
        "ok": all(result.ok for result in results),
        "work": str(work) if keep else None,
        "lines": [result.as_dict() for result in results],
    }


# --------------------------------------------------------------------------- #
# the render loop: one render helper, three tools
# --------------------------------------------------------------------------- #


def _render_into(answers: dict[str, Any], dest: Path) -> None:
    """Render this checkout into `dest`, with copier's chatter on stderr.

    The single render entry point of every tool here: stdout is the MCP
    protocol channel, so a stray byte of copier progress would corrupt the
    session (`batch.report_stream_only()` moves fd 1 to stderr).
    """
    try:
        with batch.report_stream_only():
            batch.render(str(TOP), dest, answers)
    except Exception as exc:  # noqa: BLE001  WHYNOT: the tool must report, not crash the session.
        msg = f"render failed: {type(exc).__name__}: {exc}"
        raise ToolError(msg) from exc


def _tree(root: Path) -> dict[str, Path]:
    """Every file under `root`, keyed by its POSIX relative path."""
    return {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_file()}


DIFF_LINES = 40
"""Unified-diff lines kept per changed file (the byte comparison is not truncated)."""
DIFF_FILE_LIMIT = 25
"""Changed files that carry a diff; beyond it the entry keeps its digests and sizes."""
ANSWERS_FILE = ".copier-answers.yml"
"""Where copier records the answers -- and the checkout it rendered from."""
CHECKOUT_STAMP = re.compile(rb"^_commit:.*$", re.MULTILINE)
"""Copier's stamp of the template revision the render came from."""


def _compared(path: Path, name: str) -> bytes:
    """The bytes to compare for `name`, with copier's checkout stamp normalized.

    `.copier-answers.yml` records `_commit`, and for a *dirty* template that is
    a synthetic commit copier creates per render: its sha changes between two
    renders of identical answers, so comparing it as-is would report every
    comparison of a working tree as different. The stamp is reported separately
    (`answers_commit`) instead, and every other byte is compared as it is.
    """
    body = path.read_bytes()
    return CHECKOUT_STAMP.sub(b"_commit: <checkout>", body) if name == ANSWERS_FILE else body


def _checkout_stamp(path: Path) -> str | None:
    """The `_commit` value copier wrote, or None when the file has no stamp."""
    match = re.search(rb"^_commit:\s*(\S+)", path.read_bytes(), re.MULTILINE)
    return match.group(1).decode() if match else None


def _unified(name: str, path_a: Path, path_b: Path) -> tuple[str, bool]:
    """A bounded unified diff of one path between two renders."""
    try:
        lines_a = _compared(path_a, name).decode().splitlines()
        lines_b = _compared(path_b, name).decode().splitlines()
    except UnicodeDecodeError:
        return (f"{name}: binary or not UTF-8; {path_a.stat().st_size} -> {path_b.stat().st_size} bytes", False)
    diff = list(difflib.unified_diff(lines_a, lines_b, f"a/{name}", f"b/{name}", lineterm="", n=1))
    return "\n".join(diff[:DIFF_LINES]), len(diff) > DIFF_LINES


@server.tool()
def render_diff(answers_a: dict[str, Any], answers_b: dict[str, Any], *, keep: bool = False) -> dict[str, Any]:
    """Render `answers_a` and `answers_b` and compare the two trees file by file.

    Returns `identical` (every path exists on both sides with the same bytes),
    `file_count` and `identical_count`, `only_in_a` / `only_in_b` (paths on one
    side only), `answers_commit` (the `_commit` copier recorded in
    `.copier-answers.yml` on each side) and `changed`: one entry per path
    present on both sides with different bytes, carrying `bytes_a` / `bytes_b`
    / `sha256_a` / `sha256_b` and a `diff` (unified, at most 40 lines, first 25
    changed files, with `diff_truncated` when it was cut). Files that match are
    counted, not listed. Answer sets fall back to their defaults like
    `render_project`.

    `.copier-answers.yml` is compared with that `_commit` stamp normalized: for
    a dirty template copier stamps a synthetic commit it creates per render, so
    the raw file differs between two renders of *identical* answers -- the one
    difference that says nothing about the answers. Everything else is byte
    for byte.

    Two renders, no install, no network: this is the "did my change alter an
    unrelated combination" check, and the one-call form of the audit's manual
    comparison of 1684 rendered files. `keep=True` leaves both renders on disk
    and reports their directories.
    """
    work = Path(tempfile.mkdtemp(prefix="mcp-diff-"))
    first, second = work / "a", work / "b"
    for dest, answers in ((first, answers_a), (second, answers_b)):
        dest.mkdir(parents=True, exist_ok=True)
        _render_into(answers, dest)

    tree_a, tree_b = _tree(first), _tree(second)
    only_in_a = sorted(set(tree_a) - set(tree_b))
    only_in_b = sorted(set(tree_b) - set(tree_a))
    changed: list[dict[str, Any]] = []
    identical = 0
    for name in sorted(set(tree_a) & set(tree_b)):
        path_a, path_b = tree_a[name], tree_b[name]
        body_a, body_b = _compared(path_a, name), _compared(path_b, name)
        if body_a == body_b:
            identical += 1
            continue
        text, truncated = _unified(name, path_a, path_b) if len(changed) < DIFF_FILE_LIMIT else ("", False)
        changed.append(
            {
                "path": name,
                "bytes_a": len(body_a),
                "bytes_b": len(body_b),
                "sha256_a": hashlib.sha256(body_a).hexdigest(),
                "sha256_b": hashlib.sha256(body_b).hexdigest(),
                "diff": text,
                "diff_truncated": truncated,
            }
        )
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
            "a": _checkout_stamp(tree_a[ANSWERS_FILE]) if ANSWERS_FILE in tree_a else None,
            "b": _checkout_stamp(tree_b[ANSWERS_FILE]) if ANSWERS_FILE in tree_b else None,
        },
    }


LINT_TIMEOUT = 300
LINT_COMMANDS: tuple[tuple[str, ...], ...] = (("format", "--check"), ("check",))


def _ruff_bin() -> Path:
    """This repository's ruff: the interpreter's own directory, then PATH.

    The rendered project has no environment of its own -- that is the point of
    this tool -- so the lint comes from the venv the server runs in.
    """
    for candidate in (Path(sys.executable).parent / "ruff", TOP / ".venv" / "bin" / "ruff"):
        if candidate.is_file():
            return candidate
    found = shutil.which("ruff")
    if found:
        return Path(found)
    msg = "ruff not found next to the running interpreter or on PATH"
    raise ToolError(msg)


def _lint_checks(dest: Path) -> list[batch.Check]:
    """The ruff verdicts for a rendered tree, or nothing when it cannot be linted.

    Only where the generated lint applies: a leaf whose render ships no Python
    (bare workspaces) or no ``[tool.ruff]`` has nothing for it to judge, which
    is what ``tests/test_generated_lint.py`` assumes too.
    """
    if not any(dest.rglob("*.py")):
        return []
    pyproject = dest / "pyproject.toml"
    if not pyproject.is_file() or "[tool.ruff" not in pyproject.read_text(encoding="utf-8"):
        return []
    ruff = _ruff_bin()
    checks: list[batch.Check] = []
    for args in LINT_COMMANDS:
        proc = subprocess.run(  # noqa: S603  WHYNOT: fixed argv, the render supplies the input.
            [str(ruff), *args, "--no-cache", "."],
            cwd=dest,
            capture_output=True,
            text=True,
            check=False,
            timeout=LINT_TIMEOUT,
        )
        detail = "" if proc.returncode == 0 else (proc.stdout + proc.stderr).strip()[-OUTPUT_LIMIT:]
        checks.append(batch.Check(name=f"ruff {' '.join(args)}", ok=proc.returncode == 0, detail=detail))
    return checks


@server.tool()
def lint_render(answers: dict[str, Any]) -> dict[str, Any]:
    """Render `answers` and lint the result the way the generated project does.

    Runs `ruff format --check` and `ruff check` under the rendered
    `pyproject.toml`, so a template change that renders unformatted or
    unlintable Python fails here instead of later in
    `tests/test_generated_lint.py`. No venv and no network: one render plus two
    ruff runs. The ruff is this checkout's (a rendered project has no
    environment of its own to lint with).

    Returns `checked` -- false when the render ships no Python or no
    `[tool.ruff]` section, in which case `note` says which -- plus the
    `run_batch` verdict shape: `ok`, `dest`, `seconds`, `error` and `checks`
    ({name, ok, detail}, one per ruff command, `detail` carrying ruff's own
    output).
    """
    work = Path(tempfile.mkdtemp(prefix="mcp-lint-"))
    work.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    _render_into(answers, work)
    checks = _lint_checks(work)
    note = "" if checks else "no Python or no [tool.ruff] section in the render; nothing to lint"
    result = batch.LineResult(
        id="lint_render", index=0, checks=checks, seconds=time.monotonic() - started, dest=str(work), note=note
    )
    return {**result.as_dict(), "checked": bool(checks)}


# --------------------------------------------------------------------------- #
# the witness ledger (tests/matrix/, W3 of PLAN-improvements)
# --------------------------------------------------------------------------- #

WITNESS_LIST = TOP / "tests" / "matrix" / "witnesses.jsonl"
"""The declared leaves: a JSONL request list, which batch.load_requests validates."""
WITNESS_LEDGER = TOP / "tests" / "matrix" / "witnesses.json"
"""The committed coverage artifact: per-leaf tier and result, plus the counters."""
WITNESS_TESTS = TOP / "tests" / "test_witness_matrix.py"
"""The suite that executes the leaves; run_witness shells out to it."""


def _witness_inventory() -> dict[str, Any]:
    """The declared leaves, each with the tier and result last recorded for it."""
    try:
        requests = batch.load_requests([WITNESS_LIST])
    except (batch.SpecError, OSError) as exc:
        msg = f"cannot read {WITNESS_LIST}: {exc}"
        raise ToolError(msg) from exc
    ledger: dict[str, Any] = json.loads(WITNESS_LEDGER.read_text(encoding="utf-8")) if WITNESS_LEDGER.is_file() else {}
    recorded: dict[str, dict[str, Any]] = {entry["id"]: entry for entry in ledger.get("leaves", [])}
    leaves = [
        {
            "id": request.id,
            "tier": recorded.get(request.id, {}).get("tier", "unrecorded"),
            "result": recorded.get(request.id, {}).get("result", "not-run"),
        }
        for request in requests
    ]
    return {
        "total": len(leaves),
        "coverage": ledger.get("coverage", {}),
        "tiers": dict(sorted(Counter(leaf["tier"] for leaf in leaves).items())),
        "results": dict(sorted(Counter(leaf["result"] for leaf in leaves).items())),
        "leaves": leaves,
    }


@server.tool()
def list_witnesses() -> dict[str, Any]:
    """List the questionnaire's Z3 witness leaves and what has executed them.

    The 225 leaves are `tests/matrix/witnesses.jsonl` -- the request list
    `tools/z3_witnesses.py` enumerates, one answer combination each -- and
    `tier` / `result` are the deepest verdict `tests/matrix/witnesses.json`
    records for that leaf, so this is the "what is already verified" answer.
    Returns `total`, `coverage` (the ledger's counters), `tiers` and `results`
    (leaf counts per value) and `leaves`: {id, tier, result} in declaration
    order. Filesystem only -- no render, no network.
    """
    return _witness_inventory()


WITNESS_MARKERS = {
    "fast": "not heavy and not slow",
    "slow": "slow",
    "full": "full",
}
"""Tier -> pytest marker expression (`--help`-style cost of each in run_witness)."""
WITNESS_TIMEOUTS = {"fast": 900, "slow": 900, "full": 7200}
"""Per-tier wall-clock budget in seconds; the full tier builds venvs, slowest first."""


def _junit_verdicts(report: Path) -> tuple[list[batch.LineResult], dict[str, int]]:
    """Turn pytest's JUnit XML into one batch.LineResult per executed test."""
    lines: list[batch.LineResult] = []
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    # WHYNOT: the report is written by the pytest process this tool launches
    # over a fixed argv; no XML here comes from a peer.
    root = ET.parse(report).getroot()  # noqa: S314
    for index, case in enumerate(root.iter("testcase")):
        failure = case.find("failure") if case.find("failure") is not None else case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            verdict, name, detail = False, "pytest", (failure.get("message") or failure.text or "").strip()
        elif skipped is not None:
            # A W4 `tier: none` opt-out: not a failure, and not a verified leaf.
            verdict, name, detail = True, "skipped", (skipped.get("message") or "").strip()
        else:
            verdict, name, detail = True, "pytest", ""
        counts["failed" if failure is not None else "skipped" if skipped is not None else "passed"] += 1
        lines.append(
            batch.LineResult(
                id=f"{case.get('classname')}::{case.get('name')}",
                index=index,
                checks=[batch.Check(name=name, ok=verdict, detail=detail[-OUTPUT_LIMIT:])],
                seconds=float(case.get("time") or 0.0),
            )
        )
    return lines, counts


def _output_tail(stdout: str, stderr: str) -> str:
    """The tail of a subprocess' output: enough to see why it did not run."""
    return (stdout + stderr).strip()[-OUTPUT_LIMIT:]


@server.tool()
def run_witness(
    tier: Literal["fast", "slow", "full"], *, only: str | None = None, timeout: int | None = None
) -> dict[str, Any]:
    """Run one tier of the witness suite and return a verdict per test.

    `tests/test_witness_matrix.py` executes the leaves; this runs it in a
    subprocess so a caller gets its verdict instead of pytest's text. `tier` is
    the marker expression: `fast` renders and lints every leaf (no venv; a few
    seconds under the suite's `-n auto`), `slow` runs the serial 225-leaf batch
    runner (~2 min), `full` adds the sampled leaves' venv builds and their
    network. `only` narrows the selection with pytest's `-k` expression -- a
    leaf keyword, for one case -- and `timeout` overrides the tier's budget
    (seconds).

    Returns `ok` (pytest's exit status), the exact `command` so it can be
    rerun by hand, `seconds`, `counts` (passed / failed / skipped), `output`
    (the tail, only when the run failed) and `lines`: one entry per executed
    test in `run_batch`'s verdict shape -- `id`, `ok`, `seconds`, `checks`
    ({name, ok, detail}) -- with a skip reported as `name: "skipped"` rather
    than a failure.
    """
    if tier not in WITNESS_MARKERS:
        msg = f"unknown tier {tier!r}; expected one of {', '.join(sorted(WITNESS_MARKERS))}"
        raise ToolError(msg)
    limit = timeout or WITNESS_TIMEOUTS[tier]
    report = Path(tempfile.mkdtemp(prefix="mcp-witness-")) / "report.xml"
    command = [sys.executable, "-m", "pytest", "-q", "--junit-xml", str(report), "-m", WITNESS_MARKERS[tier]]
    if only:
        command += ["-k", only]
    command.append(str(WITNESS_TESTS))
    started = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603  WHYNOT: fixed argv; `only` is passed to pytest, not a shell.
            command, cwd=TOP, capture_output=True, text=True, check=False, timeout=limit
        )
    except subprocess.TimeoutExpired:
        msg = f"the {tier} tier did not finish within {limit}s"
        raise ToolError(msg) from None
    seconds = round(time.monotonic() - started, 3)
    if not report.is_file():
        return {
            "ok": False,
            "tier": tier,
            "only": only,
            "command": command,
            "seconds": seconds,
            "counts": {"passed": 0, "failed": 0, "skipped": 0},
            "output": _output_tail(proc.stdout, proc.stderr),
            "lines": [],
        }
    lines, counts = _junit_verdicts(report)
    return {
        "ok": proc.returncode == 0,
        "tier": tier,
        "only": only,
        "command": command,
        "seconds": seconds,
        "counts": counts,
        "output": "" if proc.returncode == 0 else _output_tail(proc.stdout, proc.stderr),
        "lines": [line.as_dict() for line in lines],
    }


# --------------------------------------------------------------------------- #
# the render fingerprint
# --------------------------------------------------------------------------- #


@server.tool()
def template_fingerprint() -> dict[str, Any]:
    """Report the sha256 of the render inputs -- what a render is a function of.

    The digest covers every file present under `template/` and `_shared/`, plus
    `copier.yml` and `_tasks.jinja`, as sorted relative path + content hash.
    Copier renders a *dirty* working tree as it finds it, so this is a
    content-based key rather than a git revision: an unchanged fingerprint
    means the same answers still render the same bytes, and a changed one means
    every render you are holding -- the one in `dest` of a previous call, a
    project's checked-in `.copier-answers.yml` render, the suite's session
    render cache -- is stale. Returns that `fingerprint`, the `algorithm`, and
    `inputs`: the trees and files covered, the path count and the total bytes.
    Hashes the working tree only -- no render, no network (~224 paths, 0.8 MB,
    ~5 ms). The digest comes from `tools/render_inputs.py`, the same one the
    test suite's render cache namespaces its entries by, so the two cannot
    disagree.
    """
    fingerprint, paths, total = render_fingerprint(TOP)
    return {
        "fingerprint": fingerprint,
        "algorithm": "sha256(relative path + \\0 + sha256(content)) over the sorted inputs",
        "inputs": {
            "dirs": list(RENDER_INPUT_DIRS),
            "files": list(RENDER_INPUT_FILES),
            "paths": paths,
            "bytes": total,
        },
    }


@server.resource("template://questionnaire")
def questionnaire_resource() -> str:
    """The full questionnaire as JSON, including the internal variables."""
    questions, settings = questionnaire.load_questions()
    return json.dumps({"questions": [q.as_dict() for q in questions], "settings": settings}, indent=2, default=str)


@server.resource("template://witnesses")
def witnesses_resource() -> str:
    """The witness leaves with their recorded tier and result, as JSON.

    Sorted keys and declaration order make the payload deterministic, so a
    caller can diff it between runs.
    """
    return json.dumps(_witness_inventory(), indent=2, sort_keys=True)


@server.resource("template://support")
def support_resource() -> str:
    """The declared support contract (`support.yml`) as JSON.

    What the project promises to have executed, per combination and per leaf
    class, each entry carrying the measured `why`. Read through
    tools/gen_docs.py's loader -- the same one the generated docs blocks and
    tests/test_support_matrix.py use -- so a caller sees the live declaration
    rather than a second reading of the file.
    """
    return json.dumps(gen_docs.load_support(gen_docs.SUPPORT_YML), indent=2, sort_keys=True)


@server.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    """Liveness probe for an orchestrator (unauthenticated, no data).

    A custom route is a plain Starlette route, so it bypasses the Host
    allowlist that guards /mcp -- the same trade the generated scaffold makes,
    and why this one answers nothing but "the process is up".
    """
    return JSONResponse({"status": "ok"})


def _allowed_hosts() -> TransportSecuritySettings | None:
    """Turn MCP_ALLOWED_HOSTS / MCP_ALLOWED_ORIGINS into the SDK's settings."""
    raw_hosts = os.environ.get("MCP_ALLOWED_HOSTS")
    if not raw_hosts:
        return None
    hosts = [host.strip() for host in raw_hosts.split(",") if host.strip()]
    raw_origins = os.environ.get("MCP_ALLOWED_ORIGINS")
    if not raw_origins:
        return TransportSecuritySettings(allowed_hosts=hosts)
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins)


def main(args: Sequence[str] | None = None) -> None:
    """Run the MCP server with stdio (default) or Streamable HTTP."""
    parser = argparse.ArgumentParser(description="MCP server for python-copier-template")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (streamable-http)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (streamable-http)")
    parsed = parser.parse_args(args)
    transport = cast(Literal["stdio", "streamable-http"], parsed.transport)
    if transport == "streamable-http":
        host = cast(str, parsed.host)
        if host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("MCP_ALLOWED_HOSTS"):
            parser.error(
                "binding to a non-local host requires MCP_ALLOWED_HOSTS "
                "(comma-separated host allowlist) so the server does not "
                "accept every Host header"
            )
        server.run(transport=transport, host=host, port=cast(int, parsed.port), transport_security=_allowed_hosts())
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
