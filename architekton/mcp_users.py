#!/usr/bin/env python3
"""The MCP server people install: generate, adopt or update a project.

What a user's agent needs and nothing else -- the users' tools in
architekton/mcp_interface.yml. It imports only the modules those tools live in,
so it runs on the package's runtime dependencies (no z3, no pytest); the
template-development tools stay in architekton/mcp_server.py, which a checkout's
.mcp.json starts.

Run it the way docs/tutorials/with-an-agent.md registers it:

    uvx --from git+https://github.com/politeuma/architekton-py.git architekton-py mcp
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from architekton.mcp_project import register_project  # noqa: E402
from architekton.mcp_questionnaire import register_questionnaire  # noqa: E402
from architekton.mcp_render_loop import register_render_loop  # noqa: E402
from architekton.mcp_shared import serve  # noqa: E402
from architekton.mcp_shared import server  # noqa: E402

register_questionnaire(server)
register_project(server)
register_render_loop(server)


def main(args: Sequence[str] | None = None) -> None:
    """Run the users' server (stdio by default)."""
    serve(args, audience="users", description="MCP server for architekton-py: generate, adopt or update a project")


if __name__ == "__main__":
    main()
