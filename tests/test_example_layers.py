"""The opt-in layers stacked on a base project type: include_mcp,
include_scraping, include_ctf, include_sentry, include_web_api /
include_data_science combos, and the agent scaffold -- with the *_effective
guards that keep each layer inside the base it belongs to.

The "a layer is not offered elsewhere" half is a property of the QUESTION
SPACE, not of any render, so it is pinned once, at L1, by evaluating the real
questionnaire over every project_type choice
(test_effective_flags_are_not_offered_outside_their_declared_bases) -- the
tests/test_layer_matrix.py oracle (one Worker._ask pass per answer set, the
derived flag read out of Worker._render_context). What a flag gates on the
ARTIFACT side is pinned render-side, on one representative leaf per flag, by
the single-render tests below (test_template_include_mcp /
test_template_mcp_on_web_api, test_template_include_ctf,
test_template_include_scraping_httpx, test_template_agent_scaffold /
test_template_agent_cli_only) and, over the whole witness leaf space, by the
exact file-set expectations of tests/matrix/witnesses.jsonl. The former
per-off-type render sweeps (ctf / scraping / mcp x3 / agent-scaffold placement)
were the L2 spelling of the L1 table and are gone (TODO archive T12)."""

import json
import sys
import tempfile
import tomllib
from collections.abc import Iterator
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:  # tests/test_layer_matrix.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from copier._main import Worker  # noqa: E402
from tools import answers  # noqa: E402
from tools import when_model  # noqa: E402

from support import copy_project  # noqa: E402
from support import copy_project_capturing_stderr  # noqa: E402
from support import copy_project_recommended  # noqa: E402
from support import make_venv  # noqa: E402

# -- L1: the derived-layer flags, evaluated on the real questionnaire ------- #


@dataclass(frozen=True)
class FlagRow:
    """One declared row of the flag truth table.

    `expected` is the set of audited flags that must resolve True for these
    answers; every other audited flag must resolve False. `answers` are the
    overrides beyond the shared Project Details and `project_type` -- at the
    polarity the deleted render sweeps used: the include layers forced ON (the
    sweeps rendered with them forced to prove the guards hold) and the agent
    gate forced OFF (its sweep declined the recommended scaffold).
    """

    project_type: str
    expected: frozenset[str]
    answers: dict[str, Any]
    note: str = ""

    @property
    def where(self) -> str:
        """The row's name in failure messages."""
        return f"{self.project_type} {self.note}".strip()


# The render-time guards the deleted sweeps exercised. `license_check_effective`
# is in the table to pin that it is NOT one of them: its gate is
# use_recommended_security / license_check (questions/_internal.yml), so it
# resolves True on every base -- the one former sweep family (license_check)
# that lost its "not offered elsewhere" property when the check moved behind
# the security gate; its render side lives in tests/test_example_docs_ci.py.
AUDITED_FLAGS: tuple[str, ...] = (
    "ctf_effective",
    "scraping_effective",
    "mcp_effective",
    "agents_md_effective",
    "agent_scaffold",
    "license_check_effective",
)


# The answers the deleted render sweeps forced, kept as the table's evaluation
# polarity (FlagRow's): the include layers ON, the agent gate OFF -- the
# sweeps rendered with those answers forced to prove the guards hold, so the
# L1 evaluation must see them too, or every guard would look green while
# reading its default-off answer.
SWEEP_POLARITY: dict[str, Any] = {
    "include_ctf": True,
    "include_scraping": True,
    "include_mcp": True,
    "use_recommended_agent": False,
}


def _row(project_type: str, expected: frozenset[str], note: str = "", **answers: Any) -> FlagRow:
    return FlagRow(
        project_type=project_type,
        expected=expected,
        answers={**SWEEP_POLARITY, **answers},
        note=note,
    )


# The declared truth table (TODO archive T12: "project_type x include_* ->
# derived flag, verified over every combination"). One row per project_type
# choice plus one per online-judge polarity the sweeps rendered; a new
# project_type without a row fails the check, and so does any cell whose
# resolved flag drifts from the declaration.
FLAG_TABLE: tuple[FlagRow, ...] = (
    _row(
        "library",
        frozenset({"ctf_effective", "agents_md_effective", "agent_scaffold", "license_check_effective"}),
    ),
    _row(
        "cli",
        frozenset(
            {
                "ctf_effective",
                "scraping_effective",
                "mcp_effective",
                "agents_md_effective",
                "agent_scaffold",
                "license_check_effective",
            }
        ),
    ),
    _row("web_api", frozenset({"mcp_effective", "agents_md_effective", "license_check_effective"})),
    _row("data_science", frozenset({"agents_md_effective", "license_check_effective"})),
    _row("script", frozenset({"agents_md_effective", "license_check_effective"})),
    _row(
        "online_judge",
        frozenset({"agents_md_effective", "license_check_effective"}),
        note="(the oj defaults: kaggle always allows AI agents)",
    ),
    _row(
        "online_judge",
        frozenset({"agents_md_effective", "license_check_effective"}),
        note="(competitive_coding/atcoder, AI not allowed: the guide still ships, oj_allow_ai now picks its wording)",
        oj_category="competitive_coding",
        oj_kind="atcoder",
    ),
    _row("ros2", frozenset({"agents_md_effective", "license_check_effective"})),
    _row("micropython", frozenset({"agents_md_effective", "license_check_effective"})),
)


@pytest.fixture(scope="module")
def worker() -> Iterator[Worker]:
    """One copier Worker for the L1 checks: the checkout's own questionnaire
    (vcs_ref=HEAD), the setup tests/test_layer_matrix.py uses."""
    with tempfile.TemporaryDirectory() as dst:
        yield Worker(src_path=str(TOP), dst_path=Path(dst), defaults=True, quiet=True, vcs_ref="HEAD")


def _flag_table_problems(worker: Worker, table: tuple[FlagRow, ...], choices: Sequence[str]) -> list[str]:
    """Diff the declared table against the flags the real questionnaire resolves.

    One questionnaire pass per row (Worker._ask; `worker.data` seeds the pass
    with the shared Project Details, the row's project_type and the sweep
    polarity, exactly as tests/test_layer_matrix.py evaluates its matrix), the
    audited flags read from Worker._render_context(). Both are private,
    because copier exposes no other way to run that pass.
    """
    problems: list[str] = []
    covered: set[str] = set()
    for row in table:
        worker.data = {**answers.BASE, "project_type": row.project_type, **row.answers}
        worker._ask()  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001  WHYNOT: the oracle is copier's own questionnaire pass, the tests/test_layer_matrix.py precedent.
        context = worker._render_context()  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001  WHYNOT: same oracle as above.
        covered.add(row.project_type)
        for flag in AUDITED_FLAGS:
            resolved = context.get(flag, "<missing from the render context>")
            if bool(resolved) != (flag in row.expected):
                problems.append(
                    f"{row.where}: {flag} resolved to {resolved!r}, expected {'on' if flag in row.expected else 'off'}"
                )
    uncovered = sorted(set(choices) - covered)
    if uncovered:
        problems.append(f"no FLAG_TABLE row covers project_type(s) {uncovered}: declare one")
    return problems


def test_effective_flags_are_not_offered_outside_their_declared_bases(worker: Worker) -> None:
    """L1 (TODO archive T12): each derived layer flag resolves True exactly on
    the bases that offer its question.

    The deleted render sweeps (test_template_include_{ctf,scraping}_not_offered_elsewhere,
    test_template_mcp_not_offered_to_{library,online_judge,data_science},
    test_template_agent_not_offered_for_web_api) rendered up to five projects
    each to observe one flag's absence; that is a property of the question
    space, so it is evaluated here over every project_type choice -- including
    the ros2 / micropython bases the sweeps never reached -- at the sweep
    polarity (include layers forced on, the agent gate forced off). That the
    flags actually gate artifacts render-side is the single-render
    representatives' business (module docstring), and the judge-side absences
    (challenges on kaggle / code judges, AGENTS.md on code judges) stay
    declared in tests/matrix/invariants.yml.
    """
    questions, _order = when_model.load_questions()
    choices = when_model.static_str_choices(questions["project_type"])
    assert choices, "project_type lost its static choices: there is no base space to iterate"
    problems = _flag_table_problems(worker, FLAG_TABLE, choices)
    assert not problems, (
        "the derived-layer flags drift from the declared truth table (evaluated by copier's own "
        "questionnaire pass at the sweep polarity) -- update FLAG_TABLE or questions/_internal.yml, "
        "whichever is wrong:\n  " + "\n  ".join(problems)
    )


def test_the_flag_table_check_fails_on_a_wrong_expectation(worker: Worker) -> None:
    """Guard for the guard (the tests/test_copier_structure.py error-sweep
    precedent): one wrong declared cell and the L1 check must name it.

    The mutation is in-process, on the expectation table only -- the real
    questions are not touched. The flipped cell is the old sweep's signature
    failure (include_mcp leaking onto library); a checker that stayed green
    here would be comparing nothing.
    """
    leaked = replace(FLAG_TABLE[0], expected=FLAG_TABLE[0].expected | {"mcp_effective"})
    questions, _order = when_model.load_questions()
    choices = when_model.static_str_choices(questions["project_type"])
    problems = _flag_table_problems(worker, (leaked,), choices[:1])
    assert problems == ["library: mcp_effective resolved to False, expected on"], problems


# -- L2: one representative render per layer's artifact set ------------------ #


def test_template_web_api_data_science_combo_guide(tmp_path: Path):
    """The app/ + src/ coexistence must be explained where agents and humans
    read (AGENTS.md / README)."""
    copy_project(
        tmp_path,
        project_type="web_api",
        include_data_science=True,
        use_recommended_integrations=False,
    )
    assert "data-science layer coexists" in (tmp_path / "AGENTS.md").read_text()
    readme = (tmp_path / "README.md").read_text()
    assert "two trees coexist" in readme
    assert "`src/`" in readme


def test_template_include_sentry(tmp_path: Path):
    copy_project(tmp_path, include_sentry=True)
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("sentry-sdk") for d in pyproject_toml["project"]["dependencies"])
    main_file = tmp_path / "src" / "python_copier_template_example" / "__main__.py"
    assert "sentry_sdk.init" in main_file.read_text()


def test_template_include_mcp(tmp_path: Path):
    copy_project(tmp_path, project_type="cli", include_mcp=True)
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("mcp[cli]") for d in pyproject_toml["project"]["dependencies"])
    pkg_dir = tmp_path / "src" / "python_copier_template_example"
    assert (pkg_dir / "mcp_server.py").exists()
    assert (tmp_path / "tests" / "test_mcp_server.py").exists()
    scripts = pyproject_toml["project"]["scripts"]
    assert "mcp-server-python-copier-template-example" in scripts
    # mcp_server.py is covered by the type checkers (v2 SDK ships stubs) and
    # the scaffold uses the v2 API with safe-by-default HTTP serving.
    mcp_server = (pkg_dir / "mcp_server.py").read_text()
    assert "from mcp.server import MCPServer" in mcp_server
    assert "fastmcp" not in mcp_server
    assert "streamable-http" in mcp_server
    # Security hardening: non-local binds require MCP_ALLOWED_HOSTS, --host /
    # --port are exposed, and a /health custom route is registered.
    assert "MCP_ALLOWED_HOSTS" in mcp_server
    assert "--host" in mcp_server
    assert '"/health"' in mcp_server
    assert "transport_security" in mcp_server


def test_template_mcp_docker_task(tmp_path: Path):
    """With docker enabled, the task runner ships an mcp-serve task that
    builds and runs the MCP server over Streamable HTTP."""
    copy_project(tmp_path, project_type="cli", include_mcp=True, docker=True)
    taskfile = (tmp_path / "Taskfile.yml").read_text()
    assert "mcp-serve" in taskfile
    assert "mcp-server-python-copier-template-example" in taskfile
    assert "MCP_ALLOWED_HOSTS" in taskfile
    # The Dockerfile exposes the MCP port and documents the run command.
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "EXPOSE 8000" in dockerfile
    assert "mcp-server-python-copier-template-example" in dockerfile
    # .env.example documents the allowlist variable.
    env_example = (tmp_path / ".env.example").read_text()
    assert "MCP_ALLOWED_HOSTS" in env_example
    # .mcp.json points the host at the stdio command (zero-config registration).
    mcp_json = json.loads((tmp_path / ".mcp.json").read_text())
    server = mcp_json["mcpServers"]["python-copier-template-example"]
    assert server["args"] == ["run", "mcp-server-python-copier-template-example"]
    # README advertises the registration path.
    assert ".mcp.json" in (tmp_path / "README.md").read_text()


def test_template_mcp_no_docker_no_task(tmp_path: Path):
    """Without docker, no mcp-serve task is generated."""
    copy_project(tmp_path, project_type="cli", include_mcp=True, docker=False)
    taskfile = (tmp_path / "Taskfile.yml").read_text()
    assert "mcp-serve" not in taskfile


@pytest.mark.heavy
@pytest.mark.network
def test_template_mcp_runs_in_process(tmp_path: Path):
    """The generated MCP server must actually work against the installed v2
    SDK: sync the project, run the in-process client test, and type-check the
    scaffold (no exclusions)."""
    copy_project(tmp_path, project_type="cli", include_mcp=True)
    run = make_venv(tmp_path)
    run("uv run --locked pytest -q")
    run("uv run --locked basedpyright src tests")
    run("uv run --locked ruff check src tests")


def test_template_mcp_on_web_api(tmp_path: Path):
    """web_api offers the MCP scaffold in app/: the server module, its
    in-process client test, the mcp dependency and the console script all
    point at the app import root."""
    copy_project(
        tmp_path,
        project_type="web_api",
        use_recommended_integrations=False,
        include_mcp=True,
    )
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("mcp[cli]") for d in pyproject_toml["project"]["dependencies"])
    assert (tmp_path / "app" / "mcp_server.py").exists()
    assert (tmp_path / "tests" / "test_mcp_server.py").exists()
    test_body = (tmp_path / "tests" / "test_mcp_server.py").read_text()
    assert "from app import mcp_server" in test_body
    assert "app.mcp_server:main" in (tmp_path / "pyproject.toml").read_text()
    # no <pkg>-side duplicate
    assert not list(tmp_path.rglob("src/*/mcp_server.py"))


@pytest.mark.heavy
@pytest.mark.network
def test_template_mcp_runs_on_web_api_in_process(tmp_path: Path):
    """The app/-hosted MCP server must actually work: sync the web_api+MCP
    project and run its in-process client test plus the API tests."""
    copy_project(
        tmp_path,
        project_type="web_api",
        use_recommended_integrations=False,
        include_mcp=True,
    )
    run = make_venv(tmp_path)
    run("uv run --locked pytest -q")
    run("uv run --locked ruff check app tests")


def test_template_mcp_flat_layout(tmp_path: Path):
    """The flat-layout package variant also ships mcp_server.py and its
    console script."""
    copy_project(tmp_path, project_type="cli", layout="flat", include_mcp=True)
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("mcp[cli]") for d in pyproject_toml["project"]["dependencies"])
    assert (tmp_path / "python_copier_template_example" / "mcp_server.py").exists()
    assert (tmp_path / "tests" / "test_mcp_server.py").exists()


def test_template_include_ctf(tmp_path: Path):
    """include_ctf layers the participant workspace: solve.py starter, its
    test, the ctf extra, and the gitignore guards."""
    copy_project(tmp_path, project_type="cli", include_ctf=True)
    assert (tmp_path / "challenges" / "pwn" / "example" / "solve.py").exists()
    assert (tmp_path / "tests" / "test_ctf_example.py").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["optional-dependencies"]["ctf"] == [
        "pwntools>=4.13,<5",
        "z3-solver>=4.13,<5",
    ]
    gitignore = (tmp_path / ".gitignore").read_text()
    assert "challenges/**/vuln" in gitignore


@pytest.mark.heavy
@pytest.mark.network
def test_template_include_ctf_runs(tmp_path: Path):
    """The generated solve.py starter must actually run: sync the project
    and execute both the starter directly and its generated test."""
    copy_project(tmp_path, project_type="cli", include_ctf=True)
    run = make_venv(tmp_path)
    run(
        "uv run --locked python challenges/pwn/example/solve.py",
        # noqa: S603 -- test helper, fixed argv
    )
    run("uv run --locked pytest tests/test_ctf_example.py -q")
    run("uv run --locked ruff check challenges tests/test_ctf_example.py")


def test_template_include_scraping_httpx(tmp_path: Path):
    """include_scraping layers the polite fetcher: CHARTER.md, fetcher.py,
    its offline test, the httpx dep, ruff banned-api and gitignore guards."""
    copy_project(tmp_path, project_type="cli", include_scraping=True)
    assert (tmp_path / "CHARTER.md").exists()
    pkg_dir = tmp_path / "src" / "python_copier_template_example"
    assert (pkg_dir / "fetcher.py").exists()
    assert (tmp_path / "tests" / "test_scraping.py").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("httpx") for d in pyproject_toml["project"]["dependencies"])
    ruff_lint = pyproject_toml["tool"]["ruff"]["lint"]
    banned = ruff_lint["flake8-tidy-imports"]["banned-api"]
    assert any(name.startswith("httpx.") for name in banned), "direct httpx calls are banned in favour of the fetcher"
    ignores = ruff_lint["per-file-ignores"]
    assert any(key.endswith("fetcher.py") and "TID251" in codes for key, codes in ignores.items()), (
        "fetcher.py is the allowlisted implementation behind the ban"
    )
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".cache/fetcher/" in gitignore
    agents = (tmp_path / "AGENTS.md").read_text()
    assert "CHARTER.md" in agents
    assert "banned-api" in agents
    readme = (tmp_path / "README.md").read_text()
    assert "CHARTER.md" in readme


@pytest.mark.heavy
@pytest.mark.network
def test_template_include_scraping_runs(tmp_path: Path):
    """The generated fetcher must actually run: sync the project and execute
    its offline test plus ruff on the fetcher."""
    copy_project(tmp_path, project_type="cli", include_scraping=True)
    run = make_venv(tmp_path)
    run("uv run --locked pytest tests/test_scraping.py -q")
    run("uv run --locked ruff check src tests/test_scraping.py")


def test_template_scraping_engine_choices(tmp_path: Path):
    """Each non-default engine ships its starter + test; `all` ships all."""
    cases = {
        "scrapy": (["spider.py"], ["test_scrapy_spider.py"], "scrapy"),
        "memorious": (["crawler.py"], ["test_memorious_crawler.py"], "memorious4"),
        "playwright": (["browser_fetch.py"], ["test_browser_fetch.py"], "playwright"),
        "all": (
            ["fetcher.py", "spider.py", "crawler.py", "browser_fetch.py"],
            ["test_scraping.py", "test_scrapy_spider.py", "test_memorious_crawler.py", "test_browser_fetch.py"],
            "memorious4",
        ),
    }
    for engine, (modules, tests, dep) in cases.items():
        project_path = tmp_path / f"engine_{engine}"
        copy_project(
            project_path,
            project_type="cli",
            include_scraping=True,
            use_recommended_scraping=False,
            scraping_engine=engine,
        )
        pkg_dir = project_path / "src" / "python_copier_template_example"
        for module in modules:
            assert (pkg_dir / module).exists(), f"{engine}: missing {module}"
        for test in tests:
            assert (project_path / "tests" / test).exists(), f"{engine}: missing {test}"
        pyproject = tomllib.loads((project_path / "pyproject.toml").read_text())
        assert any(d.startswith(dep) for d in pyproject["project"]["dependencies"]), f"{engine}: missing {dep}"


def test_template_scraping_memorious_forces_agpl(tmp_path: Path):
    """memorious4 is AGPL-3.0: the generated project license must be AGPL-3.0
    even when MIT was asked."""
    stderr = copy_project_capturing_stderr(
        tmp_path,
        project_type="cli",
        include_scraping=True,
        use_recommended_scraping=False,
        scraping_engine="memorious",
        license="MIT",
    )
    assert "WARNING" in stderr and "AGPL-3.0 instead of your MIT answer" in stderr, (
        "the silent license override must say so at generation time"
    )
    pyproject = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject["project"]["license"] == "AGPL-3.0"
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in (tmp_path / "LICENSE").read_text()


def test_template_agent_off_by_default(tmp_path: Path):
    # use_recommended_agent defaults to true: no agent scaffold on a library
    copy_project_recommended(tmp_path, project_type="library")
    assert not (tmp_path / "prompts").exists()
    assert not (tmp_path / "src" / "recommended_example" / "tools").exists()
    assert not (tmp_path / "src" / "recommended_example" / "agent.py").exists()
    assert not (tmp_path / "tests" / "test_agent.py").exists()


def test_template_agent_scaffold(tmp_path: Path):
    copy_project(tmp_path, project_type="library", use_recommended_agent=False)
    # prompt, typed tools package and the runnable agent module
    assert (tmp_path / "prompts" / "agent.md").exists()
    assert (tmp_path / "src" / "python_copier_template_example" / "tools" / "__init__.py").exists()
    assert (tmp_path / "src" / "python_copier_template_example" / "tools" / "example.py").exists()
    assert (tmp_path / "src" / "python_copier_template_example" / "agent.py").exists()
    assert (tmp_path / "tests" / "test_agent.py").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("pydantic-ai") for d in pyproject_toml["project"]["dependencies"])
    # the agent's LLM keys are documented in the env example (shipped because
    # the agent scaffold consumes env vars)
    env_example = (tmp_path / ".env.example").read_text()
    assert "OPENAI_API_KEY" in env_example


def test_template_agent_cli_only(tmp_path: Path):
    # cli also offers the agent gate
    copy_project(tmp_path, project_type="cli", use_recommended_agent=False)
    assert (tmp_path / "prompts" / "agent.md").exists()
    assert (tmp_path / "src" / "python_copier_template_example" / "agent.py").exists()


def test_combo_data_science_with_web_api(tmp_path: Path):
    """The include_web_api opt-in adds the FastAPI scaffold on top of a
    data_science base: app/ + alembic + FastAPI deps coexist with the
    analysis layout (notebooks/, data/, ...)."""
    copy_project(
        tmp_path,
        project_type="data_science",
        include_web_api=True,
    )
    assert (tmp_path / "app" / "main.py").exists()
    assert (tmp_path / "alembic").exists()
    assert (tmp_path / "notebooks").exists()
    assert (tmp_path / "data" / "DEIDENTIFICATION.md").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    deps = pyproject_toml["project"]["dependencies"]
    assert any("fastapi" in d for d in deps)
    assert any("polars" in d for d in deps)
    assert (tmp_path / "tests" / "test_app.py").exists()


def test_combo_guards_reject_incompatible_bases(tmp_path: Path):
    """Forcing a combo opt-in on a non-combinable base (ros2 / script / ...)
    must not leak the layered artifacts: the combinable guard keeps them out."""
    copy_project(tmp_path, project_type="script", include_web_api=True)
    assert not (tmp_path / "app").exists()
    assert not (tmp_path / "alembic").exists()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert not any("fastapi" in d for d in pyproject_toml["project"]["dependencies"])
