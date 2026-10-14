# The answers file (`.copier-answers.yml`)

Every project generated from this template records its answers in
`.copier-answers.yml` at the project root. Editing that file is the fastest
way to change a project's configuration — but <lt-m v="*"/>when<lt-m v="*"/> and <lt-m v="*"/>how<lt-m v="*"/> the edit takes
effect depends on which copier command you run, and the difference is not
obvious. This page states it, with the mechanism behind it.

## What is in the file

```yaml
# Changes here will be overwritten by Copier
_commit: 6.0.0-144-g3abc1234     # the template revision this project was generated from
_src_path: https://github.com/politeuma/architekton-py.git
package_name: my_project
project_type: cli
dependencies:                    # structured answer: edit to change [project] dependencies
- structlog
- httpx>=0.27
src_dirs:                        # structured answer: edit to change the src/ sub-directories
- data
- features
use_recommended_toolchain: true
# ... every other answer
```

Two kinds of keys:

- <lt-m v="**"/>`_commit` / `_src_path`<lt-m v="**"/> — copier's own bookkeeping. `copier update`
  reads them to know which template revision to diff against. Do not edit
  them by hand: a revision that does not exist makes `update` fail.
- <lt-m v="**"/>Everything else<lt-m v="**"/> — your answers, one key per question. Most are gate
  booleans (`use_recommended_*`) or choices; `dependencies` and `src_dirs`
  are the <lt-m v="["/>structured answers<lt-m v="](#structured-answers)"/> described below.

Copier <lt-m v="**"/>rewrites this whole file<lt-m v="**"/> on every `copy` / `recopy` / `update`, so
it is a record of what was rendered, not a file you own. Edit it, then run a
copier command — do not expect a project to notice the edit on its own.

## Which command picks up an edit

This is the part worth getting right. Both commands below are run **inside
the generated project**.

| Command | Picks up an answers-file edit? | Preserves your edits to <lt-m v="*"/>other<lt-m v="*"/> files? |
| --- | --- | --- |
| `copier update` | <lt-m v="**"/>No.<lt-m v="**"/> | <lt-m v="**"/>Yes.<lt-m v="**"/> |
| `copier recopy --overwrite` | <lt-m v="**"/>Yes.<lt-m v="**"/> | <lt-m v="**"/>No.<lt-m v="**"/> |

### `copier update` — brings template changes, keeps your work

```
uvx copier update --trust
```

`update` renders the template <lt-m v="**"/>twice<lt-m v="**"/> — once at the revision the project was
generated from, once at the target revision — and applies the <lt-m v="*"/>difference<lt-m v="*"/>
between the two trees to your project. Both renders use the answers in this
file, so an edit you made is present on <lt-m v="*"/>both<lt-m v="*"/> sides and cancels out of the
diff. The result: your project receives the template's changes, and your own
edits (to the answers file or to any generated file) are left alone.

That is exactly the behaviour you want most of the time, and it is why
editing `.copier-answers.yml` and running `update` appears to "do nothing".

### `copier recopy --overwrite` — re-renders from the current answers

```
uvx copier recopy --trust --overwrite
```

`recopy` throws away the project's evolution and renders it again from the
answers file. An edit to any answer — including `dependencies` and
`src_dirs` — takes effect. `--overwrite` is what makes it non-interactive;
without it copier stops at every file that differs and asks.

<!--lt:adm 4 !!! warning "`recopy %2D%2Doverwrite` replaces generated files"-->
Because it re-renders the whole project, it <lt-m v="**"/>overwrites<lt-m v="**"/> any file the
template owns — including edits you made to them. Commit first, run
`recopy`, then review `git diff`: anything of your own that it clobbered
is recoverable from the commit. `update` is the safer command when what
you want is the template's changes rather than a different configuration.

<!--lt:adm-end 4-->
## Structured answers

Two answers are <lt-m v="*"/>lists<lt-m v="*"/> rather than single values, so the choices that used to
be spread through the template's Jinja branches are visible and editable in
one place.

### `dependencies`

The runtime dependencies rendered into `[project] dependencies`.

The default is <lt-m v="**"/>derived<lt-m v="**"/> from your other answers: the project type, the
logging library you chose, and whichever of `web_api` / `mcp_effective` /
`scraping_*` / `bot_*` / `cloud_provider` / `include_sentry` / the
data-science stack apply. You do not have to work that derivation out — the
list you accept in the questionnaire <lt-m v="*"/>is<lt-m v="*"/> the derived set, and it is recorded
in the answers file.

Edit it to add your own entries (PEP 508 strings) or to remove a derived one
you do not want:

```yaml
dependencies:
- structlog
- httpx>=0.27,<1
- my-internal-lib
```

An empty list is allowed and renders `dependencies = []`. Entries are written
verbatim, so a bare `pandas` (no version bound) is fine.

### `src_dirs`

The sub-directories to create under `src/`, each with a `.gitkeep` so git
tracks it.

The default is derived: the data-science layout contributes
`data` / `features` / `models` / `visualization`, and the Kaggle workspace
contributes `input` / `logs` / `output` / `scripts`. `src/` itself is created
only when this list is non-empty, so `src_dirs: []` ships no `src/` tree at
all.

Add a directory of your own the same way:

```yaml
src_dirs:
- data
- features
- experiments
```

Directories that carry real content — Kaggle's `configs/`, `notebook/` and
`utils/`, and the package tree under the src layout — are <lt-m v="**"/>not<lt-m v="**"/> part of this
list: they are not empty sentinels, and a list cannot express "this directory
with these files inside". They keep their own gates in the template.

## Adopting this in an existing project

A project generated before `dependencies` / `src_dirs` existed has neither
key. Adding them by hand works: copy the shape above, list what you want, and
run `copier recopy --overwrite` (committing first). Copier reads a question
answer from this file even when the question is new, so no migration entry is
needed — a <lt-m v="*"/>new<lt-m v="*"/> question defaults rather than breaking the replay (see
<lt-m v="["/>Update to the latest template structure<lt-m v="](../how-to/update-template.md)"/> for
the update path itself).

## See also

- <lt-m v="["/>Non-interactive generation<lt-m v="](non-interactive.md)"/> — `--data-file`, and the
  troubleshooting list for generation-time failures.
- <lt-m v="["/>Update to the latest template structure<lt-m v="](../how-to/update-template.md)"/> —
  the day-to-day `copier update` workflow.
