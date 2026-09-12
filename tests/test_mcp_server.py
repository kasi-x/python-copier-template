"""Tests for tools/mcp_server.py: the tooling exposed over MCP.

The in-process client below is the same pattern the generated MCP scaffold
ships in its own tests (`mcp.Client` against the server object, no
subprocess, no port), so this file also documents how to call the server from
your own code.
"""

import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.types import TextContent
from mcp.types import TextResourceContents

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import mcp_server  # noqa: E402

BASE_ANSWERS = {
    "package_name": "mcp_example",
    "description": "An example project",
    "git_platform": "github.com",
    "github_org": "kasi-x",
    "author_name": "kasi-x",
    "author_email": "kashimiya.exe@gmail.com",
    "repo_name": "mcp-example",
    "distribution_name": "mcp-example",
}

TOOL_NAMES = {
    "adopt_project",
    "inspect_project",
    "list_batch_requests",
    "list_questions",
    "render_project",
    "run_batch",
    "template_status",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[Client]:
    async with Client(mcp_server.server, raise_exceptions=True) as c:
        yield c


async def call(client: Client, name: str, arguments: dict | None = None) -> Any:
    result = await client.call_tool(name, arguments or {})
    assert result.is_error is False, result.content
    assert isinstance(result.content[0], TextContent)
    return json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_every_tool_is_registered_with_a_description(client: Client):
    """A tool without a docstring is a tool the model cannot choose."""
    tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == TOOL_NAMES
    for tool in tools:
        assert tool.description, f"{tool.name} needs a docstring (it is the tool description)"


@pytest.mark.anyio
async def test_list_questions_filters_internal_variables(client: Client):
    asked = (await call(client, "list_questions"))["questions"]
    everything = (await call(client, "list_questions", {"asked_only": False}))["questions"]
    assert len(everything) > len(asked) >= 60
    assert all(entry["internal"] is False for entry in asked)
    assert any(entry["internal"] is True for entry in everything)
    assert asked[0]["name"] == "project_type"
    assert "help" in asked[0] and "default" in asked[0]


@pytest.mark.anyio
async def test_questionnaire_resource(client: Client):
    result = await client.read_resource("template://questionnaire")
    assert isinstance(result.contents[0], TextResourceContents)
    payload = json.loads(result.contents[0].text)
    assert payload["questions"][0]["name"] == "project_type"
    assert len(payload["questions"]) >= 108


@pytest.mark.anyio
async def test_template_status_reports_the_checkout(client: Client):
    status = await call(client, "template_status")
    assert isinstance(status, dict)
    assert status["questions"] >= 108
    assert status["asked_questions"] < status["questions"]
    assert isinstance(status["dirty"], bool)
    assert status["latest_tag"], "the checkout has tags; the trap is that they are stale"
    assert status["commits_behind_latest_tag"] is None or status["commits_behind_latest_tag"] >= 0
    assert mcp_server.template_status()["repo"] == str(TOP), "the plain function is the same call"


@pytest.mark.anyio
async def test_inspect_project_reports_mode_and_collisions(client: Client, tmp_path: Path):
    (tmp_path / "src" / "legacy").mkdir(parents=True)
    (tmp_path / "src" / "legacy" / "__init__.py").write_text("")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "legacy"\ndescription = "legacy"\n')
    (tmp_path / "README.md").write_text("# mine\n")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("# mine\n")

    detection = await call(client, "inspect_project", {"path": str(tmp_path)})
    assert isinstance(detection, dict)
    assert detection["mode"] == "adopt"
    assert detection["suggested_answers"]["existing_project"] is True
    assert detection["suggested_answers"]["package_name"] == "legacy"
    assert ".github/workflows/ci.yml" in detection["collisions"]
    assert "README.md" in detection["kept"]
    assert mcp_server.inspect_project(str(tmp_path))["mode"] == "adopt"


@pytest.mark.anyio
async def test_inspect_project_reports_a_foreign_template(client: Client, tmp_path: Path):
    (tmp_path / ".copier-answers.yml").write_text("_src_path: https://github.com/other/template.git\n")
    detection = await call(client, "inspect_project", {"path": str(tmp_path)})
    assert detection["mode"] == "foreign"
    assert detection["foreign_src"] == "https://github.com/other/template.git"
    taken = await call(client, "inspect_project", {"path": str(tmp_path), "takeover": True})
    assert taken["mode"] == "adopt" and taken["took_over"] is True


@pytest.mark.anyio
async def test_render_project_keeps_stdout_clean(client: Client, tmp_path: Path, capfd: pytest.CaptureFixture[str]):
    """A stdio MCP server's stdout is the protocol channel: copier's chatter
    must land on stderr, which is what report_stream_only() guarantees."""
    dest = tmp_path / "rendered"
    result = await call(
        client,
        "render_project",
        {"answers": {**BASE_ANSWERS, "project_type": "script"}, "dest": str(dest)},
    )
    assert isinstance(result, dict)
    assert result["dest"] == str(dest)
    assert "pyproject.toml" in result["files"]
    assert "README.md" in result["files"]
    assert result["file_count"] == len(result["files"])

    captured = capfd.readouterr()
    assert captured.out == "", "rendering wrote to stdout, which would corrupt the MCP session"
    assert (dest / "pyproject.toml").is_file()


@pytest.mark.anyio
async def test_adopt_project_plans_then_applies(client: Client, tmp_path: Path):
    """dry_run plans without writing; applying keeps the adopter's files."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("# MY OWN CI\n")
    (tmp_path / "README.md").write_text("# mine\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "legacy"\nversion = "0"\n')

    plan = await call(client, "adopt_project", {"path": str(tmp_path), "ref": "HEAD"})
    assert plan["ok"] and plan["applied"] is False
    assert plan["skip"] == [".github/workflows/ci.yml"]
    assert plan["deps"]["added"]["dev"], "the plan includes the dependency merge"
    assert (tmp_path / "README.md").read_text() == "# mine\n"

    applied = await call(client, "adopt_project", {"path": str(tmp_path), "ref": "HEAD", "dry_run": False})
    assert applied["ok"] and applied["applied"] is True
    assert applied["created_count"] > 0
    assert (tmp_path / ".github" / "workflows" / "ci.yml").read_text() == "# MY OWN CI\n"
    assert (tmp_path / "README.md").read_text() == "# mine\n"
    assert (tmp_path / ".gitleaks.toml").exists()
    assert "[dependency-groups]" in (tmp_path / "pyproject.toml").read_text()


@pytest.mark.anyio
async def test_adopt_project_refuses_a_foreign_template(client: Client, tmp_path: Path):
    (tmp_path / ".copier-answers.yml").write_text("_src_path: https://github.com/other/template.git\n")
    result = await client.call_tool("adopt_project", {"path": str(tmp_path)})
    assert result.is_error is True
    assert "another copier template" in str(result.content)


@pytest.mark.anyio
async def test_run_batch_reports_a_verdict(client: Client, tmp_path: Path):
    jsonl = tmp_path / "requests.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "id": "script-case",
                "answers": {**BASE_ANSWERS, "project_type": "script"},
                "expect": {"files": ["mcp_example/__init__.py"], "absent": ["src"]},
            }
        )
        + "\n"
    )
    verdict = await call(client, "run_batch", {"jsonl": str(jsonl)})
    assert isinstance(verdict, dict)
    assert verdict["ok"] is True
    assert [line["id"] for line in verdict["lines"]] == ["script-case"]
    assert verdict["lines"][0]["checks"][0]["name"] == "render"


@pytest.mark.anyio
async def test_list_batch_requests_reads_the_shipped_batch(client: Client):
    requests = (await call(client, "list_batch_requests", {"jsonl": str(TOP / "batches" / "smoke.jsonl")}))["requests"]
    assert len(requests) == 8
    assert requests[0]["id"] == "library-recommended"
    assert any(request["has_update"] for request in requests)


@pytest.mark.anyio
async def test_bad_input_is_a_tool_error(client: Client):
    result = await client.call_tool("list_batch_requests", {"jsonl": "/nonexistent/requests.jsonl"})
    assert result.is_error is True
    assert "cannot read" in str(result.content)
