"""The structured answers: `dependencies` and `src_dirs`.

These two questionnaire answers are lists whose defaults are *derived* from
the rest of the answers (questions/_structured.yml), and both are recorded in
`.copier-answers.yml` so a user can edit them and re-render. That refactor
replaced a ~1800-character single-line Jinja expression in
`_shared/pyproject-deps.toml.jinja` and four separately-gated `src/` trees,
so the tests here pin the two properties that make it safe:

1. **The derived set is unchanged.** For every project kind the template
   offers, the answer renders the same `[project] dependencies` line the
   pre-refactor template rendered. The expected lines below are literal
   transcriptions of that template's output, so a branch that loses,
   gains or reorders a dependency fails here rather than shipping.
2. **A user edit is honoured.** Overriding the list changes the render
   (including to `[]`), which is the whole point of the feature.

The renders use the session render cache (pure renders, `skip_tasks=True`),
so the cost is a cache lookup for an answer set another test already rendered.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from support import render_answers

# The answer sets whose derived list matters, keyed by a readable name. Each
# is a partial override on the shared Project Details (tools/answers.py BASE
# reaches them through `render_answers`'s own defaults).
CASES: dict[str, dict[str, Any]] = {
    "library": {"project_type": "library"},
    "cli": {"project_type": "cli"},
    "script": {"project_type": "script"},
    "web_api": {"project_type": "web_api"},
    "data_science": {"project_type": "data_science"},
    "kaggle": {"project_type": "online_judge", "oj_category": "data_science", "oj_kind": "kaggle"},
    "oj_bare": {"project_type": "online_judge", "oj_category": "competitive_coding", "oj_kind": "atcoder"},
    "micropython": {"project_type": "micropython"},
    "ros2": {"project_type": "ros2"},
}

# The pre-refactor render's `dependencies = [...]` line for each case, with
# the package renamed to `probe_pkg` and the value list verbatim. Pin them as
# the *values*, not the whole line: the comment after the array is the
# template's own scaffolding hint and is asserted separately.
EXPECTED: dict[str, list[str]] = {
    "library": ["structlog"],
    "cli": ["structlog"],
    "script": ["structlog"],
    "web_api": [
        "structlog",
        "alembic>=1.13,<2",
        "asgi-correlation-id>=4.3,<6",
        "asyncpg>=0.29,<1",
        "fastapi>=0.115,<1",
        "pydantic-settings>=2.2.1",
        "sqlalchemy[asyncio]>=2.0,<3",
        "uvicorn[standard]>=0.30,<1",
        "prometheus-client>=0.20,<1",
        "slowapi>=0.1.9,<1",
    ],
    "data_science": ["structlog", "duckdb", "pyarrow", "polars>=0.20.15"],
    "kaggle": [
        "structlog",
        "hydra-core>=1.3.2",
        "lightgbm>=4.3",
        "omegaconf>=2.3",
        "optuna>=4.0",
        "pandas>=2.2,<3",
        "pydantic>=2.6",
        "pydantic-settings>=2.2.1",
        "pyyaml>=6.0",
        "rich>=13.0",
        "torch>=2.12",
        "torchvision>=0.27",
        "typer",
        "xgboost",
        "duckdb",
        "pyarrow",
        "polars>=0.20.15",
    ],
    "oj_bare": [],
    "micropython": [],
    "ros2": ["structlog"],
}


def _dependencies(root: Path) -> list[str]:
    """The rendered `[project] dependencies` list."""
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return list(pyproject["project"]["dependencies"])


@pytest.mark.parametrize("case", sorted(CASES), ids=sorted(CASES))
def test_derived_dependency_list_matches_the_pre_refactor_render(case: str, tmp_path: Path) -> None:
    """Each project kind's derived list is exactly what the template shipped."""
    render_answers(tmp_path, {"package_name": "probe_pkg", **CASES[case]}, run_tasks=False)
    assert _dependencies(tmp_path) == EXPECTED[case], (
        f"{case}: the derived dependency list moved. If the change is deliberate, update"
        " EXPECTED here and the dependency reference in docs/reference/dependencies.md"
    )


def test_the_list_answer_is_recorded_and_overridable(tmp_path: Path) -> None:
    """`dependencies` lands in `.copier-answers.yml`, and an override renders.

    Both halves matter: a recorded answer is what makes the list editable
    without re-answering the questionnaire, and an honoured override is what
    makes the edit worth recording.
    """
    derived = tmp_path / "derived"
    render_answers(derived, {"package_name": "probe_pkg", "project_type": "cli"}, run_tasks=False)
    assert "dependencies:" in (derived / ".copier-answers.yml").read_text(encoding="utf-8"), (
        "the structured answer must be recorded in .copier-answers.yml"
    )

    overridden = tmp_path / "overridden"
    render_answers(
        overridden,
        {"package_name": "probe_pkg", "project_type": "cli", "dependencies": ["httpx>=0.27", "my-lib"]},
        run_tasks=False,
    )
    assert _dependencies(overridden) == ["httpx>=0.27", "my-lib"], (
        "a user-supplied list must render verbatim, not be merged with the derived one"
    )

    emptied = tmp_path / "emptied"
    render_answers(
        emptied,
        {"package_name": "probe_pkg", "project_type": "web_api", "dependencies": []},
        run_tasks=False,
    )
    assert _dependencies(emptied) == [], "an empty list must render an empty array, not resurrect defaults"


def test_src_dirs_answer_controls_the_tree(tmp_path: Path) -> None:
    """`src_dirs` gates `src/` itself, and user-added names are created.

    The template tree materializes the known vocabulary; the arbitrary-name
    case is a `_tasks` entry, so this test runs WITH tasks (the only one in
    this module that does) and adds a directory no template file could name.
    """
    derived = tmp_path / "derived"
    render_answers(derived, {"package_name": "probe_pkg", "project_type": "data_science"}, run_tasks=False)
    for name in ("data", "features", "models", "visualization"):
        assert (derived / "src" / name / ".gitkeep").is_file(), f"the derived list lost src/{name}"
    assert "src_dirs:" in (derived / ".copier-answers.yml").read_text(encoding="utf-8")

    # The list's sentinels are gone, but `src/` itself stays: data_science
    # renders its package under the src layout (pkg_scaffold), which is a
    # different mechanism. Pin both so the two are not confused.
    none = tmp_path / "none"
    render_answers(
        none,
        {"package_name": "probe_pkg", "project_type": "data_science", "src_dirs": []},
        run_tasks=False,
    )
    for name in ("data", "features", "models", "visualization"):
        assert not (none / "src" / name).exists(), f"an empty src_dirs must drop src/{name}"
    assert (none / "src" / "probe_pkg" / "__init__.py").is_file(), "the src layout package is not the list's concern"

    # A project with no src layout and no list ships no src/ tree at all.
    bare = tmp_path / "bare"
    render_answers(
        bare,
        {"project_type": "script", "package_name": "probe_pkg", "src_dirs": []},
        run_tasks=False,
    )
    assert not (bare / "src").exists(), "an empty src_dirs on a flat project must leave no src/ behind"

    # A name the tree cannot spell: created by the task, with a .gitkeep.
    custom = tmp_path / "custom"
    render_answers(
        custom,
        {"package_name": "probe_pkg", "project_type": "script", "src_dirs": ["experiments", "pipelines"]},
        run_tasks=True,
    )
    for name in ("experiments", "pipelines"):
        assert (custom / "src" / name / ".gitkeep").is_file(), (
            f"src/{name} missing: a user-added directory name must reach the render"
        )
