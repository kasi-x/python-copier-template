"""architekton/mcp_interface.yml is what an agent is told, and it is complete.

The file lists every MCP tool once, per audience, with the effect that
becomes its annotations; the server registers exactly those tools; each
audience's instructions name exactly its tools; and each audience's how-to
lists the same tools as its table, so the two how-tos and the server cannot
drift apart.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from architekton import mcp_interface  # noqa: E402
from architekton import mcp_server  # noqa: E402

HOW_TOS = {
    "users": TOP / "docs" / "tutorials" / "with-an-agent.md",
    "developers": TOP / "docs" / "how-to" / "mcp-tools.md",
}


def _registered() -> set[str]:
    return {tool.name for tool in mcp_server.server._tool_manager.list_tools()}  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def test_every_registered_tool_is_listed_once():
    listed = [name for audience in mcp_interface.AUDIENCES for name in mcp_interface._own_tools(audience)]  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    assert len(listed) == len(set(listed)), "a tool belongs to one audience"
    assert set(listed) == _registered()


def test_annotations_follow_the_effect():
    effects = mcp_interface.load()["effects"]
    for tool in mcp_server.server._tool_manager.list_tools():  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        effect = effects[mcp_interface.tools()[tool.name]["effect"]]
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is effect["read_only"], tool.name
        assert tool.annotations.destructive_hint is effect["destructive"], tool.name


@pytest.mark.parametrize("audience", mcp_interface.AUDIENCES)
def test_instructions_name_exactly_the_audiences_tools(audience: str):
    text = mcp_interface.instructions(audience)
    named = set(re.findall(r"^- ([a-z_]+) \[", text, re.MULTILINE))
    assert named == set(mcp_interface.tools(audience))


def test_users_never_see_the_developer_tools():
    users = set(mcp_interface.tools("users"))
    developers_only = set(mcp_interface.tools("developers")) - users
    assert developers_only, "the developers' list adds tools"
    assert not developers_only & set(re.findall(r"[a-z_]+", mcp_interface.instructions("users")))


@pytest.mark.parametrize("audience", mcp_interface.AUDIENCES)
def test_each_how_to_lists_its_audiences_tools(audience: str):
    text = HOW_TOS[audience].read_text(encoding="utf-8")
    tabled = set(re.findall(r"^\| `([a-z_]+)` \|", text, re.MULTILINE))
    assert tabled == set(mcp_interface._own_tools(audience)), HOW_TOS[audience].name  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def test_every_mode_has_a_next_step():
    """detect.detect_mode's four answers each point somewhere."""
    for mode in ("fresh", "adopt", "update", "foreign"):
        assert mcp_interface.next_for_mode(mode), mode
