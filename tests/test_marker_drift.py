"""Guards against the test suite's cost tiers drifting away from their names.

Three drifts cost the most time and none of them fails anything by itself:

marker debt
    A test that builds a virtualenv or hits the network without ``heavy``
    (plus ``network``) leaks into the edit loop's ``-m "not heavy and not
    slow and not meta"`` selection. Every such test is marked today; nothing
    stops the next one from being unmarked, and the edit loop just gets
    slower.
tier membership
    tests/matrix/tiers.json records, per tier, the marker expression that
    tier passes to pytest and the node ids it collected when the record was
    written. A test that changes tiers without the record changing is a
    membership change nobody chose, so the check re-collects each tier --
    collection only, no test runs -- and fails on the difference.
stale cost
    ``wall_seconds`` is the human half of that ledger: collection cannot time
    a tier, so a measurement that a growing suite has outgrown is invisible to
    every other check. An entry whose ``measured`` date is older than
    ``STALENESS_DAYS`` fails and names the command to re-measure with.

The task tiers come from Taskfile.yml and the witness tier from
.github/workflows/witness.yml (its expression and job timeout are read back
from the workflow, exactly as the tasks' are from the Taskfile). This module
is itself marked ``meta`` and runs in its own CI job: re-collecting every tier
means one pytest startup each, which is work the edit loop's budget cannot
afford.

The marker scan is structural (``ast``), not textual: it classifies the
commands a test actually builds and follows same-module helpers, fixtures, and
``from <module> import <name>`` edges, so a ``uv sync`` hidden one call deep is
still seen. It pins no counts; the ledger does, where a change is a deliberate
re-record::

    UPDATE_TIERS=1 uv run --no-sync pytest -q tests/test_marker_drift.py

That rewrites the collected sets *and* the Tests column of the tier table in
docs/how-to/test-loop.md, so the documented counts are no longer the hand-edited
half of a re-record (the step that was forgotten, and that merges kept
conflicting on). ``wall_seconds`` and ``measured`` stay for whoever ran the tier
to fill in, and the doc check below stays as the verifier of that rewrite: a
count the ledger does not hold still fails, naming the row.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC
from datetime import date
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_witness_matrix.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools import z3_witnesses  # noqa: E402

TESTS = TOP / "tests"
LEDGER = TESTS / "matrix" / "tiers.json"
TASKFILE = TOP / "Taskfile.yml"
WITNESS = TOP / ".github" / "workflows" / "witness.yml"
DOC = TOP / "docs" / "how-to" / "test-loop.md"

# Everything here is `meta`: re-collecting every tier starts one pytest session
# per tier, and the edit loop's 30s budget cannot afford its own guard. The
# selection `-m "not heavy and not slow and not meta"` is what Taskfile.yml's
# `test-fast` runs, and .github/workflows/ci.yml runs this module as its own
# job.
pytestmark = pytest.mark.meta

# The tier tasks of Taskfile.yml. The marker expression each one runs is read
# back from the Taskfile, so the ledger cannot claim a selection the task does
# not use; a renamed or removed task fails the ledger check on purpose.
TIER_TASKS = ("test-fast", "test-slow", "test-heavy", "test-randomly", "test-meta", "test")

# The witness tiers of .github/workflows/witness.yml, as ledger name -> job
# name. They are not Taskfile tasks: the job runs its pytest command itself, so
# the expression and the test path are read back from the workflow instead.
WITNESS_JOBS = {"witness-fast": "fast"}

MARKER_HEAVY = "heavy"
MARKER_NETWORK = "network"

# A wall time is an observation of a suite that grows and a machine that
# changes, so an entry measured longer ago than this is re-measured rather than
# cited. The date is the one in the ledger's own `measured` column.
STALENESS_DAYS = 30

# The witness leaf space (tools/z3_witnesses.build(), rendered end to end by the
# fast job of .github/workflows/witness.yml) has a declared ceiling, not just a
# growth rate. TODO.md §24.1's law makes ordinary growth additive -- +76 leaves
# per include layer, +22 per gate-off dimension -- but lifting include
# exclusivity turns the layer multiplier into a combinatorial product:
# exponential growth that would otherwise surface only as that job creeping
# toward its 30-minute timeout. 450 was twice the 225-leaf space the budget
# landed with (228 leaves as of 2026-09-16), so the additive increments fit
# several times over and only a multiplicative change trips it. Crossing the
# budget is a decision -- raise this constant and
# re-measure the witness job's wall time into tests/matrix/tiers.json -- not an
# accident a slow CI run discovers.
LEAF_BUDGET = 450

# Commands that build a project virtualenv, and commands that need the wire.
# The two are not the same set: `uv run` uses a project environment without
# resolving anything new, `uvx` fetches a tool without building one, and the
# installers do both.
VENV_COMMANDS = (
    ("uv", "sync"),
    ("uv", "lock"),
    ("uv", "venv"),
    ("uv", "add"),
    ("uv", "run"),
    ("uv", "pip"),
    ("pip", "install"),
    ("poetry", "install"),
    ("pixi", "install"),
    ("python", "-m", "venv"),
)
NETWORK_COMMANDS = (
    ("uv", "sync"),
    ("uv", "lock"),
    ("uv", "add"),
    ("uvx",),
    ("pip", "install"),
    ("poetry", "install"),
    ("pixi", "install"),
    ("git", "clone"),
    ("git", "fetch"),
    ("git", "pull"),
    ("git", "ls-remote"),
)
# A helper whose *name* says venv (``make_venv`` in tests/support.py, reached
# from test_task_runners.py by import) is a venv build whatever it does inside.
VENV_HELPER = re.compile(r"venv")
# A bare URL is the network only where something is asked to fetch it: as a
# copier source, or handed to an opener. A URL in any other argument (a fake
# ``Host`` allowlist, a rendered answers file) is data, and a URL inside a
# larger payload never matches: the whole literal has to be the URL.
BARE_URL = re.compile(r"(?:https?|git\+https?|ssh)://\S+")
URL_ARGUMENTS = {"src_path", "url", "src", "repo", "remote"}
URL_CALLS = {"run_copy", "run_update", "urlopen", "urlretrieve"}


@dataclass(frozen=True)
class Work:
    """Expensive work found inside one function body, with its evidence.

    ``evidence`` entries name the function that performs the call, so merging
    two of these is a union: the resolver runs merges to a fixpoint, and a
    lattice that grows on every merge would never reach one.
    """

    venv: bool = False
    network: bool = False
    evidence: frozenset[str] = frozenset()

    def merge(self, other: Work) -> Work:
        """This work plus `other`'s."""
        return Work(
            venv=self.venv or other.venv,
            network=self.network or other.network,
            evidence=self.evidence | other.evidence,
        )

    def markers(self) -> set[str]:
        """The markers this work requires of the test that performs it."""
        required = set()
        if self.venv:
            required.add(MARKER_HEAVY)
        if self.network:
            required.add(MARKER_NETWORK)
        return required


def _literal_text(node: ast.AST) -> str | None:
    """The literal text of a str/JoinedStr/list-of-str argument, else None.

    f-strings keep their literal parts and drop the interpolations, so
    ``f"git clone -q {path}"`` still reads as a clone; a list of strings joins
    into the argv a subprocess gets.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_literal_text(value) or " " for value in node.values)
    if isinstance(node, (ast.List, ast.Tuple)):
        parts = [_literal_text(element) for element in node.elts]
        if any(part is None for part in parts):
            return None
        return " ".join(part.strip() for part in parts if part and part.strip())
    return None


def _call_name(call: ast.Call) -> str | None:
    """The simple name a call is made through: ``f(...)`` or ``obj.f(...)``."""
    target = call.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _split(text: str) -> list[str]:
    """Shell-split a literal command; an unbalanced quote is not a command."""
    try:
        return shlex.split(text)
    except ValueError:
        return []


def _is_remote_source(callee: str | None, keyword: str | None, text: str) -> bool:
    """True if this argument asks something to fetch `text`."""
    if not BARE_URL.fullmatch(text.strip()):
        return False
    return keyword in URL_ARGUMENTS or callee in URL_CALLS


def _work_of_call(call: ast.Call, owner: str) -> Work:
    """The expensive work one call performs, from its name and its literals."""
    venv = False
    network = False
    evidence = []
    name = _call_name(call)
    if name is not None and VENV_HELPER.search(name):
        venv = True
        evidence.append(f"{owner} line {call.lineno}: {name}() builds a virtualenv")
    arguments = [(None, argument) for argument in call.args]
    arguments += [(keyword.arg, keyword.value) for keyword in call.keywords]
    for keyword, argument in arguments:
        text = _literal_text(argument)
        if text is None:
            continue
        if _is_remote_source(name, keyword, text):
            network = True
            evidence.append(f"{owner} line {call.lineno}: fetches {text.strip()}")
        tokens = _split(text)
        if not tokens:
            continue
        if any((tuple(tokens[: len(pattern)]) == pattern) for pattern in VENV_COMMANDS):
            venv = True
            evidence.append(f"{owner} line {call.lineno}: runs `{text.strip()}` (project venv)")
        if any((tuple(tokens[: len(pattern)]) == pattern) for pattern in NETWORK_COMMANDS):
            network = True
            evidence.append(f"{owner} line {call.lineno}: runs `{text.strip()}` (network)")
    return Work(venv=venv, network=network, evidence=frozenset(evidence))


def _work_in(node: ast.AST, owner: str) -> Work:
    """The work a body performs directly, nested helper definitions included.

    A test that defines a local runner and calls it is still the test that
    builds the venv, so nested definitions count as part of their enclosing
    body rather than as separate nodes of the graph.
    """
    work = Work()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            work = work.merge(_work_of_call(child, owner))
    return work


def _markers_in(node: ast.AST) -> set[str]:
    """Marker names declared in a decorator or ``pytestmark`` value."""
    found = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr in {MARKER_HEAVY, MARKER_NETWORK}:
            parent = child.value
            if (isinstance(parent, ast.Attribute) and parent.attr == "mark") or (
                isinstance(parent, ast.Name) and parent.id == "mark"
            ):
                found.add(child.attr)
    return found


def _decorators(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    found: set[str] = set()
    for decorator in node.decorator_list:
        found |= _markers_in(decorator)
    return found


def _parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    arguments = node.args
    names = {argument.arg for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]}
    if arguments.vararg:
        names.add(arguments.vararg.arg)
    if arguments.kwarg:
        names.add(arguments.kwarg.arg)
    return names - {"self", "cls"}


@dataclass
class _Function:
    """One module-level (or class-level) function and what it reaches."""

    node: ast.FunctionDef | ast.AsyncFunctionDef
    name: str
    markers: set[str]
    parameters: set[str]
    calls: set[str]
    work: Work

    @property
    def is_test(self) -> bool:
        return self.name.startswith("test_")


@dataclass
class _Module:
    """One scanned test module: its functions, module marks and imports."""

    path: Path
    functions: dict[str, _Function]
    marks: set[str]
    work: Work
    imports: dict[str, tuple[str, str]]  # local name -> (module stem, name there)
    scope_calls: set[str]  # names called while the module itself is imported


def _scan(path: Path) -> _Module:
    """Parse one module into the graph the resolver propagates over."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions: dict[str, _Function] = {}
    imports: dict[str, tuple[str, str]] = {}
    marks: set[str] = set()
    work = Work()
    scope_calls: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[statement.name] = _Function(
                node=statement,
                name=statement.name,
                markers=_decorators(statement),
                parameters=_parameters(statement),
                calls=set(_called_names(statement)),
                work=_work_in(statement, statement.name),
            )
        elif isinstance(statement, ast.ClassDef):
            for child in statement.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions[child.name] = _Function(
                        node=child,
                        name=child.name,
                        markers=_decorators(child),
                        parameters=_parameters(child),
                        calls=set(_called_names(child)),
                        work=_work_in(child, child.name),
                    )
        elif isinstance(statement, ast.ImportFrom) and statement.module:
            for alias in statement.names:
                imports[alias.asname or alias.name] = (statement.module.split(".")[-1], alias.name)
        elif isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in statement.targets
        ):
            marks |= _markers_in(statement.value)
        else:
            work = work.merge(_work_in(statement, path.name))
            scope_calls |= set(_called_names(statement))
    return _Module(path=path, functions=functions, marks=marks, work=work, imports=imports, scope_calls=scope_calls)


def _called_names(node: ast.AST) -> Iterator[str]:
    """Every simple name called from inside a body."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _call_name(child)
            if name is not None:
                yield name


def _resolve(modules: dict[str, _Module]) -> None:
    """Propagate work along call and fixture edges until nothing changes."""
    changed = True
    while changed:
        changed = False
        for module in modules.values():
            for name in module.scope_calls:
                source = _source_of(modules, module, name)
                if source is None:
                    continue
                merged = module.work.merge(source.work)
                if merged != module.work:
                    module.work = merged
                    changed = True
            for function in module.functions.values():
                reached = set(function.calls)
                reached |= function.parameters
                for name in reached:
                    source = _source_of(modules, module, name)
                    if source is None or source is function:
                        continue
                    merged = function.work.merge(source.work)
                    if merged != function.work:
                        function.work = merged
                        changed = True


def _source_of(modules: dict[str, _Module], module: _Module, name: str) -> _Function | None:
    """The scanned function a name refers to: local, imported, or a shared fixture."""
    local = module.functions.get(name)
    if local is not None:
        return local
    target = module.imports.get(name)
    if target is not None:
        other = modules.get(target[0])
        if other is not None:
            return other.functions.get(target[1])
    # A fixture in conftest.py is requestable by name from every module without
    # an import (that is what conftest means), so it is the last place to look.
    conftest = modules.get("conftest")
    return None if conftest is None else conftest.functions.get(name)


@cache
def _modules() -> dict[str, _Module]:
    """Every scanned test module, with work propagated exactly once.

    tests/render_cache.py and tests/conftest.py hold fixtures, not tests, but a
    fixture that builds a venv would cost whatever requests it -- so they are
    scanned too and followed through ``from <module> import <name>``. The scan
    runs on first use, not at import: a sibling module that does not parse is a
    failure of the test below, not an unimportable guard.
    """
    scanned = {path.stem: _scan(path) for path in sorted(TESTS.glob("*.py"))}
    _resolve(scanned)
    return scanned


def _unmarked_work() -> list[str]:
    """One entry per test that performs expensive work without its markers."""
    problems = []
    for module in _modules().values():
        location = str(module.path.relative_to(TOP))
        required = module.work.markers() - module.marks
        if required:
            problems.append(
                f"{location} (module scope, runs at import) -- missing module-level pytestmark for: {_names(required)}\n"
                + "\n".join(f"      {item}" for item in sorted(module.work.evidence))
            )
        for function in module.functions.values():
            if not function.is_test:
                continue
            required = function.work.markers() - (function.markers | module.marks)
            if not required:
                continue
            problems.append(
                f"{location}::{function.name} -- missing: {_names(required)}\n"
                + "\n".join(f"      {item}" for item in sorted(function.work.evidence))
            )
    return problems


def _names(markers: set[str]) -> str:
    """The missing markers, in the order the tiers read them."""
    return ", ".join(name for name in (MARKER_HEAVY, MARKER_NETWORK) if name in markers)


def test_the_randomized_tier_is_the_only_place_the_plugin_pays() -> None:
    """pytest-randomly is installed but inert everywhere except `task test-randomly`.

    The plugin is a dev dependency for the nightly seed job alone (TODO §24.3,
    §27.4: conditional adopt, the edit loop must not pay for the reshuffle), so
    the addopts block it globally and exactly one task re-enables it on its own
    command line (later `-p` arguments unblock earlier `no:` ones). If a second
    task starts paying for it, that is a tier-budget change and belongs in the
    ledger deliberately.
    """
    addopts = tomllib.loads((TOP / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"][
        "addopts"
    ]
    assert "-p no:randomly" in addopts, "addopts must keep the randomly plugin inert by default"
    tasks = yaml.safe_load(TASKFILE.read_text(encoding="utf-8"))["tasks"]
    payers = [name for name, task in tasks.items() if "-p randomly" in str(task.get("cmd", ""))]
    assert payers == ["test-randomly"], f"only the nightly seed task may re-enable the plugin, found: {payers}"


def test_venv_and_network_work_carries_the_markers_that_keep_it_out_of_the_edit_loop() -> None:
    """A test that builds a venv / uses the network must say so with markers.

    ``heavy`` keeps it out of the edit loop's ``-m "not heavy and not slow and
    not meta"``; ``network`` says it needs the wire. The scan is structural, so
    the fix is to mark the test (or move the work to a helper the test does not
    call).
    """
    problems = _unmarked_work()
    assert not problems, (
        f"{len(problems)} test(s) do expensive work without the markers that declare it:\n\n"
        + "\n\n".join(problems)
        + "\n\nmark them `@pytest.mark.heavy` (and `@pytest.mark.network` when the work needs the wire), "
        + "or make the expensive call reachable only from tests that carry both."
    )


# A module whose tests cover each way the scan decides, and each way it must not:
# the guard is the deliverable here, so its judgement is pinned by a probe
# rather than trusted.
PROBE = """
import pytest

from copier import run_copy

from support import run_pipe


def _provisioned(project):
    run_pipe(f"uv sync", cwd=str(project))


@pytest.fixture
def provisioned(tmp_path):
    _provisioned(tmp_path)
    return tmp_path


def test_venv_through_a_helper(tmp_path):
    _provisioned(tmp_path)


def test_venv_through_a_fixture(provisioned):
    assert provisioned


def test_remote_source():
    run_copy(src_path="https://github.com/other/template.git", dst_path=".")


def test_shell_clone(tmp_path):
    run_pipe(f"git clone -q https://github.com/other/template.git {tmp_path}")


def test_local_git_init(tmp_path):
    run_pipe(f"git init {tmp_path}")


def test_fake_hosts_are_not_a_fetch(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "https://a.example,https://b.example")


def test_answers_file_is_not_a_fetch(tmp_path):
    (tmp_path / ".copier-answers.yml").write_text("_src_path: https://github.com/other/template.git\\n")


def test_marked(monkeypatch):
    run_pipe("uvx twine check dist/*")
"""


def test_the_scan_judges_helpers_fixtures_and_data_not_network(tmp_path: Path) -> None:
    """The scan's verdicts, on a module written to exercise each one: probes like
    this are how the repository keeps a detector honest (see
    tests/test_copier_structure.py's injected-bug meta tests).

    A test reaches the work through a helper or a fixture, a URL only counts
    where something is asked to fetch it, and a marked test is left alone.
    """
    path = tmp_path / "test_probe.py"
    path.write_text(PROBE, encoding="utf-8")
    module = _scan(path)
    _resolve({"test_probe": module})
    judged = {name: function.work.markers() for name, function in module.functions.items()}
    assert judged == {
        "_provisioned": {MARKER_HEAVY, MARKER_NETWORK},
        "provisioned": {MARKER_HEAVY, MARKER_NETWORK},
        "test_venv_through_a_helper": {MARKER_HEAVY, MARKER_NETWORK},
        "test_venv_through_a_fixture": {MARKER_HEAVY, MARKER_NETWORK},
        "test_remote_source": {MARKER_NETWORK},
        "test_shell_clone": {MARKER_NETWORK},
        "test_local_git_init": set(),
        "test_fake_hosts_are_not_a_fetch": set(),
        "test_answers_file_is_not_a_fetch": set(),
        "test_marked": {MARKER_NETWORK},
    }, "the scan's classification of the probe module changed"


# --------------------------------------------------------------------------- #
# the cost ledger: the tiers' collected sets, checked by collection only.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Selection:
    """What a tier passes to pytest: a path (None for the whole suite) and a marker expression."""

    path: str | None
    expression: str


def _task_expressions() -> dict[str, str]:
    """The marker expression each tier task passes to pytest, from the Taskfile."""
    tasks = yaml.safe_load(TASKFILE.read_text(encoding="utf-8"))["tasks"]
    expressions = {}
    for name in TIER_TASKS:
        assert name in tasks, f"Taskfile.yml has no `{name}` task: the tier ledger names one that is gone"
        command = str(tasks[name]["cmd"])
        match = re.search(r'-m "([^"]*)"|-m (\S+)', command)
        expressions[name] = (match.group(1) or match.group(2)) if match else ""
    return expressions


def _witness_job(name: str) -> dict[str, Any]:
    """The .github/workflows/witness.yml job a witness ledger row names."""
    workflow = yaml.safe_load(WITNESS.read_text(encoding="utf-8"))
    job = WITNESS_JOBS[name]
    assert job in workflow["jobs"], f"{WITNESS.name} has no `{job}` job: the ledger names one that is gone"
    return workflow["jobs"][job]


def _witness_selection(name: str) -> _Selection:
    """What the witness job's pytest step passes, read back from the workflow.

    The job runs pytest itself (it is not a Taskfile task), so its expression
    and test path are recovered from the step's own argv: the ledger cannot
    record a selection the job does not run.
    """
    for step in _witness_job(name)["steps"]:
        args = shlex.split(str(step.get("run", "")))
        if "pytest" in args:
            rest = args[args.index("pytest") + 1 :]
            return _Selection(
                path=next((arg for arg in rest if arg.endswith(".py")), None),
                expression=rest[rest.index("-m") + 1] if "-m" in rest else "",
            )
    msg = f"{WITNESS.name}'s {WITNESS_JOBS[name]!r} job runs no pytest step"
    raise AssertionError(msg)


def _witness_timeout(name: str) -> int:
    """The job timeout, in seconds, that witness tier's measured cost must fit inside."""
    return int(_witness_job(name)["timeout-minutes"]) * 60


def _selections() -> dict[str, _Selection]:
    """Every recorded tier's pytest selection, task tiers and witness tier alike."""
    selections = {
        name: _Selection(path=None, expression=expression) for name, expression in _task_expressions().items()
    }
    return {name: _witness_selection(name) for name in WITNESS_JOBS} | selections


def _collect(selection: _Selection) -> list[str]:
    """The node ids pytest collects for one tier (collection only, no runs)."""
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",  # `-vv -n auto` only makes this output harder to read
        "-p",
        "no:cacheprovider",  # several of these run at once: no cache to share
        "--collect-only",
        "-q",
    ]
    if selection.path:
        argv.append(selection.path)
    if selection.expression:
        argv += ["-m", selection.expression]
    proc = subprocess.run(argv, cwd=TOP, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, (
        f"pytest cannot collect `{selection.path or '.'} -m {selection.expression!r}` -- the tier is "
        f"uncollectable, so its cost is unknown:\n{proc.stdout[-4000:]}{proc.stderr[-4000:]}"
    )
    return [line for line in proc.stdout.splitlines() if line.startswith("tests/") and "::" in line]


def _summarize(ids: list[str]) -> dict[str, object]:
    """The recorded shape of one tier: its size, per-file split, and digest."""
    files: dict[str, int] = {}
    for node_id in ids:
        files[node_id.split("::", 1)[0]] = files.get(node_id.split("::", 1)[0], 0) + 1
    return {
        "collected": len(ids),
        "files": dict(sorted(files.items())),
        "ids_sha256": hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest(),
    }


def _load_ledger() -> dict[str, dict[str, object]]:
    return json.loads(LEDGER.read_text(encoding="utf-8"))["tiers"]


def _load_witness() -> dict[str, dict[str, object]]:
    return json.loads(LEDGER.read_text(encoding="utf-8"))["witness"]


def _cost_entries() -> dict[str, dict[str, object]]:
    """Every hand-measured cost row: the task tiers and the witness tiers."""
    return {**_load_ledger(), **_load_witness()}


def _live_tiers() -> dict[str, tuple[list[str], dict[str, object]]]:
    """Collect every recorded tier once, in parallel: one pytest startup each."""
    selections = _selections()
    with ThreadPoolExecutor(max_workers=len(selections)) as pool:
        collected = dict(zip(selections, pool.map(_collect, selections.values()), strict=True))
    return {name: (ids, _summarize(ids)) for name, ids in collected.items()}


def _changes(recorded: dict[str, object], live: dict[str, object]) -> list[str]:
    """How a tier's collected set differs from the recorded one, in words."""
    lines = []
    if recorded.get("collected") != live["collected"]:
        lines.append(f"  size: recorded {recorded.get('collected')}, collected {live['collected']}")
    before, after = recorded.get("files"), live["files"]
    if isinstance(before, dict) and isinstance(after, dict):
        lines += [
            f"  {path}: {before.get(path, 0)} -> {after.get(path, 0)}"
            for path in sorted(set(before) | set(after))
            if before.get(path, 0) != after.get(path, 0)
        ]
    if recorded.get("ids_sha256") != live["ids_sha256"]:
        lines.append("  the node ids changed (same size and files: a rename or a re-parametrization)")
    return lines


def _update_ledger(live: dict[str, tuple[list[str], dict[str, object]]]) -> list[str]:
    """Rewrite the collected sets and the doc's tier counts, keeping the human columns.

    ``wall_seconds``, ``measured``, the timeout, the command and the note are
    the human half of the record: a tier that has never been run keeps its null
    time and empty note rather than looking measured. The count columns the
    re-record used to leave for a hand edit -- the Tests cells of
    docs/how-to/test-loop.md's tier table -- are rewritten here too, so the
    hand step cannot be the forgotten half. Returns one line per doc row whose
    stated count moved, for the skip message.
    """
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    selections = _selections()
    for name, (_ids, summary) in live.items():
        witness = name in WITNESS_JOBS
        previous = ledger["witness" if witness else "tiers"].get(name, {})
        identity = {"workflow": str(WITNESS.relative_to(TOP)), "job": WITNESS_JOBS[name]} if witness else {"task": name}
        collected = {
            "expression": selections[name].expression,
            "collected": summary["collected"],
            "files": summary["files"],
            "ids_sha256": summary["ids_sha256"],
        }
        measured = {
            "wall_seconds": previous.get("wall_seconds"),
            "measured": previous.get("measured", ""),
            **({"timeout_seconds": previous.get("timeout_seconds")} if witness else {}),
            "command": previous.get("command", ""),
            "note": previous.get("note", ""),
        }
        ledger["witness" if witness else "tiers"][name] = identity | collected | measured
    LEDGER.write_text(json.dumps(ledger, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return _update_doc_counts(live)


def _doc_cells(line: str) -> list[str]:
    """The cells of a markdown table row in docs/how-to/test-loop.md (empty for a non-row)."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _doc_tier_row(cells: list[str]) -> str | None:
    """The tier a docs/how-to/test-loop.md table row documents, else None.

    The tier table is ``| Tier | Command | Tests | Wall time |``: a row belongs
    to a tier when its Command cell is `` `task <name>` ``. The page's other
    tables mention tasks too, but never in that column. The doc check and the
    UPDATE_TIERS rewrite share this predicate, so the two cannot drift apart
    about which rows carry the counts.
    """
    if len(cells) < 3:
        return None
    for name in TIER_TASKS:
        if cells[1].strip("`") == f"task {name}":
            return name
    return None


def _update_doc_counts(live: dict[str, tuple[list[str], dict[str, object]]]) -> list[str]:
    """Rewrite the Tests column of the doc's tier table from the live collection.

    Only that column: a wall time is a measurement a human records, not a
    projection, so the Wall time cells are left exactly as written. Rows whose
    count already agrees are left byte-identical. Returns one line per row
    whose stated count moved, for the skip message.
    """
    counts = {name: str(live[name][1]["collected"]) for name in TIER_TASKS}
    changed = []
    lines = DOC.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        cells = _doc_cells(line)
        name = _doc_tier_row(cells)
        if name is None or cells[2] == counts[name]:
            continue
        changed.append(f"{DOC.name}:{index + 1}: `task {name}` {cells[2]} -> {counts[name]}")
        cells[2] = counts[name]
        lines[index] = "| " + " | ".join(cells) + " |"
    if changed:
        DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def _cost_problems(name: str, entry: dict[str, object]) -> list[str]:
    """The human columns of one row, judged: a measured time, a date, its command."""
    problems = []
    seconds = entry.get("wall_seconds")
    if not isinstance(seconds, (int, float)) or float(seconds) <= 0:
        problems.append(f"{name}: wall_seconds is not a measured cost ({seconds!r})")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(entry.get("measured", ""))):
        problems.append(f"{name}: measured is not a date ({entry.get('measured')!r})")
    command, expression = entry.get("command"), str(entry.get("expression", ""))
    if not isinstance(command, str) or not command.strip():
        problems.append(f"{name}: command is not the re-measure command ({command!r})")
    elif expression and f"-m {expression}" not in command and f'-m "{expression}"' not in command:
        problems.append(f"{name}: command {command!r} does not select {expression!r}")
    return problems


def test_tier_ledger_records_the_selection_each_task_claims() -> None:
    """tests/matrix/tiers.json must name the tiers and expressions the tasks use.

    The expressions come from Taskfile.yml, so the ledger cannot claim a
    selection the task does not run; the times are the human half of the record
    and must look measured (a number, a date, and the command it was measured
    with) rather than inferred here.
    """
    if os.environ.get("UPDATE_TIERS"):
        pytest.skip("UPDATE_TIERS set: the ledger is being rewritten; re-run without it to check it")
    expressions = _task_expressions()
    ledger = _load_ledger()
    assert set(ledger) == set(TIER_TASKS), (
        f"the ledger records {sorted(ledger)}, Taskfile.yml declares {sorted(TIER_TASKS)}: "
        "one tier was renamed or added without the other"
    )
    problems = []
    for name in TIER_TASKS:
        if ledger[name].get("expression") != expressions[name]:
            problems.append(
                f"{name}: the ledger says {ledger[name].get('expression')!r}, `{name}` runs {expressions[name]!r}"
            )
        problems += _cost_problems(name, ledger[name])
    assert not problems, (
        f"{LEDGER.relative_to(TOP)} no longer describes the tiers Taskfile.yml runs:\n  " + "\n  ".join(problems)
    )


def test_witness_ledger_records_the_selection_its_workflow_runs() -> None:
    """A witness row must name the CI job that runs it, its selection and its timeout.

    A witness tier is a job in .github/workflows/witness.yml, not a Taskfile
    task, so its row is checked against that job instead: the expression of the
    pytest step, and the job timeout the measured time has to sit inside. The
    measured time itself is a local observation -- the job's wall in CI also
    carries checkout and the venv -- so the row records the timeout, not the
    other way round.
    """
    if os.environ.get("UPDATE_TIERS"):
        pytest.skip("UPDATE_TIERS set: the ledger is being rewritten; re-run without it to check it")
    ledger = _load_witness()
    assert set(ledger) == set(WITNESS_JOBS), (
        f"the ledger records {sorted(ledger)}, WITNESS_JOBS names {sorted(WITNESS_JOBS)}: "
        "one witness tier was renamed or added without the other"
    )
    problems = []
    for name, job in WITNESS_JOBS.items():
        entry = ledger[name]
        selection = _witness_selection(name)
        if (entry.get("workflow"), entry.get("job")) != (str(WITNESS.relative_to(TOP)), job):
            problems.append(
                f"{name}: the ledger points at {entry.get('workflow')!r}#{entry.get('job')!r}, "
                f"WITNESS_JOBS points at {WITNESS.name}#{job}"
            )
        if entry.get("expression") != selection.expression:
            problems.append(
                f"{name}: the ledger says {entry.get('expression')!r}, the job runs {selection.expression!r}"
            )
        timeout = entry.get("timeout_seconds")
        if timeout != _witness_timeout(name):
            problems.append(f"{name}: the ledger allows {timeout!r}s, the job's timeout is {_witness_timeout(name)}s")
        problems += _cost_problems(name, entry)
    assert not problems, (
        f"{LEDGER.relative_to(TOP)} no longer describes the witness jobs {WITNESS.name} runs:\n  "
        + "\n  ".join(problems)
    )


def test_each_tier_collects_what_the_ledger_records() -> None:
    """The collected set of every recorded tier must still be the one on record.

    A tier's cost is a property of the selection, and the selection is decided
    by markers on tests (and, for the witness tier, by the path and expression
    of the job's own pytest step). A test that joins or leaves a tier without
    the record moving is an unexplained cost change, so this re-collects (no
    runs) and names the files that moved. Re-record deliberately with
    UPDATE_TIERS=1.
    """
    live = _live_tiers()
    if os.environ.get("UPDATE_TIERS"):
        rewritten = _update_ledger(live)
        pytest.skip(
            f"rewrote {LEDGER.relative_to(TOP)} and the Tests column of {DOC.relative_to(TOP)} "
            "(fill wall_seconds/measured by hand)"
            + (":\n  " + "\n  ".join(rewritten) if rewritten else "; the doc's counts already matched")
        )
    ledger = _cost_entries()
    problems = []
    for name, (_ids, summary) in live.items():
        changes = _changes(ledger.get(name, {}), summary)
        if changes:
            problems.append(f"{name} (-m {ledger.get(name, {}).get('expression')!r}):\n" + "\n".join(changes))
    assert not problems, (
        "the tiers no longer collect what tests/matrix/tiers.json records:\n\n"
        + "\n\n".join(problems)
        + "\n\nif the change is deliberate, re-record the ledger and the doc counts in one step "
        + "(only wall_seconds/measured are filled in by hand):\n  "
        + "UPDATE_TIERS=1 uv run --no-sync pytest -q tests/test_marker_drift.py"
    )


def test_no_recorded_cost_is_stale() -> None:
    """A cost older than STALENESS_DAYS must be re-measured, not cited.

    ``wall_seconds`` is the human half of the ledger: nothing recomputes it, so
    a suite that has grown and a machine that has changed leave a number that
    still looks measured. The failure names the command the row was measured
    with, so re-measuring is a copy and paste rather than a search through the
    notes.
    """
    if os.environ.get("UPDATE_TIERS"):
        pytest.skip("UPDATE_TIERS set: the ledger's collected sets are being rewritten, not its costs")
    today = datetime.now(UTC).date()
    stale = []
    for section, entries in (("tiers", _load_ledger()), ("witness", _load_witness())):
        for name, entry in entries.items():
            measured = str(entry.get("measured", ""))
            try:
                age = (today - date.fromisoformat(measured)).days
            except ValueError:
                age = None
            if age is None or age > STALENESS_DAYS:
                stale.append(
                    f"  {name}: measured {measured!r}, "
                    + ("not a date" if age is None else f"{age} days ago")
                    + f" -- re-measure with\n      time {entry.get('command') or 'uv run --no-sync pytest -q -m <expression>'}\n"
                    + f"    then write that wall time into {LEDGER.relative_to(TOP)} -> "
                    + f'{section}."{name}".wall_seconds and {today.isoformat()} into its "measured"'
                )
    assert not stale, (
        f"these costs were measured more than {STALENESS_DAYS} days ago (today {today.isoformat()}):\n"
        + "\n".join(stale)
    )


def test_test_loop_doc_states_the_recorded_tier_sizes() -> None:
    """The tier table in docs/how-to/test-loop.md must match the ledger.

    The doc's wall times are measurements a human records; its test counts are
    the ledger's, and they are what this checks: a doc that promises a size the
    tier does not have is the §23.2 drift that started this ledger. UPDATE_TIERS
    writes these counts itself (``_update_doc_counts``, on the same row
    predicate this check reads); the check stays as the verifier of that
    rewrite, which is why it is skipped while the rewrite runs.
    """
    if os.environ.get("UPDATE_TIERS"):
        pytest.skip(
            "UPDATE_TIERS set: the doc's counts are being rewritten from the fresh ledger; re-run without it to check them"
        )
    ledger = _load_ledger()
    documented: dict[str, tuple[int, str]] = {}
    for number, line in enumerate(DOC.read_text(encoding="utf-8").splitlines(), start=1):
        cells = _doc_cells(line)
        # The tier table is `| Tier | Command | Tests | Wall time |`; read the
        # count from the column after the command.
        name = _doc_tier_row(cells)
        if name is not None:
            documented[name] = (number, cells[2])
    problems = []
    for name in TIER_TASKS:
        if name not in documented:
            problems.append(f"{DOC.name}: no row documenting `task {name}`")
            continue
        number, stated = documented[name]
        if stated != str(ledger[name]["collected"]):
            problems.append(
                f"{DOC.name}:{number}: `task {name}` says {stated} tests, the ledger records {ledger[name]['collected']}"
            )
    assert not problems, f"{DOC.relative_to(TOP)} contradicts {LEDGER.relative_to(TOP)}:\n  " + "\n  ".join(problems)


# --------------------------------------------------------------------------- #
# the leaf-space budget: §24.1's growth law, enforced at the enumerator.
# --------------------------------------------------------------------------- #


def test_the_witness_leaf_space_stays_within_its_declared_budget() -> None:
    """tools/z3_witnesses.py's leaf space must fit inside LEAF_BUDGET.

    Everything else in this module watches costs that already happened; this
    one watches the one growth that compounds. TODO.md §24.1's law makes
    ordinary growth additive -- one more include layer ≈ +76 leaves, one more
    gate-off dimension ≈ +22 -- but exponential if include exclusivity is
    lifted, and the witness fast job renders the whole space inside its
    30-minute CI timeout (.github/workflows/witness.yml), so unbounded growth
    would surface only as that job creeping toward its timeout. Exceeding the
    budget fails here instead, and raising it is the decision.
    """
    _leaf_space, leaves = z3_witnesses.build()
    # An int, not the comparison over `leaves` itself: pytest's assertion
    # rewriting would otherwise echo the whole leaf list into the failure.
    count = len(leaves)
    assert count <= LEAF_BUDGET, (
        f"the witness leaf space grew to {len(leaves)} leaves, over the declared budget of "
        f"{LEAF_BUDGET} (TODO.md §24.1: +1 include layer ≈ +76 leaves, +1 gate-off dimension ≈ +22, "
        "and include exclusivity lifted makes the growth exponential; the witness fast job must "
        "render every leaf inside its 30-minute timeout). If the growth is deliberate, raise "
        "LEAF_BUDGET in tests/test_marker_drift.py and re-measure the witness job's wall time into "
        "tests/matrix/tiers.json."
    )
