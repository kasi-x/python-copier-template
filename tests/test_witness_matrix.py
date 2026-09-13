"""Execute the questionnaire's Z3 witness leaves (PLAN-improvements §W3, §C4, §C6).

tools/z3_witnesses.py enumerates the leaf space of the questionnaire's
``use_recommended_*`` gates, include layers and project types, and writes it
out as §C6 batch requests (tests/matrix/witnesses.jsonl, 205 leaves). This
module *executes* that declaration in three tiers:

``fast``
    render every leaf with copier (``skip_tasks=True``, no venv) and assert the
    leaf's declared artifact set -- the ``expect`` files/absent list the
    generator derived -- plus ``ruff format --check`` / ``ruff check`` on the
    rendered Python. Renders come from tests/render_cache.py, so the tiers that
    share answers pay for one copier run.
``full``
    a bounded sample of leaves additionally gets ``uv sync``, the generated
    project's own ``pytest``, ``basedpyright`` and its docs build.
``slow``
    tools/batch.py runs the whole JSONL through the real §C6 runner, whose
    verdict -- not this module's -- is the judge for "every leaf ran and every
    expectation held".

Coverage: tests/matrix/witnesses.json (§C4) records one entry per leaf with
its declared tier and the verdict of the deepest recorded run (``source``:
``fast`` for a render, ``full`` for the venv tier). Every verdict merges into
the ledger under a lock, so the artifact is order-independent: a fresh failure
is always recorded, a deeper verdict survives a shallower run (the render tier
cannot clear a failure only the venv tier can see), and at equal depth the
fresher verdict wins (how a fixed leaf clears its failure). A leaf this
session did not exercise keeps the verdict of its last recorded run, so a
tier that does not cover every leaf can only leave a result stale -- never
drop a leaf. test_witness_coverage (fast tier) fails when a leaf has no
recorded run, and the batch runner refreshes the ledger from the §C6 engine's
verdicts in the full tier.

W4 may grant a leaf ``tier: none`` in that file (with a ``reason``): both
tiers skip it and the coverage assertion stops requiring a run for it.

Guard for the guard: test_witness_leaves_match_the_generator and
test_witness_leaves_are_reachable fail -- naming the leaves -- when a
questionnaire edit makes a declared leaf unreachable, e.g. forcing a gate's
``when`` to false.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_batch.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools import batch  # noqa: E402

# Imported so pytest can inject the session render cache (it lives in
# render_cache.py, not conftest.py: the template renders conftest.py into every
# generated project).
from render_cache import RenderCache  # noqa: E402
from render_cache import render_cache as render_cache  # noqa: E402, PLC0414

WITNESSES = TOP / "tests" / "matrix" / "witnesses.jsonl"
COVERAGE = TOP / "tests" / "matrix" / "witnesses.json"
GENERATOR = TOP / "tools" / "z3_witnesses.py"
STRUCTURE_TESTS = TOP / "tests" / "test_copier_structure.py"

# The ledger is written by several xdist workers at once (every verdict merges
# into it) and rewritten on every run, so both the read-modify-write lock and
# the scratch file live in pytest's own ignored directory -- never a stray file
# in tests/matrix/.
LEDGER_LOCK = TOP / ".pytest_cache" / "witness-ledger.lock"
LEDGER_SCRATCH = TOP / ".pytest_cache" / "witnesses.json.tmp"

FAST = "fast"
FULL = "full"
NONE = "none"

PASS = "pass"
FAIL = "fail"
NOT_RUN = "not-run"
EXCLUDED = "excluded"

# Full-tier sample: one leaf per project family whose checks run on a bare
# runner, plus the one gate-off leaf that switches the agent prompts on (the
# only branch-only artifact set). 205 leaves x a venv build + docs (~3 min
# each) is ~10 hours, so the deep checks are sampled; the render and batch
# tiers still execute every leaf, and test_witness_coverage requires each leaf
# to have run in at least one of them. ros2 is omitted on purpose: its
# generated test/build recipes need a ROS distribution (`/opt/ros/$ROS_DISTRO`),
# not a bare runner, so its leaves stay in the render tiers.
FULL_SAMPLE: tuple[str, ...] = (
    "project_type=library/gate=recommended",
    "project_type=cli/gate=recommended",
    "project_type=web_api/gate=recommended",
    "project_type=data_science/gate=recommended",
    "project_type=script/gate=recommended",
    "project_type=micropython/gate=recommended",
    "project_type=online_judge/gate=recommended/oj=competitive_coding/atcoder",
    "project_type=cli/gate=off:use_recommended_agent",
)

# Per-leaf timeouts: the full tier is bounded by PLAN-improvements §W3's 550s,
# and the batch runner renders 205 projects serially (no venv, ~1.5s each) so
# it needs the wider budget.
FULL_TIMEOUT = 550
BATCH_TIMEOUT = 1800
GENERATOR_TIMEOUT = 300

# How long test_witness_coverage waits for sibling xdist workers to record the
# leaves that neither this session nor the committed ledger has a verdict for.
# With a committed ledger (the normal case, including a fresh clone) nothing is
# ever pending, so this only fires when the witness list itself was
# regenerated; 205 renders at ~1.3s over `-n auto` finish far inside it.
COVERAGE_GRACE = 600


@dataclass(frozen=True)
class Witness:
    """One declared leaf: the §C6 request line, parsed by the runner's parser."""

    id: str
    answers: dict[str, Any]
    expect: dict[str, Any]


def _load_witnesses() -> list[Witness]:
    """Parse tests/matrix/witnesses.jsonl with tools/batch.py's own validator."""
    requests = batch.load_requests([WITNESSES])
    return [Witness(id=request.id, answers=dict(request.answers), expect=dict(request.expect)) for request in requests]


LEAVES: list[Witness] = _load_witnesses()
LEAF_BY_ID: dict[str, Witness] = {leaf.id: leaf for leaf in LEAVES}


def _leaf(leaf_id: str) -> Witness:
    """The declared leaf, or a test failure naming the drifted declaration."""
    leaf = LEAF_BY_ID.get(leaf_id)
    if leaf is None:
        pytest.fail(f"leaf {leaf_id!r} is not declared in {WITNESSES.name}; regenerate the witness list")
    return leaf


def _tier(leaf_id: str) -> str:
    """The deepest tier a leaf is declared for (FULL_SAMPLE promotes leaves)."""
    return FULL if leaf_id in FULL_SAMPLE else FAST


def _recorded_ledger() -> dict[str, Any]:
    """The committed coverage artifact (§C4), or an empty one."""
    if not COVERAGE.exists():
        return {"leaves": [], "coverage": {}}
    payload = json.loads(COVERAGE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{COVERAGE} is not an object"
    return payload


def _exclusions() -> dict[str, str]:
    """W4's ``tier: none`` opt-outs: leaf id -> reason (empty when none)."""
    exclusions: dict[str, str] = {}
    for entry in _recorded_ledger().get("leaves", []):
        if entry.get("tier") != NONE:
            continue
        reason = entry.get("reason")
        assert isinstance(reason, str) and reason, (
            f"{COVERAGE.name}: {entry.get('id')!r} declares tier 'none' without a reason; W4 must say why it is unsupported"
        )
        exclusions[str(entry["id"])] = reason
    return exclusions


def _skip_excluded(leaf: Witness) -> None:
    """Skip a W4-excluded leaf, quoting the declared reason (§C5 best_effort)."""
    reason = _exclusions().get(leaf.id)
    if reason is not None:
        pytest.skip(f"tier none (W4): {reason}")


class ResultStore:
    """Per-leaf verdicts of this session, shared by every xdist worker.

    One file per leaf keeps concurrent workers from clobbering each other (the
    batch runner writes 205 verdicts in one process, a render case writes one).
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, leaf_id: str) -> Path:
        return self.root / f"{hashlib.sha256(leaf_id.encode()).hexdigest()[:24]}.json"

    def write(self, leaf_id: str, tier: str, result: str, seconds: float = 0.0) -> None:
        """Record one verdict: atomically here, merged into the ledger under its lock.

        Merging here (and not only in the aggregate writers) is what makes the
        §C4 artifact order-independent: a verdict reaches it even when the
        writer that recorded it finishes last, after another writer already
        refreshed the file.
        """
        payload = {"id": leaf_id, "tier": tier, "result": result, "seconds": round(seconds, 3)}
        path = self._path(leaf_id)
        scratch = path.with_name(f"{path.name}.tmp")
        scratch.write_text(json.dumps(payload), encoding="utf-8")
        Path(scratch).replace(path)
        _merge_verdict(payload)

    @contextlib.contextmanager
    def record(self, leaf_id: str, tier: str) -> Generator[None, None, None]:
        """Record ``pass``/``fail`` for the enclosed test body."""
        started = time.monotonic()
        try:
            yield
        except BaseException:
            self.write(leaf_id, tier, FAIL, time.monotonic() - started)
            raise
        else:
            self.write(leaf_id, tier, PASS, time.monotonic() - started)

    def entries(self) -> dict[str, list[dict[str, Any]]]:
        """Every verdict written so far, keyed by leaf id."""
        found: dict[str, list[dict[str, Any]]] = {}
        for path in sorted(self.root.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            found.setdefault(str(payload["id"]), []).append(payload)
        return found


@pytest.fixture(scope="session")
def witness_results(tmp_path_factory: pytest.TempPathFactory) -> ResultStore:
    """The one result store every process of this session agrees on.

    pytest hands each xdist worker its own basetemp (``<controller>/popen-gwN``
    under the usual ``-n auto``), so the shared store lives in its parent --
    the same trick tests/render_cache.py uses for its cache.
    """
    base = tmp_path_factory.getbasetemp()
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker and base.name == f"popen-{worker}":
        base = base.parent
    return ResultStore(base / "witness-results")


def _run_python(args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    """Run a repo tool with the interpreter running this suite."""
    return subprocess.run(
        [sys.executable, *args],
        cwd=TOP,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# --------------------------------------------------------------------------- #
# Guard for the guard: the declared leaves must still exist in the template.
# --------------------------------------------------------------------------- #


@pytest.mark.fast
@pytest.mark.full
def test_witness_leaves_match_the_generator() -> None:
    """The committed JSONL is exactly what tools/z3_witnesses.py enumerates.

    A questionnaire edit that makes a projected branch unsatisfiable makes the
    generator abort (its own reachability assertion), and an edit that changes
    an answer or an expected artifact set changes a request line. Either way
    the committed witness list is stale, and the failing leaves are named here.
    """
    proc = _run_python([str(GENERATOR), "--json"], timeout=GENERATOR_TIMEOUT)
    assert proc.returncode == 0, (
        f"tools/z3_witnesses.py can no longer enumerate the leaf space, so the "
        f"{len(LEAVES)} committed leaves are unverifiable:\n{proc.stderr[-4000:]}"
    )
    generated = {str(leaf["id"]): leaf for leaf in json.loads(proc.stdout)["leaves"]}
    declared = {leaf.id: leaf for leaf in LEAVES}

    uncovered = sorted(set(declared) - set(generated))
    stale = sorted(set(generated) - set(declared))
    assert not uncovered and not stale, (
        f"{WITNESSES.name} is out of sync with the questionnaire:\n"
        f"  declared but no longer generated ({len(uncovered)}): {uncovered[:10]}\n"
        f"  generated but not declared ({len(stale)}): {stale[:10]}\n"
        f"regenerate with: python tools/z3_witnesses.py --jsonl {WITNESSES}"
    )

    drifted = sorted(
        leaf_id
        for leaf_id in declared
        if generated[leaf_id]["answers"] != declared[leaf_id].answers
        or generated[leaf_id]["expect"] != declared[leaf_id].expect
    )
    assert not drifted, (
        f"{len(drifted)} declared leaf/leaves changed answers or expectations: {drifted[:10]}\n"
        f"regenerate with: python tools/z3_witnesses.py --jsonl {WITNESSES}"
    )


def _structure_module() -> ModuleType:
    """Load tests/test_copier_structure.py -- the project's Z3 encoder lives there."""
    spec = importlib.util.spec_from_file_location("_witness_matrix_structure", STRUCTURE_TESTS)
    assert spec is not None and spec.loader is not None, f"cannot import {STRUCTURE_TESTS}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _conditional_answers(leaf: Witness) -> list[str]:
    """The answers that assert a conditional branch (gate off, or layer on)."""
    return sorted(
        name
        for name, value in leaf.answers.items()
        if (name.startswith("use_recommended_") and value is False) or (name.startswith("include_") and value is True)
    )


@pytest.mark.fast
@pytest.mark.full
def test_witness_leaves_are_reachable() -> None:
    """Every conditional answer of every declared leaf can still be asked.

    This is the leaf-level half of the guard: a gate switched off (or a layer
    switched on) may only be a witness if that question's ``when`` can hold.
    Forcing e.g. ``use_recommended_agent``'s ``when`` to false leaves every
    ``gate=off:use_recommended_agent`` leaf uncovered, and the failures below
    name them.
    """
    z3 = pytest.importorskip("z3")
    structure = _structure_module()
    questions, _order = structure._load_questions()  # noqa: SLF001
    domains = structure._sweep_str_domains(questions)  # noqa: SLF001
    project_types = structure._static_str_choices(questions["project_type"])  # noqa: SLF001

    uncovered: list[str] = []
    for leaf in LEAVES:
        project_type = leaf.answers.get("project_type")
        if project_type is not None and project_type not in project_types:
            uncovered.append(f"{leaf.id}: project_type {project_type!r} is no longer a questionnaire choice")
        for name in _conditional_answers(leaf):
            question = questions.get(name)
            if question is None:
                uncovered.append(f"{leaf.id}: answers {name}, which the questionnaire no longer declares")
                continue
            when = question.get("when")
            if isinstance(when, str) and not structure._when_expr_satisfiable(when, domains, z3):  # noqa: SLF001
                uncovered.append(
                    f"{leaf.id}: answers {name}={leaf.answers[name]!r}, but its when {when!r} can never hold"
                )

    assert not uncovered, (
        f"{len(uncovered)} of {len(LEAVES)} witness leaves are unreachable under the current questionnaire:\n  "
        + "\n  ".join(uncovered)
    )


# --------------------------------------------------------------------------- #
# fast tier: render every leaf and check the invariants it declares.
# --------------------------------------------------------------------------- #


def _ruff_bin() -> Path:
    """The ruff in this repo's venv (the generated project has none of its own)."""
    for base in (TOP / ".venv" / "bin", Path(sys.executable).resolve().parent):
        candidate = base / "ruff"
        if candidate.exists():
            return candidate
    pytest.fail("ruff not found in .venv/bin or next to sys.executable")


def _expectation_problems(dest: Path, expect: dict[str, Any]) -> list[str]:
    """Judge a render with tools/batch.py's own checkers (same verdicts, no drift)."""
    checks = batch.check_files(dest, [str(pattern) for pattern in expect.get("files", [])])
    checks += batch.check_absent(dest, [str(pattern) for pattern in expect.get("absent", [])])
    return [f"{check.name}: {check.detail}" for check in checks if not check.ok]


def _ruff_problems(dest: Path) -> list[str]:
    """``ruff format --check`` + ``ruff check`` under the generated config.

    Only where it is meaningful: a leaf whose render ships no Python (bare
    workspaces) or no ``[tool.ruff]`` has nothing for the generated lint to
    judge, so it is not judged.
    """
    if not any(dest.rglob("*.py")):
        return []
    pyproject = dest / "pyproject.toml"
    if not pyproject.exists() or "[tool.ruff" not in pyproject.read_text(encoding="utf-8"):
        return []
    ruff = _ruff_bin()
    for args in (["format", "--check"], ["check"]):
        proc = subprocess.run(
            [str(ruff), *args, "--no-cache", "."],
            cwd=dest,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return [f"ruff {' '.join(args)} failed:\n{proc.stdout}{proc.stderr}"]
    return []


@pytest.mark.fast
@pytest.mark.parametrize("leaf_id", [leaf.id for leaf in LEAVES])
def test_witness_render_invariants(
    leaf_id: str, tmp_path: Path, render_cache: RenderCache, witness_results: ResultStore
):
    """Every leaf renders, produces its declared artifacts, and lints clean."""
    leaf = _leaf(leaf_id)
    _skip_excluded(leaf)
    with witness_results.record(leaf.id, FAST):
        render_cache.render(tmp_path, dict(leaf.answers))
        problems = _expectation_problems(tmp_path, leaf.expect)
        problems += _ruff_problems(tmp_path)
        assert not problems, f"{leaf.id} rendered into {tmp_path} violates its declared invariants:\n  " + "\n  ".join(
            problems
        )


# --------------------------------------------------------------------------- #
# full tier: the bounded sample, with a venv.
# --------------------------------------------------------------------------- #


def _run(cmd: str, dest: Path, venv: Path) -> str:
    """Run a command in a rendered project's own venv (test_example.py's recipe)."""
    proc = subprocess.run(
        shlex.split(cmd),
        cwd=dest,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=dict(os.environ, UV_PROJECT_ENVIRONMENT="", VIRTUAL_ENV=str(venv)),
        check=False,
    )
    output = proc.stdout.decode()
    assert proc.returncode == 0, f"{cmd} failed in {dest}:\n{output}"
    return output


def _render_leaf(dest: Path, leaf: Witness) -> None:
    """Render one leaf the way example-answers-based heavy tests do (git-tracked).

    The git repo matters: the generated project versions itself with
    setuptools_scm, which needs one (tests/test_example.py's heavy recipe).
    """
    from copier import run_copy  # noqa: PLC0415  WHYNOT: only the heavy tier needs copier's API.

    init = subprocess.run(["git", "init", str(dest)], capture_output=True, text=True, check=False)
    assert init.returncode == 0, f"git init {dest} failed:\n{init.stdout}{init.stderr}"
    run_copy(
        src_path=str(TOP),
        dst_path=dest,
        data=dict(leaf.answers),
        vcs_ref="HEAD",
        unsafe=True,
        defaults=True,
    )
    _run("git add .", dest, dest / ".venv")


def _make_venv(dest: Path) -> None:
    """``uv sync`` the rendered project and commit the lockfile it just created."""
    venv = dest / ".venv"
    _run("uv sync", dest, venv)
    assert (venv / "bin" / "python").exists(), f"uv created a venv but did not install {venv / 'bin' / 'python'}"
    _run("git config user.email 'you@example.com'", dest, venv)
    _run("git config user.name 'Your Name'", dest, venv)
    _run("git add -A", dest, venv)
    _run("git commit -qm 'Initial sync'", dest, venv)


def _docs_runner(dest: Path) -> str | None:
    """How to build this rendered project's docs, per its own task runner.

    The runner's docs recipe must exist: a project family that ships no docs
    task (ros2) has nothing to build, which the caller asserts against its
    docs sources rather than skipping silently.
    """
    recipes = (("justfile", "uvx --from rust-just just docs"), ("Taskfile.yml", "uvx --from go-task-bin task docs"))
    for name, command in recipes:
        path = dest / name
        if path.exists() and re.search(r"^\s*docs:", path.read_text(encoding="utf-8"), re.MULTILINE):
            return command
    return None


@pytest.mark.full
@pytest.mark.heavy
@pytest.mark.network
@pytest.mark.timeout(FULL_TIMEOUT)
@pytest.mark.parametrize("leaf_id", FULL_SAMPLE)
def test_witness_full_tier(leaf_id: str, tmp_path: Path, witness_results: ResultStore):
    """The sample leaves survive what their own generated project CI runs."""
    leaf = _leaf(leaf_id)
    _skip_excluded(leaf)
    with witness_results.record(leaf.id, FULL):
        dest = tmp_path / "project"
        _render_leaf(dest, leaf)
        _make_venv(dest)
        _run("uv run --locked pytest -q", dest, dest / ".venv")
        _run("uv run --locked basedpyright", dest, dest / ".venv")
        docs = _docs_runner(dest)
        if docs is None:
            # No docs entry point: the render must not ship a docs source tree
            # either, or "no docs build" would be hiding one.
            assert not (dest / "zensical.toml").exists() and not (dest / "docs").is_dir(), (
                f"{leaf.id} ships docs sources without a docs task"
            )
        else:
            _run(docs, dest, dest / ".venv")
            assert any(dest.glob("site/**/*.html")), f"{leaf.id}: the docs build produced no site/ output"


# --------------------------------------------------------------------------- #
# the real §C6 runner over the whole JSONL.
# --------------------------------------------------------------------------- #


@pytest.mark.slow
@pytest.mark.full
@pytest.mark.timeout(BATCH_TIMEOUT)
def test_witness_batch_runner_executes_every_leaf(witness_results: ResultStore):
    """tools/batch.py runs the JSONL and judges every leaf's expectations.

    The runner is the §C6 judge, so this is the end-to-end proof that all 205
    requests render and that every `expect` (files/absent) holds. Its verdicts
    go into the result store and refresh the §C4 ledger, so a nightly
    ``-m full`` run records what the real engine saw.
    """
    proc = _run_python(
        ["tools/batch.py", str(WITNESSES.relative_to(TOP)), "--json"],
        timeout=BATCH_TIMEOUT,
    )
    assert proc.returncode in (0, 1), (
        f"the batch runner rejected the request list (exit {proc.returncode}):\n{proc.stderr[-4000:]}"
    )
    lines = {str(line["id"]): line for line in json.loads(proc.stdout)["lines"]}
    missing = [leaf.id for leaf in LEAVES if leaf.id not in lines]
    # The runner renders and judges expectations -- the fast tier's checks --
    # so its verdicts count as fast-tier observations: they can never clear a
    # failure only the full tier's venv checks can see.
    for leaf_id, line in lines.items():
        witness_results.write(leaf_id, FAST, PASS if line["ok"] else FAIL, float(line.get("seconds", 0.0)))
    with _ledger_lock():
        entries, uncovered = _ledger_entries(_observations(witness_results))
        _write_ledger(entries, uncovered)

    assert not missing, (
        f"the runner never executed {len(missing)} of {len(LEAVES)} leaves: {missing[:10]}\n"
        "its verdict cannot cover leaves it skipped"
    )
    assert not uncovered, (
        f"the batch run left {len(uncovered)} of {len(LEAVES)} leaves with no recorded run: {uncovered[:20]}"
    )
    failed = [leaf_id for leaf_id, line in lines.items() if not line["ok"]]
    assert not failed, f"{len(failed)} leaf/leaves failed their expectations: {failed[:20]}\n" + "\n".join(
        f"  {leaf_id}: "
        + "; ".join(f"{check['name']}: {check['detail']}" for check in lines[leaf_id]["checks"] if not check["ok"])
        + (f" ({lines[leaf_id]['error']})" if lines[leaf_id].get("error") else "")
        for leaf_id in failed[:10]
    )


# --------------------------------------------------------------------------- #
# coverage: the §C4 artifact, and the failure when a leaf has no recorded run.
# --------------------------------------------------------------------------- #


def _observation_depth(tier: str) -> int:
    """How deep a verdict went: the full tier's venv checks beat a render."""
    return {FAST: 1, FULL: 2}.get(tier, 0)


def _verdict_depth(verdict: dict[str, Any]) -> int:
    """A verdict's depth: its observation tier, falling back to its declared tier."""
    return _observation_depth(str(verdict.get("source") or verdict.get("tier")))


def _best(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The deepest verdict, and a failure when a tier reported both."""
    if not candidates:
        return None
    return max(candidates, key=lambda entry: (_verdict_depth(entry), str(entry.get("result")) != PASS))


def _pick(fresh: dict[str, Any] | None, recorded: dict[str, Any] | None) -> dict[str, Any] | None:
    """Merge one fresh verdict over the recorded one.

    A fresh failure is always recorded (a render that breaks is real evidence,
    whatever tier saw it), a deeper verdict survives a shallower run (the fast
    tier cannot clear a failure only the venv tier can see), and at equal depth
    the fresher verdict wins (that is how a fixed leaf clears its failure).
    """
    if fresh is None:
        return recorded
    if recorded is None:
        return fresh
    if str(fresh.get("result")) != PASS:
        return fresh
    return fresh if _verdict_depth(fresh) >= _verdict_depth(recorded) else recorded


def _observations(store: ResultStore) -> dict[str, dict[str, Any]]:
    """This session's best verdict per leaf, keyed by leaf id."""
    return {leaf_id: best for leaf_id, verdicts in store.entries().items() if (best := _best(verdicts)) is not None}


def _committed_verdicts() -> dict[str, dict[str, Any]]:
    """The last *recorded* verdict per leaf from the committed ledger.

    A §C4 entry may declare a tier without ever having been run, a ``not-run``
    entry is a recorded gap rather than a run, and a W4 ``tier: none``
    exclusion is not a verdict either; none of them counts as a recorded run.
    """
    recorded: dict[str, dict[str, Any]] = {}
    for entry in _recorded_ledger().get("leaves", []):
        if entry.get("result") in (PASS, FAIL) and entry.get("tier") != NONE:
            recorded[str(entry["id"])] = entry
    return recorded


def _ledger_entries(observations: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Build the §C4 entries for every declared leaf, and name the uncovered ones.

    A leaf with a fresh verdict carries it; a leaf this session did not
    exercise keeps the verdict of its last recorded run, so a tier that does
    not cover every leaf cannot silently drop one -- it can only leave its
    result stale. A leaf with neither has no recorded run.

    W4's ``tier: none`` exclusions are preserved verbatim and never require a
    run (PLAN-improvements §C4/§C5: unsupported leaves keep their reason).
    """
    committed = _committed_verdicts()
    exclusions = _exclusions()
    entries: list[dict[str, Any]] = []
    uncovered: list[str] = []
    for leaf in LEAVES:
        if leaf.id in exclusions:
            entries.append(
                {
                    "id": leaf.id,
                    "tier": NONE,
                    "result": EXCLUDED,
                    "reason": exclusions[leaf.id],
                    "answers": leaf.answers,
                }
            )
            continue
        verdict = _pick(observations.get(leaf.id), committed.get(leaf.id))
        if verdict is None:
            uncovered.append(leaf.id)
        entry: dict[str, Any] = {
            "id": leaf.id,
            "tier": _tier(leaf.id),
            "result": str(verdict["result"]) if verdict is not None else NOT_RUN,
            "answers": leaf.answers,
        }
        if verdict is not None:
            # Which tier's checks produced the recorded result (the `tier`
            # above is the leaf's declared tier, not the run's).
            entry["source"] = str(verdict.get("tier") or FAST)
        entries.append(entry)
    return entries, uncovered


@contextlib.contextmanager
def _ledger_lock() -> Generator[None, None, None]:
    """Serialize the ledger's read-modify-write across xdist workers."""
    LEDGER_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _write_ledger(entries: list[dict[str, Any]], uncovered: list[str]) -> dict[str, Any]:
    """Write tests/matrix/witnesses.json atomically and return its coverage block."""
    executed = [entry for entry in entries if entry["result"] not in (NOT_RUN, EXCLUDED)]
    coverage: dict[str, Any] = {
        "total": len(entries),
        "executed_fast": len(executed),
        "executed_full": len([entry for entry in executed if entry.get("source") == FULL]),
        "none": len([entry for entry in entries if entry["tier"] == NONE]),
        "unexecuted": uncovered,
    }
    payload = {"leaves": sorted(entries, key=lambda entry: entry["id"]), "coverage": coverage}
    LEDGER_SCRATCH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_SCRATCH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    Path(LEDGER_SCRATCH).replace(COVERAGE)
    return coverage


def _merge_verdict(verdict: dict[str, Any]) -> None:
    """Merge one fresh verdict into the ledger, under the ledger lock."""
    with _ledger_lock():
        entries, uncovered = _ledger_entries({str(verdict["id"]): verdict})
        _write_ledger(entries, uncovered)


def _await_runs(store: ResultStore, pending: list[str]) -> None:
    """Give sibling xdist workers a bounded chance to record the pending leaves.

    Only called for leaves some test in this session can actually exercise (a
    regenerated witness list): with a committed ledger there is nothing
    pending, and a run that never selects a leaf's case has nothing to wait
    for.
    """
    deadline = time.monotonic() + COVERAGE_GRACE
    while pending and time.monotonic() < deadline:
        time.sleep(1.0)
        recorded = store.entries()
        pending = [leaf_id for leaf_id in pending if leaf_id not in recorded]


def _session_targets(request: pytest.FixtureRequest) -> set[str]:
    """The leaves a test in this session can record a verdict for."""
    targets: set[str] = set()
    for item in request.session.items:
        callspec = getattr(item, "callspec", None)
        if callspec is not None and "leaf_id" in callspec.params:
            targets.add(str(callspec.params["leaf_id"]))
    return targets


@pytest.mark.fast
def test_witness_coverage(witness_results: ResultStore, request: pytest.FixtureRequest):
    """Every declared leaf has a recorded run; write the §C4 coverage artifact."""
    exclusions = _exclusions()
    known = set(_committed_verdicts()) | set(_observations(witness_results))
    runnable = _session_targets(request)
    pending = [leaf.id for leaf in LEAVES if leaf.id not in exclusions and leaf.id not in known and leaf.id in runnable]
    if pending:
        _await_runs(witness_results, pending)

    with _ledger_lock():
        entries, uncovered = _ledger_entries(_observations(witness_results))
        coverage = _write_ledger(entries, uncovered)
    assert coverage["total"] == len(LEAVES), f"{COVERAGE.name} lost a leaf: {coverage} vs {len(LEAVES)} declared"

    assert not uncovered, (
        f"{len(uncovered)} of {len(LEAVES)} witness leaves have no recorded run: {uncovered[:20]}"
        + (f" (and {len(uncovered) - 20} more)" if len(uncovered) > 20 else "")
        + f"\nrun them with: pytest {Path(__file__).name} -m fast"
    )
