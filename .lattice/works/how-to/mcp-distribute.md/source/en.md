# Distributing an MCP server

How to turn the <lt-m v="["/>MCP scaffold<lt-m v="](mcp.md)"/> into a standalone,
redistributable server of the <lt-m v="["/>reference-servers<lt-m v="][servers]"/> kind: a PyPI
package strangers can run with `uvx` and register with any MCP host.

This page is about <lt-m v="**"/>packaging and distribution<lt-m v="**"/>. Building the server
itself (tools, resources, prompts, transports) is covered in
<lt-m v="["/>MCP server scaffolding<lt-m v="](mcp.md)"/>; production HTTP operation (compose,
replicas, auth) is <lt-m v="["/>Running an MCP Server in Production<lt-m v="](mcp-production.md)"/>.

## What the scaffold already gives you

Answering <lt-m v="**"/>Yes<lt-m v="**"/> to `include_mcp` produces a package that is one
`pypi: true` answer away from being distributable:

- a `[project.scripts]` entry `mcp-server-<name>` pointing at
  `mcp_server:main`, so the server is a real console script, not a file
  path users must know;
- a `.mcp.json` registering the local stdio command (`uv run
  mcp-server-<name>`) with hosts that read project-scope config;
- the `mcp[cli]>=2.0.1,<3` dependency — the SDK plus its `mcp`
  (`dev` / `run` / `install`) command;
- an in-process client test that doubles as usage documentation.

Nothing else needs generating. The remaining work is turning the
example into <lt-m v="*"/>your<lt-m v="*"/> server and publishing it.

## The recipe

### 1. Replace the example surface with real tools

`add` / `divide`, `project://about` and `review_code` are placeholders
that teach the three primitives (tool / resource / prompt). Before
publishing, replace them with the narrowest tools your server needs —
one capability per tool, validated arguments, `ToolError` for anything
out of bounds. The <lt-m v="["/>reference servers<lt-m v="][servers]"/> are a good shape
reference here: the `everything` server shows the full primitive
catalogue, and the `filesystem` server shows access controls done
right (configurable allowed directories, not the whole disk). They are
explicitly <lt-m v="*"/>educational, not production-ready<lt-m v="*"/> — copy the structure,
not the code, and evaluate your own threat model.

Keep the in-process test pattern (`Client` against the module-level
`server` object): it runs with no port and no subprocess, so it keeps
working in CI after publishing exactly as it did before.

### 2. Answer `pypi: true` and publish with trusted publishing

The `pypi` question (asked whenever `use_recommended_integrations` is
declined) wires the release workflow (`_pypi.yml`) that uploads the
wheel and sdist on every tag push via PyPI trusted publishing (OIDC —
no long-lived token). Setup is a one-time PyPI-side step, covered in
<lt-m v="["/>Setting up PyPI publishing<lt-m v="](pypi.md)"/>.

Versioning needs no action: generated projects version from git tags
(`dynamic = ["version"]` via setuptools-scm), so tagging a release
versions the distribution on PyPI automatically.

The name users `pip install` is `distribution_name` (default: the repo
name); the command they run is the console script `mcp-server-<name>`,
derived from `repo_name`. The two default to the same string, which is
why `uvx mcp-server-<name>` just works after publishing.

### 3. Keep the SDK pin policy

The scaffold pins `mcp[cli]>=2.0.1,<3`. The `<3` cap is deliberate, not
stale: the v1→v2 migration broke every unpinned consumer (`FastMCP`
moved to `MCPServer`, SSE was removed), and the cap is what stops the
next major from silently breaking installs. When a v3 lands, bump the
floor and cap together after the render matrix stays green — Renovate
proposes the floor bumps; the cap move is a conscious decision, tested
by the generated `test_mcp_server.py`.

### 4. Point hosts at the published package

Locally, `.mcp.json` launches `uv run mcp-server-<name>` from the
checkout. Once published, users have no checkout — swap the command to
`uvx`:

```json
{
  "mcpServers": {
    "<name>": {
      "command": "uvx",
      "args": ["mcp-server-<name>"],
      "env": {}
    }
  }
}
```

`uvx` resolves, installs into an ephemeral environment, and launches —
no install step for the user. Beyond project-scope `.mcp.json`:

- <lt-m v="**"/>Claude Code / Claude Desktop<lt-m v="**"/>: `claude mcp add <name> -- uvx
  mcp-server-<name>` (stdio), or the streamable-http URL after starting
  the server;
- <lt-m v="**"/>MCP Inspector<lt-m v="**"/>: `uvx` works there too for a pre-publish smoke
  test — `mcp dev` against the local file during development, then the
  `uvx` command against the published wheel to verify what strangers
  get;
- <lt-m v="**"/>Discovery<lt-m v="**"/>: list the server on the <lt-m v="["/>MCP Registry<lt-m v="][registry]"/> so
  hosts and users can find it; that is the directory the reference
  servers README points at, not the servers repo itself.

### 5. Keep stdio the default

Ship stdio as the primary transport (it is the scaffold default and
what every host launches). Streamable HTTP is for serving over a port —
local debugging and the Docker path the scaffold already documents —
not for distribution: a `uvx` user expects a child process, not a port
to manage. If you do serve remotely, the scaffold's rules travel with
the package: non-local binds require `MCP_ALLOWED_HOSTS`, and `/health`
stays an unauthenticated liveness probe (see <lt-m v="["/>mcp.md<lt-m v="](mcp.md)"/>).

## Checklist

- [ ] Example tools replaced with narrow, validated, least-privilege tools
- [ ] `pypi: true` answered; trusted publisher configured (<lt-m v="["/>how-to<lt-m v="](pypi.md)"/>)
- [ ] First release tagged → installable; `uvx mcp-server-<name>` smoke-tested
- [ ] `.mcp.json` (or host config) documented with the `uvx` command
- [ ] SDK pin still `mcp[cli]>=2.0.1,<3` (cap moved only with a verified bump)
- [ ] Registry listing added for discovery

## Related

- <lt-m v="["/>MCP Server Scaffolding<lt-m v="](mcp.md)"/> — the generated server, transports,
  and security notes for developers and operators.
- <lt-m v="["/>Setting up PyPI publishing<lt-m v="](pypi.md)"/> — the trusted-publisher setup
  this recipe relies on.
- <lt-m v="["/>MCP Deploy & scale<lt-m v="](https://py.sdk.modelcontextprotocol.io/run/deploy/)"/> —
  official SDK docs; why process management and auth stay outside the
  scaffold.

[servers]: https://github.com/modelcontextprotocol/servers
[registry]: https://registry.modelcontextprotocol.io/
