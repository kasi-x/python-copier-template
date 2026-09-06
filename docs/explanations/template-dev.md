# Authoring Template Sources (.jinja)

Rules for editing this repository's *template sources* — the `template/`
tree, the `questions/` questionnaire fragments, and the root `_shared/` /
`_tasks.jinja` partials. These are the recurring failure modes we have hit;
each rule is backed by a real bug. Where a rule is enforced by a test, the
test name is linked so a future change can verify itself.

## End every rendered file with exactly one newline

Jinja tags at the end of a `.jinja` source silently add a trailing blank
line: a file ending in `{% include "..." %}` or a plain `{% endif %}` leaves
its own newline in the output, so the rendered file ends with `\n\n`. The
generated project's hygiene workflow then fails CI on the first push with
its end-of-file newline check.

Rules:

- A `.jinja` source that ends in a block tag must trim the tag's trailing
  newline: use `{%- endif %}` / `{%- endfor %}` / `{% include "..." %}` with
  no newline after the tag (the file may end right after `%}`), or add a
  `-` to the *opening* tag of a trailing conditional so the whole block
  consumes its own newline.
- A conditional block that can render empty (e.g. `{% if package_manager ==
  "poetry" %}...{% endif %}`) must not leave a blank line behind when its
  condition is false — trim the newline *before* the `{% if %}` (write the
  preceding tag as `{%- endif %}`) so the skipped block contributes nothing.

Enforced by
`test_generated_files_end_with_single_newline` in
`tests/test_generated_lint.py` (runs over every recommended render path).

## Share large conditional bodies via `_shared/` includes

When the same body must be generated at different paths per project type
(e.g. `logging_setup.py` lives in `<pkg>/` for library/cli/... and in the
top-level `app/` for web_api), keep the body once in a root `_shared/*.jinja`
partial and include it from thin per-location wrappers:

```jinja
{# template/<pkg>/logging_setup.py.jinja #}
{% include "_shared/logging_setup.py.jinja" %}
```

- The include path is repo-root-relative (copier's Jinja loader searchpath is
  the repository root), so `_shared/` needs no `template/` prefix.
- `_shared/` is never copied into a generated project (it is outside
  `template/`), and the wrapper picks the location.
- Any self-reference inside the shared body that differs per location
  (e.g. `from <pkg>.logging_setup import logger` vs
  `from app.logging_setup import logger`) is parameterised with an internal
  copier variable — `import_pkg` (`'app'` for web_api, else `<pkg>`) — never
  hard-coded per wrapper.
- Remember the newline rule above: the wrapper file must end *immediately
  after* the `{% include %}` tag, or the render gains a trailing blank line.
- When a direct template file is replaced by a shared partial, keep the render
  byte-identical: put the wrapper on a *single line* —
  `{# ... #}{% include "_shared/....jinja" %}` with no trailing newline. A
  two-line wrapper (comment line, then the include) emits the comment's
  newline as a leading blank line in the output. (`logging_setup.py`'s
  two-line wrappers predate this rule and carry that leading blank line as
The same pattern applies to single-location conditional blocks that are
edited often enough to cause hunk-boundary mistakes: the CTF `ctf` extra
(`_shared/pyproject-ctf-extra.toml.jinja`) and the `challenges/` ruff
ignores (`_shared/pyproject-ctf-lint.toml.jinja`) are included from
`template/pyproject.toml.jinja`. Verify with a baseline-vs-current render
Current inventory (all byte-identical verified over 9 render paths —
library / cli / web_api / data_science / atcoder / kaggle / micropython /
ros2 / cli+ctf):
`pyproject-basedpyright.toml.jinja`, `pyproject-ty-checkers.toml.jinja`
(pyrefly/ty), `pyproject-test-coverage.toml.jinja` (pytest/coverage/typos/
vulture/deptry), `pyproject-ruff-lint.toml.jinja` (select/extend-ignore/
task-tags), `pyproject-ctf-extra.toml.jinja`, `pyproject-ctf-lint.toml.jinja`.
Out of scope: inline single-line conditionals (README badges, dependency
one-liners, deptry `|token` fragments) — extracting those would scatter
one-line logic across files with no hunk-boundary benefit.

Enforced by `_template_files()` walking `_shared/` in
`tests/test_copier_structure.py` (variables inside shared partials must be
defined questionnaire keys).

## Keep the questionnaire in `questions/`, ordered by the include chain

`copier.yml` is the include chain only: it holds `project_type` inline, then
`!include questions/*.yml` fragments in ask order, then the underscore
settings. Rules:

- Each `!include` is its own YAML document (`---`-separated); two
  `!include` tags in one document collide as the same mapping key and the
  later silently wins.
- A question's `when` / `default` / `choices` may only reference variables
  defined *earlier* in ask order. Internal (`when: false`) derived variables
  that a question references (e.g. `micropython_pkg`, `online_judge`) must
  live in their genre fragment *before* that question — a back-reference
  renders as Undefined (falsy) and silently picks the wrong branch.
- The same ordering trap applies *inside* `questions/_internal.yml`: copier
  evaluates `when: false` defaults in definition order, so an internal
  variable must be defined *before* any internal variable that references it
  (e.g. `web_api` / `data_science` come first, ahead of `mcp_effective`,
  `prometheus_effective` / `rate_limit_effective` / `cors_effective`,
  `use_src_layout`, `pkg_dir`, ...). Referencing a later internal renders as
  Undefined (falsy) — the questionnaire structure test does *not* catch this
  (it skips `when: false` in the forward-only check), so verify with an
  actual render.
- Internal variables that only feed template rendering (the `*_effective`
  family, `pkg_dir`, `import_pkg`, ...) stay in `questions/_internal.yml`
  at the end of the chain.

Enforced by `test_question_references_are_forward_only` and
`test_fragments_are_complete_and_duplicate_free` in
`tests/test_copier_structure.py`.

## Adding a question or project type: keep the Z3 reachability green

Every asked question's `when` must be satisfiable for some combination of
earlier answers. A typo in a `project_type` comparison or a guard no genre
satisfies makes the question dead — it can never be asked. `test_every_question_when_is_z3_satisfiable`
models the when-expressions in Z3 and fails on unsatisfiable ones; run it
after touching any `when` / `choices` / genre list.

## Hardcoded pins need an upstream check

Renovate tracks PyPI ranges, Action digests and lockfiles — but not release
tags, CUDA indexes, distro codenames or image tags hardcoded in the
template. Every such pin must be covered by `tools/check_upstream.py`
(run weekly by `.github/workflows/check-upstream.yml`, which opens an issue
on drift):

- Add the pin to `extract_pins()` with its single source of truth, a
  resolver in `_resolve_one()`, and a drift rule in `_is_drift()`.
- Prefer machine-readable feeds (PyPI JSON, endoflife.date, index listings)
  over scraping; hardcode spec dates (e.g. REP-2000) only when the source is
  a versioned document.
- The check is report-only: it never edits files or opens PRs. CUDA-class
  bumps need a human (torch floor + index + Docker base move together).

copier itself is pinned `<10` in the root `pyproject.toml` (renovate's
`lockFileMaintenance` would otherwise pull a breaking major into `uv.lock`
unannounced). When raising the ceiling, re-verify the whole test suite —
especially `run_copy()`'s signature and `copier.errors`' exception classes —
first. The ceiling is tracked by the weekly drift check as the
"copier ceiling (root pyproject.toml)" pin.

## Freshness policy: combinations that cannot stay current

Some combinations cannot track upstream HEAD, by design. The weekly check
reports drift; the policy below decides whether drift is a bug or accepted:

- **Track HEAD**: core floors (structlog/ruff/pytest), web_api FastAPI
  ecosystem, MCP SDK (`mcp[cli]>=2.0,<3` — the `<3` cap is intentional
  after the v1→v2 breakage, not staleness). Drift here is a bug: bump the
  floor after verifying the render matrix stays green.
- **Track with lag**: torch/CUDA (cu126 pinned while cu128 exists — bump
  only when torch resolves on the new index *and* the Dockerfile base
  moves together), ROS 2 distros (REP-2000 EOL-gated; rolling is never
  offered), Python floor (endoflife.date-gated).
- **Pin by rule, not by latest**: MicroPython firmware/stubs (single source
  of truth `micropython_version`; community stubs lag official releases),
  Postgres/Ubuntu images (compose+CI must agree; bump together).
- **PyPI floor categories** (`PyPI floor [<category>]` pins) mirror the
  questionnaire axes (core / web_api / kaggle-DS / ctf / mcp) so a drift
  issue names the combination it breaks. A `REMOVED` verdict (floor matches
  no PyPI release) is always a bug — `uv sync` breaks for that combination.
  A `floor X / latest Y` gap is a judgment call per the policy above.

## Documented generation commands must pin `--vcs-ref`

Every `copier copy` command we publish against the template URL passes
`--vcs-ref=main` (or a deliberate release ref). Reason: copier checks out the
**latest git tag** when `--vcs-ref` is absent, and this fork still carries
inherited upstream tags — the newest of them (`5.4.0`) points at the old
pre-fork DiamondLightSource template. Generating without the flag therefore
silently asks the old questionnaire and renders the old files, which produced
two real bug reports ("docs_type rejects zensical", "asks component_owner";
see BUG.md — both were misdiagnosed twice before the tag mechanism was
confirmed via `git show 5.4.0:copier.yml`).

This stays a hard rule until the v1.0 fork detach re-tags the repository
(TODO item 11). Enforced by `tests/test_generation_docs.py`, which scans the
README and docs/tutorials fenced blocks for URL-based `copier copy` commands
without a `--vcs-ref=` flag.

The same investigation pattern is worth reusing: when generation behaves
differently between two invocations that look identical, print
`Worker(...).template.config_data` from the Python API — it exposes which
template source (working tree vs tag clone) and which settings keys copier
actually resolved, and turned a day of "flaky copier" theories into a
one-line root cause.
