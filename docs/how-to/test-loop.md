# How to check a change without running the full suite

Four speeds are available, from "did this one combination render" to "is
everything still green". Pick by what you changed; the last row is not a speed
but the cost ledger's own guard, and it stays outside the loop.

| Tier | Command | Tests | Wall time |
| --- | --- | --- | --- |
| Edit loop | `task test-fast` | 732 | ~47s † |
| Slow | `task test-slow` | 5 | ~72s |
| Pre-push / nightly | `task test-heavy` | 43 | ~29s |
| Everything | `task test` | 787 | ~139s |
| Cost ledger guard | `task test-meta` | 7 | ~11s † |

`task test-meta` is the odd row: it is not a speed to pick by what you changed,
it is the cost ledger's own guard (`tests/test_marker_drift.py`) split out of
the edit loop, and CI runs it as its own job on every push and PR.

Those times are the lightest of the runs measured on 2026-09-14 with
`time uv run --no-sync pytest -q -m "<the task's own selection>"`. The two rows
marked † were measured for this version of the ledger with unrelated work
filling the machine's 32 logical CPUs (load average 64–117), so they are
observations of that contention rather than of a quiet box: the same tree with
the guard still in the edit-loop selection (then 738 tests) took 46s at load 85
in the same session, and the 30s budget remains the contract. A cold
`.cache/renders` (the first run after changing the template) turned `task test`
into 337s. That spread is why the budget is the contract and a time is only an
observation — `tests/matrix/tiers.json` holds each measurement with the
conditions it was taken under.

The tiers are a contract, not a habit: each one is a marker expression the
Taskfile passes to pytest, and a check that belongs to a tier only if its cost
does. [Verification](../explanations/verification.md) states the three layers
(L1 input space, L2 render invariants, L3 execution), the edit-loop budget
(**30s**) and where a new check belongs; this page is the practical side.

- `task test-fast` runs `-m "not heavy and not slow and not meta"`: everything
  that neither builds a virtualenv nor touches the network, minus the serial
  batch runner and minus the cost ledger's own guards (`tests/test_marker_drift.py`,
  see `task test-meta` below). That is the whole edit loop and what CI runs on
  every push and PR. It does **not** exclude `tests/test_example.py` — 112 of
  that file's 135 tests run; the 23 that build a venv are marked `heavy`.
  `tests/test_generated_typecheck.py` is excluded in practice, because all 6 of
  its tests are `heavy`.
- `task test-meta` runs `-m meta`: the guards in `tests/test_marker_drift.py`,
  which check that expensive work carries its markers, that every tier still
  collects what `tests/matrix/tiers.json` records, and that no recorded wall
  time is older than 30 days. They are not part of the edit loop because the
  membership check re-collects every tier in its own pytest session (six
  startups); `ci.yml` runs them as its own job. They are also part of
  `task test`, so the pre-release gate still runs them.
- `task test-slow` runs `-m slow`: the serial 205-leaf witness batch runner
  (`tests/test_witness_matrix.py::test_witness_batch_runner_executes_every_leaf`,
  the one test the edit loop cannot afford) and the four `copier update` cases.
  Neither builds a venv; both are far too slow for the edit loop.
- `task test-heavy` runs `-m heavy`: builds a venv (`uv sync`) in a rendered
  project, plus the generated project's own checks. Run it before pushing a
  template change that touches dependencies, task runners or CI; the nightly
  `ci.yml` run is what guarantees it.
- `task test` runs everything with coverage (see
  [Coverage](coverage.md)); it is the pre-release gate, not the edit loop.

## The cost ledger

`tests/matrix/tiers.json` records, per tier, the marker expression it selects
on, the node ids it collected, and the wall time a human measured for it. Two
kinds of tier are in it: `tiers` are the Taskfile tasks (their expressions are
read back from `Taskfile.yml`) and `witness` is the PR job of
`.github/workflows/witness.yml`, whose expression and 30-minute job timeout are
read back from the workflow. It is JSON, next to the other machine-checked
artifacts in `tests/matrix/` (`witnesses.jsonl`, `witnesses.json`), rather than
a table in this page: a test has to read it, and a table a test parses is a
machine format with worse tooling. The prose stays here; the numbers live
there.

`tests/test_marker_drift.py` re-collects each tier (collection only, no
test runs) and fails when a tier no longer collects what the ledger says, so a
test cannot change tiers silently; the same file fails when a test builds a
venv or touches the network without `heavy` / `network`, which is what would
otherwise leak a 20-second case into the edit loop unnoticed. It also fails
when a row's `measured` date is more than 30 days old: a wall time is the one
column nothing recomputes, so the failure names the row's own `command` to
re-measure with rather than letting a stale number be quoted.

After a deliberate tier change, re-record the collected sets and then the
counts on this page:

```shell
UPDATE_TIERS=1 uv run --no-sync pytest -q tests/test_marker_drift.py
```

The command rewrites the sets but leaves `wall_seconds` / `measured` / `command`
alone, because a wall time is a measurement, not a projection: fill those in
from a `time` run of the row's own `command`, e.g.

```shell
time uv run --no-sync pytest -q -m "not heavy and not slow and not meta"
```

on an otherwise idle machine. Adding a whole tier is a matter of adding its
task (or witness job) and its name to the check's own lists; a row that has
never been timed keeps `wall_seconds: null` and fails until a human fills it
in. The counts in the table above are the ledger's (the check fails if the two
disagree); the times are the measurements recorded with them.

## What the tiers cost in CI

| Workflow | Event | Tier |
| --- | --- | --- |
| `ci.yml` (`_test.yml`) | push / PR | `task test-fast` — the edit loop |
| `ci.yml` (`_test.yml`) | push / PR | `task test-meta` — the ledger's own guard, its own job so the edit loop does not pay for six extra pytest startups |
| `ci.yml` (nightly) | schedule | `task test-heavy` |
| `witness.yml` (fast) | PR | `pytest -q tests/test_witness_matrix.py -m fast` — renders every leaf, no venv: 208 tests (205 renders plus three leaf-list checks), 39 s locally with the render cache emptied, against the job's 30-minute timeout |
| `witness.yml` (full) | schedule / manual | `pytest -q tests/test_witness_matrix.py -m full` — the 8-leaf venv sample plus the batch runner |

The witness tiers are the [W3 matrix](../explanations/verification.md): `fast`
renders all 205 leaves and checks the artifacts each one declares, `full` runs
`uv sync` on a bounded sample. `-m full` tests also carry `heavy`, so a local
`task test-heavy` includes the sample. A PR runner has no `.cache/renders`, so
the fast job always pays the cold render: the ledger's row for it records that
cold measurement next to the timeout it has to fit in, which is what makes
"there is headroom" a checked statement rather than an assumption.

## Ergonomic flags

`task test-fast` forwards extra arguments, which is how the loop stays short:

```shell
task test-fast CLI_ARGS="--lf"            # only what failed last time
task test-fast CLI_ARGS="-x"              # stop at the first failure
task test-fast CLI_ARGS="--durations=25"  # where the time goes
task test-fast CLI_ARGS="tests/test_example.py -k web_api"
```

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

- [Verification](../explanations/verification.md) — the layers, the tier
  budgets and how the suite is meant to grow.
- [Run a Batch of Generation Requests](batch.md) — the request format.
- [Inspect a Target Before Applying the Template](detect.md) — the mode and
  collision report in detail.
