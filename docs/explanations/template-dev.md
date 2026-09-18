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
task-tags), `pyproject-ctf-extra.toml.jinja`, `pyproject-ctf-lint.toml.jinja`,
`pyproject-deps.toml.jinja` (the runtime `dependencies` one-liner),
`pyproject-deptry.toml.jinja` (the `[tool.deptry]` table with the
`per_rule_ignores` assembly, included from the test-coverage partial).
Out of scope: inline single-line conditionals with no edit-hotspot of their
own (README badges and the like) — extracting those would scatter one-line
logic across files with no hunk-boundary benefit.

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

To see and plan the order instead of only checking it after the fact, run
`task question-graph` (`tools/question_graph.py`): it prints the whole
dependency graph in definition order, grouped by fragment, with what each
question/internal reads and feeds, recomputes the forward-reference rule
(violations name both positions), and — with
`--where NAME --refs A,B,C` — answers "where may this new internal live":
the legal position window after the last definition it reads, what
currently occupies that spot, and which fragment the insertion lands in.

## Ask time reads the prefix of the chain; render time reads it all

The questionnaire keeps two vocabularies apart, and every condition below
lives on one side of the line:

- **Question `when:` conditions run at ask time.** Copier resolves a
  question's `when` / `default` / `choices` when it is reached in ask order,
  so a question sees exactly the prefix of the include chain built so far:
  raw answers *and* any internal already defined earlier
  (`has_data_science` in questions/data_science.yml, `has_web_api` in
  questions/web_api.yml, `oj_bare` / `online_judge` in
  questions/_common_b.yml, `include_web_api` in questions/_combo.yml, ...).
  A reference to anything later is a forward reference — Undefined (falsy)
  — and the question silently never asks. The rule is include order, not
  vocabulary, and it is mechanically enforced by
  `test_question_references_are_forward_only` in
  `tests/test_copier_structure.py`.
- **Everything render-side runs at render time and reads the effective
  internal.** Template bodies, file-name conditions (`{% if ... %}` in
  `template/` paths), `_tasks.jinja` and copier.yml's `_tasks` blocks see
  every answer, and they should read the `*_effective` family (plus the
  effective `web_api` / `data_science`, `pkg_dir`, `import_pkg`, ...) from
  `questions/_internal.yml`, so "the base *or* the combo opt-in" is
  resolved in exactly one place and render conditions cannot drift from the
  layer rules they encode.

The `include_*.when` gates and the `mcp_effective` / `bot_effective` base
guards are therefore the same predicate written in the two vocabularies —
the ask-time half in raw answers, the render-time half in internals; when
you change one, mirror the other. Two pinned consequences:

- `include_mcp.when` spells out
  `(project_type == 'cli' or project_type == 'web_api' or include_web_api)`
  instead of the `web_api` alias. The alias lives in
  `questions/_internal.yml`, which the include chain puts *after*
  `questions/_common_b.yml`, so referencing it from the question would be a
  forward reference (Undefined — the question would silently never ask).
  `has_web_api` *would* resolve — it is defined earlier, in
  `questions/_combo.yml`, so the include-order rule permits it — but raw
  answers suffice at ask time, so the gate spells its base out in raw
  form. This is the documented exception pattern to "one predicate, one
  definition": an ask-time gate that cannot reach its render-time twin is
  hand-synced with it (the comment on the question says so).
- Gate answers with no effective of their own (`use_recommended_agent`,
  `include_mcp`) are leaves: nothing derives them, so render conditions use
  them raw and that is correct. `include_sentry` is a leaf too, but its
  `when` carries its own base guard (hand-synced with the pkg-tree parent
  gate, the same exception pattern as `include_mcp`): the raw answer is
  only ever true where `<pkg>/__main__.py` — its only init site — renders,
  so the raw uses in the `.env.example` / README conditions stay correct
  without needing an internal.

The render-side agreement between a file-name gate and the README section
documenting the same file is enforced by
`tests/test_bot_layer.py::test_env_example_gate_and_readme_section_agree`
(the bot layer regressed exactly this way: `.env.example` shipped the bot
tokens while the README's "Environment variables" section stayed hidden);
the include-order half is `test_question_references_are_forward_only`
in `tests/test_copier_structure.py`.

## An answer render time discards is never silent

A question is asked only where its answer can matter. If a render-time
derivation would throw an answer away, either move the discard to ask time
— add the case to the question's `when` so it is not asked (preferred) —
or warn on stderr at render time (copier.yml's `_tasks` echo pattern;
validators can neither warn nor rewrite, and there is no pre-copy task
stage). The three `_tasks` warnings are the inventory: the micropython
sphinx → zensical override, the memorious → AGPL license override, and the
GitLab discard of `security_policy` / `scorecard` (the files they ask for
are GitHub-only machinery). The two non-asks: `layout` is not asked for
`script` (`use_src_layout` would drop a src/ tree without a package) and
`include_sentry` is not asked where no pkg tree can render `__main__.py`.

## A file-name branch belongs to its parent directory's condition

A branch is owned by the parent directory's name condition, and a child
must not restate its parent's predicate — a duplicated condition is two
definitions that can drift. When a path has to embed a condition of its
own, prefer a derived internal flag
(`{% if security_policy_effective %}SECURITY.md{% endif %}`) over
re-spelling the raw derivation: the internal is the one definition the
render side cannot drift from.

## Keep the predicate inventory mechanical: `task predicates`

The condition surface is large — question `when:`s, the `when: false`
internals, `{% if %}` gates in template file names and bodies, `_tasks`
guards — and §18's unification (the `oj_bare` / `no_pkg` inventory) was done
by hand against a snapshot that could rot. `tools/predicates.py` keeps the
inventory alive: it collects every boolean condition site, evaluates each
against all 234 witness leaves with copier's own machinery, and reports the
classification tree (every `invariants.yml` row with its leaf count),
per-internal reference and fire counts, the equivalence classes over the
leaf space, mechanically-detected unification candidates (a site whose leaf
vector equals a named internal it does not reference), and shortcut
suggestions. `--json` is the machine-readable form; run it after adding a
gate, a layer, or any new `{% if %}` — and read its findings as candidates,
not verdicts (mechanical equality is not intent).

The naming rule it suggests with numbers:

- **3 or more sites sharing one leaf-vector class that has no name** — name
  the shortcut (a new `when: false` internal) and reference it everywhere;
  that is the threshold where look-alike conditions start drifting apart.
- **A named internal that never splits the 234-leaf space** (fires on all
  or none) — a shortcut that cannot distinguish leaves is dead weight;
  consider flattening it or saying why the leaf space never exercises it.

The fast-tier guard `tests/test_predicate_classifier.py` holds the
space-wide version of the same rule: no template condition may duplicate a
named internal unconditionally (proven in Z3 over the whole questionnaire
space, not just the 234 leaves) without referencing it — unless the pair is
declared in its `DECLARED_EQUIVALENCES` registry with a reason, as the
`has_*` / `web_api` / `data_science` alias family from §18 is.

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

## Jinja tags inside YAML block scalars must stay indented

`_tasks` commands that embed conditional jinja (`{% if docs %}...{% endif %}`)
must keep the tags at the SAME indentation as the block-scalar content
(col 0 breaks out of the `|` scalar and `copier.yml` fails to parse with
`found character '%'`). The rendered tag line becomes an empty line inside
the shell script — harmless. Verified by rendering with
`load_template_config` (machine gate) plus an actual `copier copy`.

The same lesson applies to answer-driven file protection: conditional
presence is expressed on the FILE NAME (`{% if x %}name{% endif %}.jinja`),
never by jinja in `_skip_if_exists` (config values are not rendered).

## Documented generation commands must run without `--vcs-ref`

Every `copier copy` command we publish against the template URL runs with no
`--vcs-ref`. Copier then checks out the repository's **newest git tag**, and
since the 6.0.0 fork detach that tag is this fork's own release, so the plain
command asks this questionnaire and renders these files. A revision is pinned
only when the surrounding text says so — `--vcs-ref=6.0.0` to reproduce an
exact older release — and `--vcs-ref=main` is never presented as required.

The rule used to be the opposite, and the reason is worth keeping. Before the
detach the newest tag (`5.4.0`) was inherited from the upstream
DiamondLightSource template, so a flagless copy silently asked the *old*
questionnaire and rendered the *old* files. That produced two real bug reports
("docs_type rejects zensical", "asks component_owner"; see BUG.md — both were
misdiagnosed twice before the tag mechanism was confirmed via
`git show 5.4.0:copier.yml`), and the published commands pinned `--vcs-ref` to
escape the trap. The detach removed the need.

The one ref that stays pinned is `--vcs-ref=HEAD` (equivalently
`tools/adopt.py --ref HEAD`), and it belongs only in this repository's own
local-iteration docs: it expands the working tree, uncommitted changes
included, so it describes how to test a template edit — never how a user
generates a project. Enforced by `tests/test_generation_docs.py`, which
renders a defaults copy with no ref and fails if the newest tag ever stops
carrying this questionnaire.

The same investigation pattern is worth reusing: when generation behaves
differently between two invocations that look identical, print
`Worker(...).template.config_data` from the Python API — it exposes which
template source (working tree vs tag clone) and which settings keys copier
actually resolved, and turned a day of "flaky copier" theories into a
one-line root cause.

## GitLab scope

`git_platform` offers `github.com` (default) and `gitlab.com`. The platform
distinction is enforced in two places: the `is_github` / `is_gitlab`
internals (questions/_internal.yml) gate whole files by filename, and
the `repo_url` / `docs_url` internals in `questions/_internal.yml` decide URL
bytes. What that means for a `gitlab.com` render:

Shipped, following the platform:

- GitLab URLs from the `repo_url` / `docs_url` internals in every consumer:
  `https://gitlab.com/<gitlab_group>/<repo>` and the GitLab Pages convention
  `https://<gitlab_group | lower>.gitlab.io/<repo>`. That reaches
  `pyproject.toml`'s `[project.urls]` (labelled `urls.Homepage` on GitLab,
  `urls.GitHub` on GitHub), `zensical.toml` `site_url` / `repo_url`,
  `CITATION.cff` `repository-code`, `REUSE.toml`,
  `docs/tutorials/installation.md`, the README clone/source links, the ros2
  `package.xml`, and the LICENSE notice text.
- the hardened `.gitlab-ci.yml` instead of the GitHub Actions workflow set
  (`.github/` is filename-gated to github.com), and — because
  `security_policy_effective` / `scorecard_effective` gate on the platform —
  no `SECURITY.md` / Scorecard workflow (see
  `docs/explanations/security.md`).

Remaining GitHub-specific on a gitlab.com render (factual state, not a
roadmap — full parity would be a project of its own):

- no GitHub Actions workflows are rendered, so the README's CI badge
  (`{{repo_url}}/actions/...`) and codecov badge point at routes a GitLab
  repository does not serve;
- the docs *deployment* story: `conf.py`'s github switcher and pages URL,
  `make_switcher.py`, the gh-pages publish job — no GitLab Pages CI job is
  generated, even though `docs_url` itself follows the GitLab Pages
  convention;
- `ghcr.io` container paths (the devcontainer base image and the
  container-publish workflows);
- the OpenSSF Scorecard badge (already gated off via `scorecard_effective`);
- README links that append GitHub routes to `repo_url` — `/issues` and
  `/releases` (GitLab's routes are `/-/issues`, `/-/releases`) — and the
  contributing section's link to `.github/CONTRIBUTING.md`, which a GitLab
  render does not ship.

Enforced by `test_template_gitlab_urls` in `tests/test_example_library_cli.py`
(a gitlab.com render's URLs carry the group, and those fields contain no
github.com) and `test_template_github_urls_unchanged` in the same file (the
github.com render still produces today's exact URL bytes).

## Adding a platform, layer, or gate: the runbook

Everything above is one checklist in context: the five design questions,
the touchpoint table (question, internals, scaffold, invariants row,
witness regeneration, ledger re-record, docs sync, markers), the tools it
leans on (`task predicates`, `task question-graph`, `task witness`), and
the rule the machinery cannot check for you (mechanical equality is not
intent). See [Extending the Questionnaire](extending.md).

## Keep the `tools/` dependency layers declared

`tools/` is nineteen modules, and their dependency direction was implicit:
every cross-module import reads `from tools import x`, but nothing said which
modules sit where, so "may `adopt.py` use `invariants`?" was answerable only
by reading all of them. The layering is now a declared contract — the repo's
registry idiom again (cf. `DEFAULT_REPEATS_ALLOWED`,
`invariants.yml`'s `excluded`): declared, not discovered. The layers, bottom
up:

| Layer | Modules | What it is |
| --- | --- | --- |
| `standalone` | `check_upstream`, `check_upstream_fork`, `check_questionnaire_diff`, `generate_license_template` | maintenance/CI scripts that import nothing from `tools/` (a pristine checkout or a released tarball is their world) |
| `foundations` | `answers`, `questionnaire`, `when_model`, `render_inputs`, `support_ledger` | the questionnaire model and shared primitives: data and meaning, no behavior on real trees |
| `machinery` | `file_merge`, `pyproject_merge`, `invariants`, `z3_witnesses` | pure transformations and verifiers over template/adoption artifacts |
| `drivers` | `detect`, `batch`, `adopt`, `git`, `predicates`, `question_graph`, `render_delta`, `answers_for`, `update_rehearsal` | act on real trees with copier/subprocess; consume the machinery |
| `frontends` | `cli`, `gen_docs`, `mcp_server` | the entry points a human or an agent calls; consume the drivers |

Rules:

- A module may import modules of its own layer or any layer BELOW it. An
  import that points up fails the test, unless the pair is declared in the
  test's `ALLOWED_UPWARD_IMPORTS` with a one-line reason — a genuine tangle
  that is not worth refactoring away is stated, not hidden. The registry is
  stale-proofed in both directions: an undeclared upward import fails, and so
  does a declared exception whose edge has vanished or stopped pointing up.
  (There are no exceptions today: no import points up.)
- New module under `tools/`? Pick a layer and add it to `LAYERS` in the test —
  the test tells you if you guessed wrong: an unplaced module fails the
  membership check (so no module can sneak in undeclared), and a wrong guess
  fails the direction check.

Enforced structurally (an AST scan of the import statements, no runtime
import) by `tests/test_tool_layers.py`; the same table lives in that test's
docstring, and the two are meant to be edited together.

## Prove what a change can affect: the render twin

`task verify-delta` (`tools/render_delta.py`) answers "which leaves did this
change touch?" mechanically. Layer A tabulates each leaf's render context (its
answers and the internals derived from them) and
every watched template byte, and diffs the two states: a leaf is a candidate
only when its context moved or changed bytes are reachable from its rendered
file set (include closure included). Layer B re-renders candidates from a
baseline checkout and the working tree and compares per-file manifests
(`.copier-answers.yml`'s per-render stamps normalize away). The verdict is
either "PROVEN render-identical" for the whole space or the exact leaves and
files that changed -- which is what the refactor commits in this history
replaced hand-picked combination diffs with. A leaf only one side declares
(the witness list is itself an input, so a leaf-space change moves it) is
named as added or removed rather than diffed: there is no counterpart render
to compare. `--audit N` re-renders N
unaffected leaves as a continuous soundness probe of Layer A; a mismatch
means the semantic diff missed a flow, and that is a bug in this tool, not
in your change.

## Accumulate ethics/regional/operational rules as sections first

Field rules (a retired public NTP, a telecom secrecy duty, a regional
backbone's quiet hours) arrive one at a time and must not each move the
questionnaire, the leaf space, or the witness matrix. Write each as a
section under `_shared/ethics/` (`baseline/`, `sector/`, `region/`,
`domain/`; `lang/` is reserved for the translation dictionaries), register
it in `_shared/ethics/REGISTRY.yml`, and leave it `draft` until a bundle
forms:

- The registry row is the single source: id, file, `YYYY-MM-DD.rev`
  version, `effective` / `review_by` dates, primary-source URLs (no
  statute pasted verbatim — one-line summary plus link), scope
  (`jurisdiction` / `sector` / `category`), scale (`domestic` /
  `regional` / `global`: who suffers vs who causes, in one line),
  audience (minimal distribution list, e.g. `iot` / `cli` — a section
  ships only where its triggers can fire), enforcement (`L0` doc /
  `L1` presence assert / `L2` real gate), and lifecycle status
  (`draft` → `active` → `kind`, with `superseded_by` naming the
  successor). The file opens with the matching
  `{# ethics: id=.. version=.. status=.. #}` header, states its scale
  line and audience up front (so humans and LLMs route it without
  reading the body), and repeats its `review_by` in the body.
- Scale is the routing axis: `domestic` (rule and sufferer inside one
  country), `regional` (one region's infrastructure), `global` (one
  country suffers, the world causes — e.g. the retired Fukuoka NTP
  drowned from 239 countries). Audience is the minimization axis:
  the smallest project kinds that can trip the rule (IoT firmware and
  CLI pollers for NTP hardcoding — not every project).
- A draft section takes no copier context (`{{ }}`) and nothing includes
  it — it is documentation only, so the leaf space does not move.
- Promote `draft` → `active` (appendix into an existing conditional doc)
  or `kind` (its own distribution condition) only when a bundle forms:
  three sections sharing one distribution condition, or one section
  needing a distinct code/test gate. A `kind` promotion names the
  audience in its distribution condition (so the section keeps shipping
  only where it applies). The promotion PR wires the questionnaire,
  the witness leaves, `invariants.yml`, and the registry row together.
  The first promotion (2026-09) is the baseline trio
  `pqc-fips` / `license-drift` / `copyright-ai` as the AGENTS.md ethics
  appendix: no new question — the appendix gates on the existing
  `project_type` / `web_api` / `data_science_layout` answers, and the
  `ethics-appendix` content predicate in `tests/test_render_invariants.py`
  holds the rendered guide to exactly those conditions. A section whose
  audience outruns its channel stays draft — `pki-chain` needs a channel
  that reaches micropython, which AGENTS.md does not render for.

Enforced by `tests/test_ethics_registry.py` (row shape incl. scale /
audience, header agreement, body scale line, draft isolation, the
parents a distributed row names actually including its file, and the
retired-identifier denylist the first section exists for).
