# How to check a change without running the full suite

Three speeds are available, from "did this one combination render" to "is
everything still green". Pick by what you changed.

| Check | Command | Wall time (measured, 16-core, warm caches) |
| --- | --- | --- |
| One request | `task batch CLI_ARGS="--only web-api --prepare --shell"` | ~2s |
| Fast tier | `task test-fast` | ~17s |
| Full suite | `task test` | ~37s (≈110s cold) |

The full suite's cost is concentrated in a handful of tests that build a
virtualenv and install dependencies (`uv sync`) per case — `pytest
--durations=25` on this repository puts `test_template_defaults` (24s),
`test_template_include_scraping_runs` (21s) and
`test_template_web_api_runs_in_process` (16s) at the top, all in
`tests/test_example.py`. `task test-fast` skips those two files entirely
(`test_example.py`, `test_generated_typecheck.py`); everything else — the
structure/machine-gate/QA checks, the render-and-lint matrix, this
repository's own tooling tests — still runs, so a template edit is still
covered by the render matrix.

Use `task test-heavy` for just the slow tier before pushing.

## Investigating one combination

`tools/batch.py` renders real projects from a JSONL request list
([Run a Batch of Generation Requests](batch.md)). For investigation, run a
single line and keep what it produced:

```shell
task batch CLI_ARGS="--only '^web-api' --prepare --keep"
```

- `--only REGEX` selects the request id.
- `--prepare` installs the rendered project's environment, choosing the
  command from the files that were rendered (`uv sync`, `pixi install` or
  `poetry install`).
- `--keep` leaves the work directory so you can read the files.
- `--shell` drops you into the rendered project, so the loop is "render one
  case, poke at it, fix the template, re-render" without pytest in between.

Adding an `expect` block to the request turns the same run into a verdict
(`PASS`/`FAIL`, exit 1 on failure), which is how a fix becomes a regression
guard.

## The same capabilities over MCP

`tools/mcp_server.py` exposes the tooling to an MCP host (an agent, an IDE,
the MCP Inspector) so it does not have to shell out and parse text:

```shell
task mcp                                  # stdio (how an MCP host launches it)
task mcp CLI_ARGS="--transport streamable-http"
uv run mcp dev tools/mcp_server.py        # MCP Inspector
```

| Tool | What it answers |
| --- | --- |
| `template_status` | this checkout's state: question count, latest tag, commits behind it, whether the tree is dirty |
| `list_questions` | the questionnaire in ask order, with defaults, help and choices |
| `inspect_project` | what a target already has, which mode fits it, and which files would be overwritten |
| `render_project` | render a set of answers and report the resulting file list |
| `list_batch_requests` | the requests in a batch file |
| `run_batch` | run a batch and return the verdict |

Read `template_status` first: `latest_tag` is the fork's own newest release —
what a plain `copier copy` expands since the 6.0.0 detach — and
`commits_behind_latest_tag` says how far the working tree has moved past it.
That counter used to be a trap: before the detach the newest tag was an
inherited pre-fork one pointing at a long-abandoned ancestor.

Two implementation notes worth knowing before editing that file:

- A stdio MCP server's stdout **is** the protocol channel, and copier prints
  its progress to stdout. Every render inside the server runs with fd 1
  redirected to stderr (`batch.report_stream_only()`), and
  `tests/test_mcp_server.py` asserts that with `capfd` — a stray `print`
  elsewhere in a tool would corrupt the session rather than fail loudly.
- The tool docstrings are the tool descriptions the model reads to decide
  when to call them, so they state the cost (rendering, installing, network)
  and the return shape. `tests/test_mcp_server.py` fails if a tool ships
  without one.

Binding the HTTP transport to a non-local address requires
`MCP_ALLOWED_HOSTS` (comma-separated), the same rule the generated MCP
scaffold enforces: the SDK arms its DNS-rebinding protection only while the
server binds to localhost, so a publicly bound server would otherwise accept
any `Host` header.

## Related

- [Run a Batch of Generation Requests](batch.md) — the request format.
- [Inspect a Target Before Applying the Template](detect.md) — the mode and
  collision report in detail.
