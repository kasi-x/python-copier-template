# References

External sources consulted during template design, kept to what actually
shaped the output. Consulted-but-rejected sources are not listed.

## MCP scaffold

- <lt-m v="["/>MCP Python SDK で MCP サーバーを作ってみる<lt-m v="](https://zenn.dev/kiitosu/articles/31f55b99c33ce5)"/>
  (Zenn, 2025/06) — v1-era intro, but its three-primitive layout (tool /
  resource / prompt) confirmed the scaffold was missing `prompt` and
  resource templates. Led to `review_code` + `greeting://{name}`.
- <lt-m v="["/>mcp-cookie-cutter<lt-m v="](https://github.com/codingthefuturewithai/mcp-cookie-cutter)"/>
  — example-rich but pinned to SDK `<2.0` (`FastMCP`), so the foundation
  predates this template's v2 (`MCPServer`) port. Only the example breadth
  was referenced; its decorator layer, Streamlit UI, SQLite logging and
  JIRA DevFlow were judged out of scope.
- <lt-m v="["/>MCP Deploy & scale<lt-m v="](https://py.sdk.modelcontextprotocol.io/run/deploy/)"/> —
  official SDK docs. Basis for the "no MCP-specific Docker recipe" position
  in the <lt-m v="["/>MCP how-to<lt-m v="](../how-to/mcp.md)"/>: process management and auth stay
  outside the scaffold.
- <lt-m v="["/>modelcontextprotocol/servers<lt-m v="](https://github.com/modelcontextprotocol/servers)"/> —
  the official reference implementations (educational, not production-ready).
  Basis for the <lt-m v="["/>distribution recipe<lt-m v="](../how-to/mcp-distribute.md)"/>: the
  `everything` shape reference, the `filesystem` access-control pattern, and
  the `uvx mcp-server-<name>` + registry publication model.
- <lt-m v="["/>Model Context Protocol<lt-m v="](https://modelcontextprotocol.io)"/> — the spec
  itself. Referenced for transport status (SSE deprecated → streamable-http)
  and `TransportSecuritySettings` semantics.
