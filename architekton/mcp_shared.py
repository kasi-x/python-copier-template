#!/usr/bin/env python3
"""Shared MCP server instance and path conventions for the template's own tooling.

This is the one owner of the `server` object: every `architekton/mcp_*.py` module
registers its `@server.tool()` / `@server.resource()` / `@server.custom_route()`
handlers against this instance at import time, and `architekton/mcp_server.py`
(the compat entry point) re-exports it. Registration takes the server as a
*parameter* of `register_*()`, never as a module global imported from the
shim, so the leaves stay importable without a cycle back to the entry point.

`repo_root()` is the one read of the checkout root: the shim owns `TOP`
(tests monkeypatch `architekton.mcp_server.TOP`), and the leaves call this lazily
at tool time rather than binding the path at import.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from typing import cast

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from architekton import batch  # noqa: E402
from architekton import mcp_interface  # noqa: E402
from mcp.server import MCPServer  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402

OUTPUT_LIMIT = batch.OUTPUT_LIMIT

# What the model is told on connect: architekton/mcp_interface.yml, the developers'
# view until main() narrows it with --audience.
server = MCPServer("architekton-py", instructions=mcp_interface.instructions())


def repo_root() -> Path:
    """This checkout's root: the `TOP` the shim owns (monkeypatched in tests)."""
    mod = sys.modules.get("architekton.mcp_server")
    top = getattr(mod, "TOP", None) if mod is not None else None
    if isinstance(top, Path):
        return top
    return TOP


@server.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    """Liveness probe for an orchestrator (unauthenticated, no data).

    A custom route is a plain Starlette route, so it bypasses the Host
    allowlist that guards /mcp -- the same trade the generated scaffold makes,
    and why this one answers nothing but "the process is up".
    """
    return JSONResponse({"status": "ok"})


def allowed_hosts() -> TransportSecuritySettings | None:
    """Turn MCP_ALLOWED_HOSTS / MCP_ALLOWED_ORIGINS into the SDK's settings."""
    raw_hosts = os.environ.get("MCP_ALLOWED_HOSTS")
    if not raw_hosts:
        return None
    hosts = [host.strip() for host in raw_hosts.split(",") if host.strip()]
    raw_origins = os.environ.get("MCP_ALLOWED_ORIGINS")
    if not raw_origins:
        return TransportSecuritySettings(allowed_hosts=hosts)
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins)


def serve(args: Sequence[str] | None, *, audience: str, description: str) -> None:
    """Narrow `server` to an audience and run it over stdio (default) or Streamable HTTP."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (streamable-http)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (streamable-http)")
    parser.add_argument(
        "--audience",
        choices=mcp_interface.AUDIENCES,
        default=audience,
        help="users: generate/adopt/update only; developers: also the template-development tools",
    )
    parsed = parser.parse_args(args)
    mcp_interface.apply(server, cast(str, parsed.audience))
    transport = cast(Literal["stdio", "streamable-http"], parsed.transport)
    if transport == "streamable-http":
        host = cast(str, parsed.host)
        if host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("MCP_ALLOWED_HOSTS"):
            parser.error(
                "binding to a non-local host requires MCP_ALLOWED_HOSTS "
                "(comma-separated host allowlist) so the server does not "
                "accept every Host header"
            )
        server.run(transport=transport, host=host, port=cast(int, parsed.port), transport_security=allowed_hosts())
    else:
        server.run(transport="stdio")
