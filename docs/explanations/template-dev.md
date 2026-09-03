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
generated project's `end-of-file-fixer` (pre-commit) then rewrites it on
first commit, which fails the generated project's CI and produces a dirty
tree.

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
