"""Guards against the test suite's cost tiers drifting away from their names.

Two drifts cost the most time and neither fails anything by itself:

marker debt
    A test that builds a virtualenv or hits the network without ``heavy``
    (plus ``network``) leaks into the edit loop's ``-m "not heavy and not
    slow"`` selection. Every such test is marked today; nothing stops the next
    one from being unmarked, and the edit loop just gets slower.
tier membership
    tests/matrix/tiers.json records, per tier task, the marker expression that
    task passes to pytest and the node ids it collected when the record was
    written. A test that changes tiers without the record changing is a
    membership change nobody chose, so the check re-collects each tier --
    collection only, no test runs -- and fails on the difference.

The marker scan is structural (``ast``), not textual: it classifies the
commands a test actually builds and follows same-module helpers, fixtures, and
``from <module> import <name>`` edges, so a ``uv sync`` hidden one call deep is
still seen. It pins no counts; the ledger does, where a change is a deliberate
re-record::

    UPDATE_TIERS=1 uv run --no-sync pytest -q tests/test_marker_drift.py

That rewrites the collected sets and says what changed; ``wall_seconds`` and
``measured`` stay for whoever ran the tier to fill in. The counts documented in
docs/how-to/test-loop.md are checked against the ledger, and the failure names
the rows to fix there.
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
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest
import yaml

TOP = Path(__file__).absolute().parent.parent
TESTS = TOP / "tests"
LEDGER = TESTS / "matrix" / "tiers.json"
TASKFILE = TOP / "Taskfile.yml"
DOC = TOP / "docs" / "how-to" / "test-loop.md"

# The tier tasks of Taskfile.yml. The marker expression each one runs is read
# back from the Taskfile, so the ledger cannot claim a selection the task does
# not use; a renamed or removed task fails the ledger check on purpose.
TIER_TASKS = ("test-fast", "test-slow", "test-heavy", "test")

MARKER_HEAVY = "heavy"
MARKER_NETWORK = "network"

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
# A helper whose *name* says venv (``make_venv`` in test_example.py, reached
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


def test_venv_and_network_work_carries_the_markers_that_keep_it_out_of_the_edit_loop() -> None:
    """A test that builds a venv / uses the network must say so with markers.

    ``heavy`` keeps it out of the edit loop's ``-m "not heavy and not slow"``;
    ``network`` says it needs the wire. The scan is structural, so the fix is to
    mark the test (or move the work to a helper the test does not call).
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

from test_example import run_pipe


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


def _tier_expressions() -> dict[str, str]:
    """The marker expression each tier task passes to pytest, from the Taskfile."""
    tasks = yaml.safe_load(TASKFILE.read_text(encoding="utf-8"))["tasks"]
    expressions = {}
    for name in TIER_TASKS:
        assert name in tasks, f"Taskfile.yml has no `{name}` task: the tier ledger names one that is gone"
        command = str(tasks[name]["cmd"])
        match = re.search(r'-m "([^"]*)"|-m (\S+)', command)
        expressions[name] = (match.group(1) or match.group(2)) if match else ""
    return expressions


def _collect(expression: str) -> list[str]:
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
    if expression:
        argv += ["-m", expression]
    proc = subprocess.run(argv, cwd=TOP, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, (
        f"pytest cannot collect `-m {expression!r}` -- the tier is uncollectable, so its cost is unknown:\n"
        f"{proc.stdout[-4000:]}{proc.stderr[-4000:]}"
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


def _live_tiers() -> dict[str, tuple[list[str], dict[str, object]]]:
    """Collect every tier once, in parallel: four pytest startups, not four serial ones."""
    expressions = _tier_expressions()
    with ThreadPoolExecutor(max_workers=len(TIER_TASKS)) as pool:
        collected = dict(zip(TIER_TASKS, pool.map(_collect, (expressions[name] for name in TIER_TASKS)), strict=True))
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


def _update_ledger(live: dict[str, tuple[list[str], dict[str, object]]]) -> None:
    """Rewrite the collected sets, keeping the human-measured cost columns."""
    tiers = json.loads(LEDGER.read_text(encoding="utf-8"))
    for name, (_ids, summary) in live.items():
        previous = tiers["tiers"].get(name, {})
        tiers["tiers"][name] = {
            "task": name,
            "expression": _tier_expressions()[name],
            "collected": summary["collected"],
            "files": summary["files"],
            "ids_sha256": summary["ids_sha256"],
            # Measured by hand: collection cannot time a tier, and a tier that
            # has never been run must not look like it has.
            "wall_seconds": previous.get("wall_seconds"),
            "measured": previous.get("measured", ""),
            "note": previous.get("note", ""),
        }
    LEDGER.write_text(json.dumps(tiers, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def test_tier_ledger_records_the_selection_each_task_claims() -> None:
    """tests/matrix/tiers.json must name the tiers and expressions the tasks use.

    The expressions come from Taskfile.yml, so the ledger cannot claim a
    selection the task does not run; the times are the human half of the record
    and must look measured (a number, a date) rather than inferred here.
    """
    if os.environ.get("UPDATE_TIERS"):
        pytest.skip("UPDATE_TIERS set: the ledger is being rewritten; re-run without it to check it")
    expressions = _tier_expressions()
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
        seconds = ledger[name].get("wall_seconds")
        if not isinstance(seconds, (int, float)) or float(seconds) <= 0:
            problems.append(f"{name}: wall_seconds is not a measured cost ({seconds!r})")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(ledger[name].get("measured", ""))):
            problems.append(f"{name}: measured is not a date ({ledger[name].get('measured')!r})")
    assert not problems, (
        f"{LEDGER.relative_to(TOP)} no longer describes the tiers Taskfile.yml runs:\n  " + "\n  ".join(problems)
    )


def test_each_tier_collects_what_the_ledger_records() -> None:
    """The collected set of every tier must still be the one on record.

    A tier's cost is a property of the selection, and the selection is decided
    by markers on tests. A test that joins or leaves a tier without the record
    moving is an unexplained cost change, so this re-collects (no runs) and
    names the files that moved. Re-record deliberately with UPDATE_TIERS=1.
    """
    live = _live_tiers()
    if os.environ.get("UPDATE_TIERS"):
        _update_ledger(live)
        pytest.skip(f"rewrote {LEDGER.relative_to(TOP)} from the live collection (fill wall_seconds/measured by hand)")
    ledger = _load_ledger()
    problems = []
    for name, (_ids, summary) in live.items():
        changes = _changes(ledger.get(name, {}), summary)
        if changes:
            problems.append(f"{name} (-m {ledger.get(name, {}).get('expression')!r}):\n" + "\n".join(changes))
    assert not problems, (
        "the tiers no longer collect what tests/matrix/tiers.json records:\n\n"
        + "\n\n".join(problems)
        + "\n\nif the change is deliberate, re-record the collected sets (and then the counts in "
        + "docs/how-to/test-loop.md):\n  UPDATE_TIERS=1 uv run --no-sync pytest -q tests/test_marker_drift.py"
    )


def test_test_loop_doc_states_the_recorded_tier_sizes() -> None:
    """The tier table in docs/how-to/test-loop.md must match the ledger.

    The doc's wall times are measurements a human records; its test counts are
    the ledger's, and they are what this checks: a doc that promises a size the
    tier does not have is the §23.2 drift that started this ledger.
    """
    if os.environ.get("UPDATE_TIERS"):
        pytest.skip("UPDATE_TIERS set: re-run without it to check docs/how-to/test-loop.md against the new ledger")
    ledger = _load_ledger()
    documented: dict[str, tuple[int, str]] = {}
    for number, line in enumerate(DOC.read_text(encoding="utf-8").splitlines(), start=1):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not line.strip().startswith("|") or len(cells) < 3:
            continue
        # The tier table is `| Tier | Command | Tests | Wall time |`: match the
        # command column, and read the count from the column after it.
        for name in TIER_TASKS:
            if cells[1].strip("`") == f"task {name}":
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
