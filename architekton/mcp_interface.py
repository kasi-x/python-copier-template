#!/usr/bin/env python3
"""What the MCP server tells an agent, read from architekton/mcp_interface.yml.

The YAML file is the one place that says which tools exist for whom (users
generating a project vs developers changing the template), what each may
touch, and which to call when. This module only turns it into MCP terms: the
server `instructions`, each tool's annotations, the audience's tool set, and
inspect_project's `next` hint.

Usage:

    python architekton/mcp_interface.py                       # the developers' instructions
    python architekton/mcp_interface.py --audience users      # what a user's agent is told
"""

from __future__ import annotations

import argparse
import functools
from collections.abc import Callable
from pathlib import Path
from typing import Any
from typing import TypeVar

import yaml
from mcp.types import ToolAnnotations

INTERFACE_FILE = Path(__file__).with_name("mcp_interface.yml")

#: The audiences, narrowest first: each serves its own tools plus every earlier one's.
AUDIENCES = ("users", "developers")

_F = TypeVar("_F", bound=Callable[..., Any])


@functools.cache
def load() -> dict[str, Any]:
    """The parsed interface file."""
    return yaml.safe_load(INTERFACE_FILE.read_text(encoding="utf-8"))


def _own_tools(audience: str) -> dict[str, dict[str, str]]:
    """The tools one audience's groups list, name -> {effect, use}, in file order."""
    groups = load()["audiences"][audience]["groups"]
    own = {name: entry for group in groups for name, entry in group["tools"].items()}
    for name, entry in own.items():
        # An unquoted comma inside `{use: ...}` silently starts another key.
        if set(entry) != {"effect", "use"}:
            msg = f"{INTERFACE_FILE.name}: {name} must have exactly `effect` and `use` (quote a `use` with a comma)"
            raise ValueError(msg)
    return own


def tools(audience: str = "developers") -> dict[str, dict[str, str]]:
    """Every tool `audience` is served: its own and the narrower audiences'."""
    served: dict[str, dict[str, str]] = {}
    for name in AUDIENCES[: AUDIENCES.index(audience) + 1]:
        served.update(_own_tools(name))
    return served


def tool_annotations(tool: str) -> ToolAnnotations:
    """The MCP annotations for `tool`, from its effect."""
    effect = load()["effects"][tools()[tool]["effect"]]
    return ToolAnnotations(
        read_only_hint=effect["read_only"],
        destructive_hint=effect["destructive"],
        idempotent_hint=effect["idempotent"],
        open_world_hint=effect["network"],
    )


def tool(server: Any) -> Callable[[_F], _F]:
    """`@server.tool()` with the annotations the interface file gives the function's name."""

    def decorate(fn: _F) -> _F:
        return server.tool(annotations=tool_annotations(fn.__name__))(fn)

    return decorate


def next_for_mode(mode: str) -> str | None:
    """What to call after inspect_project reports `mode`."""
    return load()["next_by_mode"].get(mode)


def instructions(audience: str = "developers") -> str:
    """The text every MCP host hands the model on connect: summaries, groups, tools, effects."""
    data = load()
    lines: list[str] = []
    served = AUDIENCES[: AUDIENCES.index(audience) + 1]
    for name in served:
        part = data["audiences"][name]
        lines += ["", f"For {name}: {part['summary']}"] if lines else [f"For {name}: {part['summary']}"]
        for group in part["groups"]:
            lines.append(f"{group['name']}")
            lines += [
                f"- {tool_name} [{entry['effect']}]: {entry['use']}" for tool_name, entry in group["tools"].items()
            ]
    used = {entry["effect"] for entry in tools(audience).values()}
    lines += ["", "Effects:"]
    lines += [f"- {name}: {effect['says']}" for name, effect in data["effects"].items() if name in used]
    return "\n".join(lines)


def apply(server: Any, audience: str) -> None:
    """Narrow `server` to `audience`: drop the other tools, set its instructions."""
    keep = tools(audience)
    for name in tools():
        if name not in keep and name in registered(server):
            server.remove_tool(name)
    # WHYNOT: the SDK takes instructions only at construction; the audience is
    # known later (a command-line flag), and this is the one attribute it reads.
    server._lowlevel_server.instructions = instructions(audience)  # noqa: SLF001


def registered(server: Any) -> set[str]:
    """The tool names `server` currently serves."""
    # WHYNOT: the SDK lists tools only through the async protocol handler.
    return {entry.name for entry in server._tool_manager.list_tools()}  # noqa: SLF001


def main(argv: list[str] | None = None) -> int:
    """Print the instructions an audience's agent receives."""
    parser = argparse.ArgumentParser(description="Print what the MCP server tells an agent.")
    parser.add_argument("--audience", choices=AUDIENCES, default="developers")
    print(instructions(parser.parse_args(argv).audience))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
