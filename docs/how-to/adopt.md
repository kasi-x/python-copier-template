# How to adopt the template into an existing project

`tools/adopt.py` is the transactional driver: it plans the adoption, applies
it, verifies what happened, and rolls back if anything it promised not to
touch changed.

```shell
task adopt DIR=/path/to/project CLI_ARGS="--dry-run"   # plan only
task adopt DIR=/path/to/project                        # plan, then apply
```

## Why a driver and not just `copier copy`

Three failure modes, all measured against copier 9.18.1:

| Failure | What copier does on its own |
| --- | --- |
| A file the template also ships already exists (`.github/workflows/ci.yml`, `renovate.json`, ...) | Stops with `Interactive session required: Consider using --overwrite`, exit 1, **after** writing every file it had already rendered — the project is neither before nor after |
| `--overwrite` to get past that | Replaces those files, including collisions nobody listed |
| `copier copy <url>` without `--vcs-ref` | Expands the latest **tag**, which on a fork can be an inherited one pointing at a different template |

The driver closes all three:

1. **No collisions**: the collisions come from `tools/detect.py` and are passed
   to copier as `skip_if_exists`, so your files are left alone and everything
   else is still added. Nothing is passed as `--overwrite`.
2. **Rollback**: the run renders with `overwrite=False` and then verifies that
   no existing file changed (by content) and none disappeared — comparing
   file *and* directory sets. If anything did, the originals are restored,
   everything the run created is deleted (empty directories included), and the
   command exits 1 reporting what happened. A failed adoption leaves the
   project exactly as it was.
3. **The right revision**: `ref` is the latest tag *only if that tag declares
   the same questions as this checkout*; otherwise the default branch is used
   and the report says why ("latest tag 5.4.0 does not carry this
   questionnaire (missing 93 question(s), e.g. ...); using main"). Pass
   `--ref HEAD` to expand the working tree instead, uncommitted changes
   included — that is the local-iteration case.

## What it merges into your pyproject.toml

After a successful render, the dependencies the template *would* have
generated are merged into your `pyproject.toml` (rendered into a temporary
directory for exactly this, since your file is the protected one). The rules
are deliberately narrow:

| Rule | Why |
| --- | --- |
| Only add names you do not already declare | An existing requirement is yours; a merge that rewrites pins is a merge that starts fights |
| A name you declare differently is **kept and reported** (`deps.differing`) | "You have `structlog>=9`, the template pins `structlog`" is information, not a conflict to resolve |
| Never reorder or reformat anything else | The edit goes through tomlkit, which round-trips your comments and layout |
| Idempotent | Running the adoption (or the merge) twice adds nothing the second time |
| Extras are reported, not invented | `[project.optional-dependencies] experiment` is opt-in per project — the note lists it |
| No `[project]` and no `[tool.poetry]` table | Nothing to merge into: the list is printed to wire by hand |
| Poetry layouts get the requirements translated (`httpx>=0.27` → `httpx = ">=0.27"`) | Extras and markers need table syntax, so those are reported instead of guessed |

`--no-deps` skips the merge entirely (the file is then left byte-identical).

What it still does not do: reconcile a *conflicting* constraint, rewrite
`[tool.*]` sections, or merge task-runner files. `notes/SPEC-adoption.md`
section 12 keeps section-level TOML reconciliation a non-goal — the merge
above is the additive half that is safe to automate.

## Example

```
$ task adopt DIR=/path/to/project CLI_ARGS="--dry-run --ref HEAD"
target: /path/to/project
mode:   adopt
ref:    HEAD  (requested explicitly)
skip:   .github/workflows/ci.yml renovate.json

dry run -- nothing written

  dry run: would render 156 new file(s)
  created [dependency-groups] to hold the dev dependencies

$ task adopt DIR=/path/to/project CLI_ARGS="--ref HEAD"
adopted: 46 file(s) added, 4 existing file(s) untouched

  created [dependency-groups] to hold the dev dependencies
  differing deps: structlog: kept 'structlog>=9', template wanted 'structlog'

next
  git diff     # review; the adoption only added files
  git status   # untracked additions: CI, hygiene, AGENTS.md, ...
```

A refused or failed run:

```
$ task adopt DIR=/path/to/project            # another template owns it
another copier template owns this project (https://github.com/other/template.git);
pass takeover=True to replace its record                       # exit 3

$ ... --skip nothing-actually-collides        # an uncovered collision
FAILED: InteractiveSessionError: Interactive session required: Consider using `--overwrite`
  removed what the run created: 40 file(s)
                                                               # exit 1, project unchanged
```

## Options

| Option | Meaning |
| --- | --- |
| `--dry-run` | Plan only; write nothing. |
| `--ref REF` | Revision to expand (default: judged from the tags). `HEAD` = this working tree. |
| `--answers FILE` | Copier answers file — `tools/detect.py --answers` writes one for the target. |
| `--data k=v` | Extra answer, repeatable; effective YAML value (`k=true`, `k=[a, b]`). |
| `--skip PATH` | Path never to write over, repeatable. Default: the detected collisions. |
| `--takeover` | Adopt over a foreign template's answers file (otherwise refused). |
| `--no-deps` | Do not merge the template's dependencies into `pyproject.toml`. |
| `--json` | Machine-readable result, including `created`, `unchanged`, `restored`, `removed`. |

Exit codes: `0` adopted (or a clean dry run), `1` failed and rolled back, `2`
invalid request (already generated by this template, not a directory),
`3` refused (foreign template without `--takeover`).

The same operation is available over MCP as `adopt_project`
([Check a Change Without the Full Suite](test-loop.md)), where `dry_run`
defaults to `true` and a failed adoption raises rather than returning a
half-valid result.

## Related

- [Inspect a Target Before Applying the Template](detect.md) — the report the
  plan is built from.
- [Adopt the template into an existing repo](../tutorials/adopt-existing.md) —
  the user-facing walkthrough, including what copier does with each of your
  files.
