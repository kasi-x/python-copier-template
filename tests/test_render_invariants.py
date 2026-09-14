"""Content predicates for the rendered tree (TODO.md §23.4, item 3).

tests/test_witness_matrix.py asserts each leaf's declared *file set*: which
paths a render must (and must not) contain. A file set says nothing about what
is inside those files -- a layer can ship the module it adds while the
dependency that module imports never reaches pyproject.toml, and a docs nav can
point at a page the render never wrote. This module adds the deterministic
*content* predicates for a bounded sample of the same leaves:

- ``pyproject.toml`` parses, its ``[project]`` metadata is the answer set's,
  every third-party import in the rendered Python is a declared dependency,
  and each feature's dependencies are declared exactly when that feature's
  artifact is rendered;
- the ``AGENTS.md`` command table names the runner this render ships and only
  tasks that runner defines;
- every relative ``README.md`` link resolves inside the render;
- every ``zensical.toml`` / ``mkdocs.yml`` nav target exists in the render.

Which of those predicates a leaf must satisfy is declared per leaf class in
tests/matrix/invariants.yml (`predicates:`), read through tools/invariants.py:
this module owns the implementations (one per id, ``PREDICATES`` below) and
fails if the file's registry and that table drift apart.

Every predicate is a pure function of the rendered bytes: no venv, no network,
no execution (PLAN-improvements §24.1 puts those in L3). The module therefore
carries no ``heavy``/``slow``/``network``/``full`` marker and lands in
``test-fast`` (``-m "not heavy and not slow and not meta"``) by construction.

Why this sample -- §24.1 measures L2 at 0.58s/leaf, so the sample is what
bounds the cost. All ten recommended paths of tests/test_recommended_path.py
(every ``use_recommended_*`` gate at its default, i.e. what a real user
renders); eleven leaves of tests/matrix/witnesses.jsonl picked for the
artifact sets the recommended paths do not produce (one gate-off branch per
dimension that changes rendered content, one include layer per project family,
and ros2/micropython, whose runtime is not a pip-installed distribution); and
the runner variants of tests/test_task_runners.py (minus ``just``, the
questionnaire's default and therefore already among the recommended paths).
27 renders in total, ~0.65s each the first time a tree state is seen: the
renders go through tests/render_cache.py, so they are shared with the witness
fast tier and its persistent ``.cache/renders/`` namespace turns a repeat run
into a copy. The predicates themselves cost milliseconds.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from collections.abc import Callable
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_batch.py, tests/test_witness_matrix.py do the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools import batch  # noqa: E402
from tools import invariants  # noqa: E402

# The one source for which content predicates a leaf class must satisfy.
INVARIANTS = invariants.load()

# Imported so pytest can inject the session render cache. It lives in
# render_cache.py and not conftest.py: the template renders the repo's
# conftest.py into every generated project, which has neither copier nor fcntl.
from render_cache import RenderCache  # noqa: E402
from render_cache import render_cache as render_cache  # noqa: E402, PLC0414
from test_recommended_path import BASE  # noqa: E402
from test_recommended_path import FAST_PATHS  # noqa: E402
from test_task_runners import RENDER_ARGS  # noqa: E402

WITNESSES = TOP / "tests" / "matrix" / "witnesses.jsonl"

# Leaves of the witness ledger whose content the recommended paths do not
# cover. Each id is a declaration in tests/matrix/witnesses.jsonl, so a stale
# id fails loudly at import time instead of silently shrinking the sample.
LEDGER_LEAVES: tuple[str, ...] = (
    # gate-off branches that change what is rendered (not just which branch is
    # taken): the agent scaffold, the scraping layer, a non-default docs and
    # strictness answer, and two include layers riding on a base.
    "project_type=cli/gate=off:use_recommended_agent",
    "project_type=cli/gate=off:use_recommended_scraping/include=include_scraping",
    "project_type=library/gate=off:use_recommended_quality",
    "project_type=library/gate=off:use_recommended_docs",
    "project_type=library/gate=off:use_recommended_integrations",
    "project_type=library/gate=off:use_recommended_web_api/include=include_web_api",
    "project_type=web_api/gate=off:use_recommended_data_science/include=include_data_science",
    "project_type=web_api/gate=recommended/include=include_data_science",
    # the bot layer on both of its bases: the discord import must be a
    # declared dependency and the app/ variant must not orphan it
    "project_type=cli/gate=recommended/include=include_bot",
    "project_type=web_api/gate=recommended/include=include_bot",
    # the two families whose runtime is not a pip-installed distribution
    "project_type=ros2/gate=recommended",
    "project_type=micropython/gate=recommended",
    # a second online judge: the same project_type, a different workspace
    "project_type=online_judge/gate=recommended/oj=competitive_coding/yukicoder",
)

# Third-party imports the platform provides, never a PyPI distribution: ROS
# (rclpy, the message packages, the ament test plugins) and the MicroPython
# device runtime (machine). Those two families' pyproject.toml declares the dev
# toolchain, not a runtime, so their package.xml/setup.py own the runtime deps.
PLATFORM_MODULES = frozenset({"ament_copyright", "ament_flake8", "ament_pep257", "machine", "rclpy", "std_msgs"})

# Imports satisfied by a declared distribution's own dependencies (deptry's
# DEP003 class): web_api and the MCP server import the ASGI stack through
# fastapi / mcp instead of declaring it themselves.
TRANSITIVE_PROVIDES = {"fastapi": ("starlette", "pydantic"), "mcp": ("starlette",)}

# Declared distribution -> the import name it provides, when the two differ:
# discord.py is imported as `discord` (the dot in the distribution name is not
# part of the import). These are exactly the template's declared distributions
# that are not imported under their own name (`discord.py`, `hydra-core`,
# `pwntools`, `pyyaml`, `z3-solver`).
DISTRIBUTION_IMPORTS = {
    "discord.py": ("discord",),
    "hydra_core": ("hydra",),
    "pwntools": ("pwn",),
    "pyyaml": ("yaml",),
    "z3_solver": ("z3",),
}


@dataclass(frozen=True)
class Leaf:
    """One render input of the sample: the answers, and the id failures name."""

    id: str
    answers: dict[str, object]


@dataclass(frozen=True)
class Feature:
    """A questionnaire feature: the artifact it renders, and what it needs declared.

    ``paths`` are render-relative artifacts, ``tables`` pyproject tables; the
    feature counts as present when either kind is there. ``deps`` are required
    in ``group`` exactly when the feature is present, which catches both a
    dropped declaration and a declaration left behind in a layout that no
    longer renders the feature.
    """

    name: str
    group: str
    deps: tuple[str, ...]
    paths: tuple[str, ...] = ()
    tables: tuple[tuple[str, ...], ...] = ()

    @property
    def artifacts(self) -> list[str]:
        """The render artifacts that decide whether the feature is present."""
        return list(self.paths) + [".".join(table) for table in self.tables]


FEATURES: tuple[Feature, ...] = (
    Feature(
        name="web_api layout (app/)",
        group="dependencies",
        deps=("fastapi", "uvicorn", "sqlalchemy", "alembic"),
        paths=("app",),
    ),
    Feature(name="mcp integration (.mcp.json)", group="dependencies", deps=("mcp",), paths=(".mcp.json",)),
    Feature(
        name="data-science / kaggle layout",
        group="dependencies",
        deps=("duckdb", "pyarrow", "polars"),
        paths=("notebooks", "src/utils"),
    ),
    Feature(
        name="CTF workspace (challenges/)", group="extras:ctf", deps=("pwntools", "z3-solver"), paths=("challenges",)
    ),
    Feature(
        name="docs build (zensical.toml)", group="dev", deps=("zensical", "mkdocstrings"), paths=("zensical.toml",)
    ),
    Feature(name="poe runner", group="dev", deps=("poethepoet",), tables=(("tool", "poe", "tasks"),)),
    Feature(name="invoke runner", group="dev", deps=("invoke",), paths=("tasks.py",)),
    Feature(name="duty runner", group="dev", deps=("duty",), paths=("duties.py",)),
)

# The line-based runners, in the order TaskRunner reads them.
RUNNER_FILES: tuple[tuple[str, str], ...] = (("Taskfile.yml", "task"), ("justfile", "just"), ("Makefile", "make"))


@dataclass
class Counters:
    """What the session actually checked (the report, not an assertion)."""

    renders: int = 0
    dependency_sets: int = 0
    third_party_imports: int = 0
    agent_tables: int = 0
    readme_links: int = 0
    readme_relative: int = 0
    nav_files: int = 0
    nav_entries: int = 0


def _declared_answers() -> dict[str, dict[str, object]]:
    """The witness ledger's answers, read through tools/batch.py's validator."""
    return {request.id: dict(request.answers) for request in batch.load_requests([WITNESSES])}


def _sample() -> list[Leaf]:
    """The bounded sample: recommended paths, ledger leaves, runner variants."""
    leaves = [
        Leaf(id="fast:" + "-".join(f"{key}={value}" for key, value in answers.items()), answers={**BASE, **answers})
        for answers in FAST_PATHS
    ]
    declared = _declared_answers()
    missing = sorted(set(LEDGER_LEAVES) - set(declared))
    if missing:
        msg = f"{WITNESSES.name} no longer declares {missing}; regenerate the witness list and this sample"
        raise RuntimeError(msg)
    leaves += [Leaf(id=leaf_id, answers=declared[leaf_id]) for leaf_id in LEDGER_LEAVES]
    leaves += [
        Leaf(id=f"runner={runner}", answers={**BASE, "project_type": "library", **overrides})
        for runner, overrides in RENDER_ARGS.items()
        if runner != "just"  # the questionnaire's default, already rendered by FAST_PATHS
    ]
    return leaves


SAMPLE: list[Leaf] = _sample()


@pytest.fixture(scope="session")
def counters() -> Iterator[Counters]:
    """The session's predicate counters, printed at the end (``-s`` shows it)."""
    reported = Counters()
    yield reported
    print(
        f"\nrender content predicates: {reported.renders} renders, {reported.dependency_sets} dependency sets, "
        f"{reported.third_party_imports} third-party imports, {reported.agent_tables} AGENTS.md command tables, "
        f"{reported.readme_links} README links ({reported.readme_relative} relative), "
        f"{reported.nav_files} docs navs with {reported.nav_entries} entries"
    )


def _python_files(root: Path) -> list[Path]:
    """The render's own Python, minus anything the render does not ship."""
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if not {".venv", "site", "typings"} & set(path.relative_to(root).parts)
    ]


def _local_modules(root: Path) -> set[str]:
    """Import names the render provides itself (its modules and directories).

    Directory names at any depth count: the MicroPython layout ships
    ``firmware/`` without an ``__init__.py`` and its tests import it.
    """
    names: set[str] = set()
    for path in _python_files(root):
        names.add(path.stem)
        names.update(path.relative_to(root).parts[:-1])
    return names


def _imported_names(text: str) -> set[str]:
    """Top-level module names of every ``import``/``from`` in one source file."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            names.add((node.module or "").split(".")[0])
    return names - {""}


def _third_party_modules(root: Path) -> dict[str, set[str]]:
    """Top-level third-party imports -> the render-relative files importing them."""
    local = _local_modules(root)
    found: dict[str, set[str]] = {}
    for path in _python_files(root):
        relative = path.relative_to(root).as_posix()
        for module in _imported_names(path.read_text()):
            if module not in sys.stdlib_module_names and module not in local and module not in PLATFORM_MODULES:
                found.setdefault(module, set()).add(relative)
    return found


def _normalise(requirement: str) -> str:
    """A PEP 508 requirement (extras, specifiers, markers and all) as a name."""
    return re.split(r"[<>=!~;\[ (]", requirement.strip(), maxsplit=1)[0].replace("-", "_").lower()


def _table(pyproject: dict[str, Any], path: tuple[str, ...]) -> Any:
    """A pyproject table by dotted path, or None when it is absent."""
    node: Any = pyproject
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _declared(pyproject: dict[str, Any], group: str) -> list[str]:
    """The requirements of one dependency group of the render's pyproject."""
    if group == "dependencies":
        return list(_table(pyproject, ("project", "dependencies")) or [])
    if group == "dev":
        return list(_table(pyproject, ("dependency-groups", "dev")) or [])
    if group.startswith("extras:"):
        return list(_table(pyproject, ("project", "optional-dependencies", group.removeprefix("extras:"))) or [])
    msg = f"unknown dependency group {group!r}"
    raise AssertionError(msg)


def _provided(pyproject: dict[str, Any]) -> set[str]:
    """Every import name the render's own declarations make available."""
    declared = {
        _normalise(requirement) for group in ("dependencies", "dev") for requirement in _declared(pyproject, group)
    }
    declared |= {
        _normalise(requirement)
        for extras in _table(pyproject, ("project", "optional-dependencies")) or {}
        for requirement in _table(pyproject, ("project", "optional-dependencies", extras))
    }
    declared |= {_normalise(requirement) for requirement in _table(pyproject, ("build-system", "requires")) or []}
    provided = set(declared)
    for name in declared:
        provided.update(DISTRIBUTION_IMPORTS.get(name, ()))
        provided.update(TRANSITIVE_PROVIDES.get(name, ()))
    return provided


def _feature_present(feature: Feature, root: Path, pyproject: dict[str, Any]) -> bool:
    """Whether the render ships the feature's artifact."""
    if any((root / path).exists() for path in feature.paths):
        return True
    return any(_table(pyproject, table) for table in feature.tables)


def _metadata_problems(leaf_id: str, root: Path, pyproject: dict[str, Any], answers: dict[str, object]) -> list[str]:
    """``[project]`` names, urls and file references vs the answers that made them."""
    project = _table(pyproject, ("project",))
    if not isinstance(project, dict):
        return [f"{leaf_id}: pyproject.toml has no [project] table"]
    problems: list[str] = []
    if project.get("name") != answers["distribution_name"]:
        problems.append(
            f"{leaf_id}: [project].name is {project.get('name')!r}, the answers say {answers['distribution_name']!r}"
        )
    if project.get("description") != answers["description"]:
        problems.append(f"{leaf_id}: [project].description is not the answered description")
    authors = [author.get("email") for author in project.get("authors", []) if isinstance(author, dict)]
    if answers["author_email"] not in authors:
        problems.append(f"{leaf_id}: [project].authors misses {answers['author_email']!r}")
    expected_url = f"https://{answers['git_platform']}/{answers['github_org']}/{answers['repo_name']}"
    if project.get("urls", {}).get("GitHub") != expected_url:
        problems.append(f"{leaf_id}: [project].urls.GitHub is not {expected_url!r}")
    if not str(project.get("requires-python", "")).startswith(">="):
        problems.append(f"{leaf_id}: [project].requires-python is {project.get('requires-python')!r}")
    for key in ("readme", "license-files"):
        referenced = project.get(key)
        files = [referenced] if isinstance(referenced, str) else list(referenced or [])
        problems.extend(
            f"{leaf_id}: [project].{key} references {relative!r}, which is not in the render"
            for relative in files
            if not (root / relative).exists()
        )
    return problems


def _dependency_problems(leaf_id: str, root: Path, pyproject: dict[str, Any], counters: Counters) -> list[str]:
    """The declared dependency sets vs the code and the artifacts in the render."""
    problems: list[str] = []
    counters.dependency_sets += 1
    provided = _provided(pyproject)
    try:
        imports = _third_party_modules(root)
    except SyntaxError as exc:
        return [f"{leaf_id}: {exc.filename} does not parse: {exc.msg}"]
    counters.third_party_imports += len(imports)
    for module, importers in sorted(imports.items()):
        if _normalise(module) not in provided:
            problems.append(f"{leaf_id}: {min(importers)} imports {module!r}, which no declared dependency provides")

    for feature in FEATURES:
        present = _feature_present(feature, root, pyproject)
        available = {_normalise(requirement) for requirement in _declared(pyproject, feature.group)}
        for dependency in feature.deps:
            if present and _normalise(dependency) not in available:
                problems.append(f"{leaf_id}: {feature.name} is rendered without declaring {dependency!r}")
            if not present and _normalise(dependency) in available:
                problems.append(
                    f"{leaf_id}: {dependency!r} is declared for {feature.name}, "
                    f"but the render ships none of {feature.artifacts}"
                )

    if (root / "pixi.lock").exists() != bool(_table(pyproject, ("tool", "pixi", "workspace"))):
        problems.append(f"{leaf_id}: pixi.lock and [tool.pixi.workspace] disagree about the package manager")
    if (root / "pixi.lock").exists() and (root / "uv.lock").exists():
        problems.append(f"{leaf_id}: both pixi.lock and uv.lock are rendered")
    return problems


def _pyproject_problems(leaf: Leaf, root: Path, counters: Counters) -> list[str]:
    """Predicate 1: the rendered pyproject.toml, as the answers' own record."""
    path = root / "pyproject.toml"
    if not path.exists():
        return [f"{leaf.id}: pyproject.toml is not in the render"]
    try:
        pyproject = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        return [f"{leaf.id}: pyproject.toml does not parse: {exc}"]
    return _metadata_problems(leaf.id, root, pyproject, leaf.answers) + _dependency_problems(
        leaf.id, root, pyproject, counters
    )


@dataclass(frozen=True)
class TaskRunner:
    """The runner a render ships, and the task names it defines."""

    name: str
    tasks: frozenset[str]


def _task_runner(root: Path) -> TaskRunner | None:
    """The render's task runner, read out of the artifact that serializes it.

    tests/test_task_runners.py owns "every runner's table equals the pixi
    model"; this reader needs only the task *names*, to check the
    cross-artifact agreement the audit calls out: the AGENTS.md command table
    is generated from the same model, so every command it prints must name a
    task the render's own runner defines.
    """
    for filename, name in RUNNER_FILES:
        path = root / filename
        if not path.exists():
            continue
        text = path.read_text()
        if filename == "Taskfile.yml":
            return TaskRunner(name, frozenset(yaml.safe_load(text)["tasks"]) - {"default"})
        return TaskRunner(name, frozenset(re.findall(r"^([a-zA-Z][a-zA-Z_-]*):", text, re.MULTILINE)) - {"default"})
    for filename, name, pattern in (
        ("tasks.py", "invoke", r"^def ([a-z_]+)\(c: Context\)"),
        ("duties.py", "duty", r"^def ([a-z_]+)\(ctx: Context\)"),
    ):
        path = root / filename
        if path.exists():
            return TaskRunner(
                name,
                frozenset(found.replace("_", "-") for found in re.findall(pattern, path.read_text(), re.MULTILINE)),
            )
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        parsed = tomllib.loads(pyproject.read_text())
        for name, key in (("poe", ("tool", "poe", "tasks")), ("pixi", ("tool", "pixi", "feature", "dev", "tasks"))):
            tasks = _table(parsed, key)
            if tasks:
                return TaskRunner(name, frozenset(tasks))
    return None


def _agents_problems(leaf: Leaf, root: Path, counters: Counters) -> list[str]:
    """Predicate 2: the AGENTS.md command table vs the render's task model."""
    path = root / "AGENTS.md"
    if not path.exists():
        return []  # no agent guide is rendered for online_judge, ros2 and micropython
    block = re.search(r"```sh\n(.*?)```", path.read_text(), re.DOTALL)
    if block is None:
        return [f"{leaf.id}: AGENTS.md ships no sh command table"]
    rows = [line.split("#")[0].split() for line in block.group(1).splitlines() if line.split("#")[0].strip()]
    counters.agent_tables += 1
    if not rows:
        return [f"{leaf.id}: the AGENTS.md command table is empty"]
    runner = _task_runner(root)
    if runner is None:
        return [f"{leaf.id}: the render ships no task runner to check AGENTS.md against"]
    problems: list[str] = []
    prefixes = sorted({row[0] for row in rows})
    if prefixes != [runner.name]:
        problems.append(
            f"{leaf.id}: the AGENTS.md command table names {prefixes}, the render's runner is {runner.name!r}"
        )
    unknown = sorted({row[-1] for row in rows} - runner.tasks)
    if unknown:
        problems.append(
            f"{leaf.id}: the AGENTS.md command table names tasks {runner.name!r} does not define: {unknown}"
        )
    return problems


def _readme_problems(leaf: Leaf, root: Path, counters: Counters) -> list[str]:
    """Predicate 3: every relative README link resolves inside the render."""
    path = root / "README.md"
    if not path.exists():
        return [f"{leaf.id}: README.md is not in the render"]
    problems: list[str] = []
    for target in re.findall(r"\]\(([^)\s]+)", path.read_text()):
        counters.readme_links += 1
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        counters.readme_relative += 1
        if not (root / target.split("#")[0]).exists():
            problems.append(f"{leaf.id}: README.md links to {target!r}, which is not in the render")
    return problems


def _nav_targets(nav: Any) -> list[str]:
    """Every page a nav declaration points at, nested sections included."""
    if isinstance(nav, str):
        return [nav]
    if isinstance(nav, dict):
        return [target for value in nav.values() for target in _nav_targets(value)]
    if isinstance(nav, list):
        return [target for item in nav for target in _nav_targets(item)]
    return []


def _nav_problems(leaf: Leaf, root: Path, counters: Counters) -> list[str]:
    """Predicate 4: docs-build nav entries point at pages the render ships.

    A layout that ships no docs build has no nav to check: the questionnaire's
    sphinx and great-docs answers, and README itself, render neither of these
    files, and this predicate then checks nothing.
    """
    problems: list[str] = []
    for filename, loader in (("zensical.toml", tomllib.loads), ("mkdocs.yml", yaml.safe_load)):
        path = root / filename
        if not path.exists():
            continue
        parsed = loader(path.read_text())
        nav = _table(parsed, ("project", "nav")) if filename == "zensical.toml" else parsed.get("nav")
        if nav is None:
            problems.append(f"{leaf.id}: {filename} declares no nav")
            continue
        docs_dir = str(_table(parsed, ("project", "docs_dir")) or parsed.get("docs_dir") or "docs")
        counters.nav_files += 1
        for target in _nav_targets(nav):
            counters.nav_entries += 1
            if target.startswith(("http://", "https://")):
                continue
            if not (root / docs_dir / target.split("#")[0]).exists():
                problems.append(f"{leaf.id}: {filename} nav points at {target!r}, which is not in the render")
    return problems


# One implementation per predicate id the invariants file may name. The ids
# are the file's registry (tests/matrix/invariants.yml `predicates:`); a name
# with no implementation here, or an implementation no row names, fails
# test_the_invariants_file_names_exactly_the_predicates_implemented_here.
PREDICATES: dict[str, Callable[[Leaf, Path, Counters], list[str]]] = {
    "pyproject": _pyproject_problems,
    "agents-md": _agents_problems,
    "readme-links": _readme_problems,
    "docs-nav": _nav_problems,
}


def _problems(leaf: Leaf, root: Path, counters: Counters) -> list[str]:
    """Every content predicate this leaf's class declares, each problem naming the leaf."""
    problems: list[str] = []
    for name in INVARIANTS.predicates_for(leaf.answers):
        problems += PREDICATES[name](leaf, root, counters)
    return problems


def test_the_invariants_file_names_exactly_the_predicates_implemented_here() -> None:
    """The file's predicate registry and this module's table are the same set.

    A name only one side knows is a check that silently stops running: a
    registry entry with no implementation, or an implementation no row names.
    """
    assert set(INVARIANTS.predicates) == set(PREDICATES)
    # And a render must actually be held to them: the sample's classes declare
    # at least one predicate each (a class that declared none would be a
    # silently unchecked leaf).
    unchecked = sorted(leaf.id for leaf in SAMPLE if not INVARIANTS.predicates_for(leaf.answers))
    assert unchecked == [], f"sampled leaves whose class declares no content predicate: {unchecked}"


@pytest.mark.parametrize("leaf", SAMPLE, ids=[leaf.id for leaf in SAMPLE])
def test_render_content_predicates(leaf: Leaf, tmp_path: Path, render_cache: RenderCache, counters: Counters) -> None:
    """One render, every content predicate, all problems reported at once."""
    render_cache.render(tmp_path, dict(leaf.answers))
    counters.renders += 1
    problems = _problems(leaf, tmp_path, counters)
    assert problems == [], f"{leaf.id} violates its content invariants:\n  " + "\n  ".join(problems)


def test_predicates_fire_on_injected_drift(tmp_path: Path, render_cache: RenderCache, counters: Counters) -> None:
    """Guard for the guard: each predicate reports injected drift, by leaf id.

    A predicate that cannot fail proves nothing, so the render is damaged on
    purpose here -- a removed docs page and a removed linked file, a removed
    dependency, and an invented command-table row -- and every predicate must
    name both the leaf and the drift.
    """
    leaf = Leaf(id="fast:project_type=web_api", answers={**BASE, "project_type": "web_api"})
    render_cache.render(tmp_path, dict(leaf.answers))
    counters.renders += 1

    (tmp_path / "docs" / "modules.md").unlink()
    (tmp_path / "SECURITY.md").unlink()
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(re.sub(r'"fastapi[^"]*", ', "", pyproject.read_text()))
    agents = tmp_path / "AGENTS.md"
    agents.write_text(agents.read_text().replace("just test\n", "just test\njust deploy\n"))

    problems = _problems(leaf, tmp_path, counters)
    expected_drift = (
        "web_api layout (app/) is rendered without declaring 'fastapi'",
        "the AGENTS.md command table names tasks 'just' does not define: ['deploy']",
        "README.md links to 'SECURITY.md', which is not in the render",
        "zensical.toml nav points at 'modules.md', which is not in the render",
    )
    silent = [
        drift for drift in expected_drift if not any(leaf.id in problem and drift in problem for problem in problems)
    ]
    assert silent == [], f"the predicates stayed silent on: {silent}\nreported instead:\n  " + "\n  ".join(problems)
