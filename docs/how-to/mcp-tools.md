# Develop the Template With Its MCP Server

The template's MCP server has two audiences, and this page is for the second:

- **Users** generate, adopt or update a project. They install
  `architekton-py mcp` and get only those tools:
  [Generate a Project With an AI Agent](../tutorials/with-an-agent.md).
- **Developers** change the template itself (`template/`, `partials/`,
  `questions/`). In this checkout the server also serves the tools below,
  which prove that an edit changed only what it meant to.

Nothing to configure: the repository ships a project-scope `.mcp.json`, and
an MCP host that reads one (Claude Code, VS Code, Cursor, ...) starts the
developers' server as soon as you open the checkout.

## Run it

```shell
task mcp                                                     # stdio, every tool
uv run --locked python architekton/mcp_server.py --audience users   # what users get
task mcp CLI_ARGS="--transport streamable-http"              # serve it on 127.0.0.1:8000
uv run mcp dev architekton/mcp_server.py                     # MCP Inspector (needs npx)
```

`.mcp.json` registers the same stdio command `task mcp` runs:

```json
{
  "mcpServers": {
    "architekton-py": {
      "command": "uv",
      "args": ["run", "--locked", "python", "architekton/mcp_server.py"],
      "env": {}
    }
  }
}
```

## Tools only developers get

Besides the users' ten, the developers' server adds these. The effect column
is the same classification as on the users' page, plus `run`: the tool
runs commands (a batch file's checks, this repository's tests) and can do
anything they do, so hosts ask before calling it.

| Tool | Use it for | Effect |
| --- | --- | --- |
| `render_diff` | two answer sets rendered and compared file by file | render |
| `lint_render` | a render linted the way the generated project lints | render |
| `list_batch_requests` | the requests in a batch file | read |
| `run_batch` | a batch file's verdict | run |
| `list_witnesses` | the answer combinations the suite covers | read |
| `recommend_answers` | the covered combinations that match named constraints | render |
| `run_witness` | those combinations' verdicts, by tier | run |
| `run_tests` | the repository's own test tiers | run |
| `template_fingerprint` | a hash of everything a render depends on | read |

`render_project` takes `validate=False` here to force an answer combination
the questionnaire would never ask.

## Change what agents are told

What an agent learns on connect -- the tools per audience, the step each
belongs to, what each may touch, what to call after `inspect_project` -- is
one data file, `architekton/mcp_interface.yml`. It becomes the server's
`instructions`, each tool's MCP annotations and the users' tool set.
Preview what an audience is told:

```shell
uv run --locked python architekton/mcp_interface.py --audience users
```

A tool's own contract (its arguments, return shape and cost) is its
docstring, written for the agent: what it does, what it returns, what it
costs, nothing about how it works inside. Put maintainer notes in code
comments. `tests/test_mcp_interface.py` keeps the file, the server and the
two pages' tables in step; `tests/test_mcp_server.py` checks every
docstring names its return shape and its cost.

Which entry point loads what is the distribution boundary:
`architekton/mcp_users.py` imports only the users' modules, so
`architekton-py mcp` runs on the package's runtime dependencies;
`architekton/mcp_server.py` adds `architekton/mcp_witness.py`, which needs the
dev group (z3, pytest).

## Resources

| Resource | Payload |
| --- | --- |
| `template://questionnaire` | the full questionnaire as JSON, internal variables included |
| `template://witnesses` | each witness leaf with its recorded tier and result, plus the ledger's coverage counters |
| `template://support` | the declared support contract (`tests/matrix/support.yml`) |

## The HTTP transport and its allowlist

Binding to localhost is safe by default: the SDK arms its DNS-rebinding
protection for a local bind, and `main()` adds `MCP_ALLOWED_HOSTS` on top when
you set it. Binding anywhere else (`--host 0.0.0.0`, e.g. inside a container)
**requires** `MCP_ALLOWED_HOSTS`, because the SDK's protection is only
automatic for localhost; the server refuses to start rather than accept every
`Host` header.

- `MCP_ALLOWED_HOSTS` -- comma-separated; a `host:*` entry matches any port.
- `MCP_ALLOWED_ORIGINS` -- optional, comma-separated, checked after the Host.
- `GET /health` -- an unauthenticated liveness probe for an orchestrator. Like
  every SDK custom route it is a plain Starlette route, so it **bypasses** the
  allowlist and returns `{"status": "ok"}` to anyone; it exposes no data.

That scope is not a claim, it is tested: `tests/test_mcp_server.py` starts the
real server on `127.0.0.1` (no venv, no network) and pins a foreign `Host` at
421 on `/mcp` with `/health` still 200, a foreign `Origin` at 403, and an
allowed `Host` completing an `initialize` handshake at 200.

## Relationship to the generated scaffold's server

Two MCP servers exist in this repository, and they stay separate on purpose:

| | `architekton/mcp_server.py` (this one) | `template/{% if web_api %}app{% endif %}/{% if mcp_effective %}mcp_server.py{% endif %}.jinja or template/{% if pkg_scaffold %}{{ pkg_dir }}{% endif %}/{% if mcp_effective %}mcp_server.py{% endif %}.jinja` |
| --- | --- | --- |
| Serves | the template's maintenance loop | the generated project, after `include_mcp` |
| Audience | an agent editing the template | the project's own users and their hosts |
| Tools | render, inspect, adopt, batch, witnesses | a worked example: typed tools, a `ToolError`, resources, a prompt |
| Shipped as | a repo script (`task mcp`) | `<pkg>/mcp_server.py` + a console script, `uvx`-runnable once published |

They share no code and import nothing from each other: a generated project is
copied out, released and installed on its own, so it must never depend on this
repository -- and this repository must not grow a dependency on one project
type's shape. The only idea that appears in both is the `MCP_ALLOWED_HOSTS`
rule plus `/health`, about thirty lines of SDK glue re-derived from the SDK API
in each; keeping the second copy is what lets either side change its transport
settings without a release coupling. Their dependency handling differs too,
deliberately: the generated scaffold's deptry config ignores the starlette
import its `custom_route` needs (`DEP001=starlette`, plus `DEP003`), while this
repository declares `starlette` in its dev group and imports it directly.

Fix a generated project's server in `template/{% if web_api %}app{% endif %}/{% if mcp_effective %}mcp_server.py{% endif %}.jinja or template/{% if pkg_scaffold %}{{ pkg_dir }}{% endif %}/{% if mcp_effective %}mcp_server.py{% endif %}.jinja` (and
[the MCP how-to](mcp.md) describes what it ships); add a tool to one of the `architekton/mcp_*.py` modules and list it in
`architekton/mcp_interface.yml`.

## Related

- [Serve an MCP Server from a Generated Project](mcp.md) -- the scaffold, its
  security notes for developers and for users/operators.
- [Check a Change Without the Full Test Suite](test-loop.md) -- the same
  capabilities from the shell (`task batch`, `pytest -m`), and the tier model
  `run_witness` follows.
- [Verification Architecture](../explanations/verification.md) -- what the
  `fast`, `full` and `slow` tiers observe, and what the 272 leaves are.
