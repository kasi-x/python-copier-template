#!/usr/bin/env python3
"""Witness and suite surface: leaves, inverse lookup, tier runners, resources.

Responsibility: the witness ledger (`list_witnesses`, `recommend_answers`,
`run_witness`), the repository's own suite tiers (`run_tests`), the pytest
plumbing both runners share (`_output_tail`, `_build_pytest_command`,
`_format_pytest_tier_result`, `_run_pytest_tier`), and the three read-only
resources (`template://questionnaire`, `template://witnesses`,
`template://support`). The tier tables (`WITNESS_MARKERS`,
`WITNESS_TIMEOUTS`, `TIER_TASKS`, `TIER_LEDGER`, `TIER_TIMEOUTS`) live with
the runners that read them. Ethics sections live in the law-map guidance
tree, not here.
"""

# WHYNOT: the functions below are registered through
# @mcp_interface.tool(server)/@server.resource() inside register_*(); their call edge
# is the decorator, invisible to the checker.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any
from typing import Literal

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from architekton import answers_for  # noqa: E402
from architekton import batch  # noqa: E402
from architekton import mcp_interface  # noqa: E402
from architekton import questionnaire  # noqa: E402
from architekton import support_ledger  # noqa: E402
from architekton.mcp_shared import OUTPUT_LIMIT  # noqa: E402
from architekton.render_inputs import RENDER_INPUT_DIRS  # noqa: E402
from architekton.render_inputs import RENDER_INPUT_FILES  # noqa: E402
from architekton.render_inputs import render_fingerprint as _render_fingerprint  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

WITNESS_LIST = TOP / "tests" / "matrix" / "witnesses.jsonl"
"""The declared leaves: a JSONL request list, which batch.load_requests validates."""
WITNESS_LEDGER = TOP / "tests" / "matrix" / "witnesses.json"
"""The committed coverage artifact: per-leaf tier and result, plus the counters."""
WITNESS_TESTS = TOP / "tests" / "test_witness_matrix.py"
"""The suite that executes the leaves; run_witness shells out to it."""

WITNESS_MARKERS = {
    "fast": "not heavy and not slow",
    "slow": "slow",
    "full": "full",
}
"""Tier -> pytest marker expression (`--help`-style cost of each in run_witness)."""
WITNESS_TIMEOUTS = {"fast": 900, "slow": 900, "full": 7200}
"""Per-tier wall-clock budget in seconds; the full tier builds venvs, slowest first."""

# The suite tiers a caller can ask for, and the ledger row each one is. The
# marker expressions themselves are NOT repeated here: tests/matrix/tiers.json
# records them per task (and tests/test_marker_drift.py already holds that file
# against Taskfile.yml), so this reads the row instead of keeping a copy that
# could drift from the task it claims to run.
TIER_TASKS = {"fast": "test-fast", "heavy": "test-heavy", "slow": "test-slow", "meta": "test-meta", "all": "test"}
TIER_LEDGER = TOP / "tests" / "matrix" / "tiers.json"
TIER_TIMEOUTS = {"fast": 1800, "heavy": 3600, "slow": 1800, "meta": 900, "all": 7200}
"""Per-tier wall-clock budget in seconds, generous enough for a cold cache."""


def _paths() -> tuple[Path, Path, Path, Path]:
    """Resolve the witness/ledger paths against the (possibly monkeypatched) shim TOP."""
    from architekton.mcp_shared import repo_root  # noqa: E402, PLC0415  -- the shim owns TOP; leaves read it lazily.

    top = repo_root()
    return (
        top / "tests" / "matrix" / "witnesses.jsonl",
        top / "tests" / "matrix" / "witnesses.json",
        top / "tests" / "test_witness_matrix.py",
        top / "tests" / "matrix" / "tiers.json",
    )


def witness_inventory() -> dict[str, Any]:
    """The declared leaves, each with the tier and result last recorded for it."""
    witness_list, witness_ledger, _witness_tests, _tier_ledger = _paths()
    try:
        requests = batch.load_requests([witness_list])
    except (batch.SpecError, OSError) as exc:
        msg = f"cannot read {witness_list}: {exc}"
        raise ToolError(msg) from exc
    ledger: dict[str, Any] = json.loads(witness_ledger.read_text(encoding="utf-8")) if witness_ledger.is_file() else {}
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


def output_tail(stdout: str, stderr: str) -> str:
    """The tail of a subprocess' output: enough to see why it did not run."""
    return (stdout + stderr).strip()[-OUTPUT_LIMIT:]


def build_pytest_command(report: Path, expression: str | None, only: str | None, tests: Path | None) -> list[str]:
    """Assemble the pytest argv for running a tier in a subprocess."""
    command = [sys.executable, "-m", "pytest", "-q", "--junit-xml", str(report)]
    if expression:
        command += ["-m", expression]
    if only:
        command += ["-k", only]
    if tests is not None:
        command.append(str(tests))
    return command


def format_pytest_tier_result(
    proc: subprocess.CompletedProcess[str],
    report: Path,
    meta: tuple[str, str | None, float],
    command: list[str],
) -> dict[str, Any]:
    """Parse the JUnit XML report and return the structured verdict dictionary."""
    tier, only, seconds = meta
    if not report.is_file():
        return {
            "ok": False,
            "tier": tier,
            "only": only,
            "command": command,
            "seconds": seconds,
            "counts": {"passed": 0, "failed": 0, "skipped": 0},
            "output": output_tail(proc.stdout, proc.stderr),
            "lines": [],
        }
    lines, counts = batch.junit_verdicts(report)
    return {
        "ok": proc.returncode == 0,
        "tier": tier,
        "only": only,
        "command": command,
        "seconds": seconds,
        "counts": counts,
        "output": "" if proc.returncode == 0 else output_tail(proc.stdout, proc.stderr),
        "lines": [line.as_dict() for line in lines],
    }


def run_pytest_tier(
    tier: str, expression: str | None, tests: Path | None, *, only: str | None, timeout: int
) -> dict[str, Any]:
    """Run one pytest selection in a subprocess and return the structured verdict.

    The one body behind run_witness and run_tests: `expression` is the ``-m`` marker
    selection (None omits it), `tests` an optional file to run, `only` the
    ``-k`` narrowing. The verdict machinery (junit -> LineResult) is
    batch.junit_verdicts.
    """
    from architekton.mcp_shared import repo_root  # noqa: E402, PLC0415  -- the shim owns TOP; leaves read it lazily.

    report = Path(tempfile.mkdtemp(prefix="mcp-pytest-")) / "report.xml"
    command = build_pytest_command(report, expression, only, tests)
    started = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603  WHYNOT: fixed argv; `only` is passed to pytest, not a shell.
            command, cwd=repo_root(), capture_output=True, text=True, check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        msg = f"the {tier} tier did not finish within {timeout}s"
        raise ToolError(msg) from None
    seconds = round(time.monotonic() - started, 3)
    return format_pytest_tier_result(proc, report, (tier, only, seconds), command)


def register_witness(server: Any) -> None:
    """Register the witness/suite tools and the read-only resources on `server`."""
    _register_witness_tools(server)
    _register_suite_tools(server)
    _register_mcp_resources(server)


def _register_witness_tools(server: Any) -> None:  # noqa: C901  -- two witness tools; the bodies are the pre-split implementations.
    """Register the witness-ledger tools on `server`."""

    @mcp_interface.tool(server)
    def list_witnesses() -> dict[str, Any]:
        """The answer combinations the test suite covers, with their recorded verdicts.

        Returns total, coverage (the ledger counters), tiers and results (leaf
        counts per value) and leaves ({id, tier, result}). Cost: filesystem only.
        """
        return witness_inventory()

    @mcp_interface.tool(server)
    def recommend_answers(constraints: list[str], *, render: bool = False) -> dict[str, Any]:
        """The covered answer combinations that match named constraints.

        Each constraint is `name`, `name=value`, `-name` or `name!=value` over
        any question or derived value; an unknown name is refused with the
        closest real names. Returns constraints, matched, shown, leaves (each
        with answers, answers_yaml and ships), diagnostic (when nothing matches:
        the nearest leaf and what it misses) and render (`render=True` renders
        the top match and checks every constraint against it). Cost: filesystem
        only, ~50 ms warm and ~25 s on the first call; one render with `render=True`.
        """
        try:
            return answers_for.recommend(constraints, render=render, keep=True)
        except answers_for.ConstraintError as exc:
            raise ToolError(str(exc)) from exc

    @mcp_interface.tool(server)
    def run_witness(
        tier: Literal["fast", "slow", "full"], *, only: str | None = None, timeout: int | None = None
    ) -> dict[str, Any]:
        """Run the covered combinations at one tier and return a verdict per test.

        `tier` is fast (seconds, renders only), slow (minutes) or full (builds
        venvs, network, tens of minutes); `only` is a pytest -k expression over
        leaf ids; `timeout` overrides the tier's budget in seconds. Returns ok,
        command, seconds, counts, output (on failure) and lines ({id, ok,
        seconds, checks}). Cost: renders; venv installs and network at `full`.
        """
        if tier not in WITNESS_MARKERS:
            msg = f"unknown tier {tier!r}; expected one of {', '.join(sorted(WITNESS_MARKERS))}"
            raise ToolError(msg)
        limit = timeout or WITNESS_TIMEOUTS[tier]
        _witness_list, _witness_ledger, witness_tests, _tier_ledger = _paths()
        return run_pytest_tier(tier, WITNESS_MARKERS[tier], witness_tests, only=only, timeout=limit)


def _register_suite_tools(server: Any) -> None:  # noqa: C901  -- three suite/fingerprint tools; the bodies are the pre-split implementations.
    """Register the suite-tier runners and the fingerprint tool on `server`."""

    @mcp_interface.tool(server)
    def run_tests(
        tier: Literal["fast", "heavy", "slow", "meta", "all"], *, only: str | None = None, timeout: int | None = None
    ) -> dict[str, Any]:
        """Run one of the repository's own test tiers and return a verdict per test.

        `tier` is fast, heavy, slow, meta or all; `only` is a pytest -k
        expression; `timeout` overrides the tier's budget in seconds. Returns ok,
        tier, only, command, seconds, counts, output (on failure) and lines
        ({id, ok, seconds, checks}). Cost: shells out to pytest; heavy and all
        build venvs and use the network.
        """
        task = TIER_TASKS.get(tier)
        if task is None:
            msg = f"unknown tier {tier!r}; expected one of {', '.join(sorted(TIER_TASKS))}"
            raise ToolError(msg)
        _witness_list, _witness_ledger, _witness_tests, tier_ledger = _paths()
        try:
            rows = json.loads(tier_ledger.read_text(encoding="utf-8"))["tiers"]
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            msg = f"cannot read the tier ledger {tier_ledger}: {exc}"
            raise ToolError(msg) from exc
        expression = str(rows.get(task, {}).get("expression", "")) or None
        limit = timeout or TIER_TIMEOUTS[tier]
        return run_pytest_tier(tier, expression, None, only=only, timeout=limit)

    @mcp_interface.tool(server)
    def template_fingerprint() -> dict[str, Any]:
        """A sha256 over every input a render depends on.

        Returns fingerprint, algorithm and inputs (dirs, files, path count,
        bytes). An unchanged fingerprint means the same answers render the same
        bytes; a changed one means earlier renders are stale. Cost: hashes
        ~0.8 MB, ~5 ms.
        """
        from architekton.mcp_shared import (
            repo_root,  # noqa: E402, PLC0415  -- the shim owns TOP; leaves read it lazily.
        )

        fingerprint, paths, total = _render_fingerprint(repo_root())
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


def _register_mcp_resources(server: Any) -> None:
    """Register the read-only template resources on `server`."""

    @server.resource("template://questionnaire")
    def questionnaire_resource() -> str:
        """The full questionnaire as JSON, including the internal variables."""
        _questions, settings = questionnaire.load_questions()
        entries = questionnaire.schema_entries()
        return json.dumps({"questions": entries, "settings": settings}, indent=2, default=str)

    @server.resource("template://witnesses")
    def witnesses_resource() -> str:
        """The witness leaves with their recorded tier and result, as JSON.

        Sorted keys and declaration order make the payload deterministic, so a
        caller can diff it between runs.
        """
        return json.dumps(witness_inventory(), indent=2, sort_keys=True)

    @server.resource("template://support")
    def support_resource() -> str:
        """The declared support contract (`tests/matrix/support.yml`) as JSON.

        What the project promises to have executed, per combination and per leaf
        class, each entry carrying the measured `why`. Read through
        architekton/support_ledger.py -- the one reader of the file, shared with the
        generated docs blocks and tests/test_support_matrix.py -- so a caller sees
        the live declaration rather than a second reading of it.
        """
        return json.dumps(support_ledger.load_support(), indent=2, sort_keys=True)
