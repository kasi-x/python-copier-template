# Generate a Project With an AI Agent

`architekton-py mcp` is an MCP server: an agent (Claude Code, an IDE agent, any
MCP host) uses it to create, adopt or update a project from this template.
You only register it; the agent learns the tools from the server itself.

## Register it

Claude Code:

```shell
claude mcp add architekton-py -- uvx --from git+https://github.com/politeuma/architekton-py.git architekton-py mcp
```

Any other MCP host (`mcp.json` / `claude_desktop_config.json` style):

```json
{
  "mcpServers": {
    "architekton-py": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/politeuma/architekton-py.git", "architekton-py", "mcp"]
    }
  }
}
```

The first start clones the template into `~/.cache/architekton-py/repo` (one
network fetch); later starts refresh it.

## What the agent gets

Four steps, in order. The `effect` column is what a tool may touch; hosts
use it to decide which calls run without asking you.

| Tool | Use it for | Effect |
| --- | --- | --- |
| `template_status` | which template revision a render would use | read |
| `inspect_project` | before writing to a directory: its `mode` picks the generate tool | read |
| `suggest_config` | requirement words -> ranked presets | read |
| `list_presets` | the ready-made answer sets | read |
| `list_questions` | every question with its choices and default | read |
| `explain_choice` | why a preset or an answer, in the template's own words | read |
| `validate_answers` | before generating: names each wrong answer and why | read |
| `render_project` | mode `fresh`: a new project | render |
| `adopt_project` | mode `adopt`: an existing project this template did not make | change |
| `update_project` | mode `update`: a project this template made, to a newer template | change |

- **read** looks only.
- **render** writes a new project into a new or empty directory.
- **change** changes an existing project. Both `change` tools default to
  `dry_run`, which shows the plan first and writes nothing.

## What to expect

The agent proposes the shape of your project (`project_type`, the
`include_*` layers) and asks you to confirm before it generates anything.
`adopt_project` and `update_project` show you their plan first. An update
works on a committed git repository and leaves any conflicts in the files
for you (or the agent) to resolve before you commit.

## Related

- [Create New Project](create-new.md) and [Adopt Existing](adopt-existing.md):
  the same operations from the command line.
- [Develop the Template With Its MCP Server](../how-to/mcp-tools.md): the
  extra tools for people changing the template itself.
