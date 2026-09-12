# Adopt the template into an existing repo

You can adopt this template into an existing repo by running `copier copy` in much the same way as in a new project.

!!! warning
    This repository has not reached its v1.0 detach yet, so the only current
    release tags are inherited from the upstream project and point at the old,
    pre-fork template. **Until v1.0, every URL-based `copier copy` here must
    pass `--vcs-ref=main`** (as the commands below for the general case do).
    The `1.0.0`-based flow below applies once the fork has been detached and
    re-tagged (see the repository's TODO, item 11).

This will:

- Ask some questions about the existing project
- Expand the template with the answers given, protecting your own files
- Add the infrastructure you do not have yet (CI, hygiene, quality tooling)
- Record the answers in the project so they can be used in later updates

!!! note
    Adoption protects *your* files, not the template's canonical ones. Read the
    next two sections before running anything: the conflict row in the table
    is the difference between "added" and "replaced".

## What copier does with the files you already have

This is the part that decides whether an adoption is safe, and it is worth
knowing exactly (all measured against copier 9.18.1):

| Your file | What happens |
| --- | --- |
| Named by `existing_project` / `adopt_protect` (README, LICENSE, pyproject.toml, .gitignore, .python-version, source scaffolding, `docs/` if you protect it) | Not rendered at all — yours is untouched |
| `CHANGELOG.md` | Never overwritten (`_skip_if_exists`), whatever the mode |
| Task-runner files in adopt mode (`justfile`, `Taskfile.yml`, `Makefile`, `tasks.py`, `duties.py`) | Not rendered at all |
| Anything else that already exists (`.github/workflows/ci.yml`, `.gitleaks.toml`, `renovate.json`, `cliff.toml`, ...) | **Conflict**: copier stops with `Interactive session required: Consider using --overwrite` and exits 1 — *after* writing every file it had already rendered |
| The same, with `--overwrite` | Replaced by the template's version |
| The same, with `--skip <path>` | Left alone, and everything else is still added |

The last row is the one to use. `--skip` needs no `--overwrite`, and a run
with `--skip` for every collision produces exactly the same file set as
`--overwrite` would — with your files intact. Adding `--overwrite` on top
only widens the blast radius to collisions nobody listed.

## Before you start: inspect the target

Run the detection tool first. It reports which operation fits (fresh copy /
adoption / update of a project this template already generated), what your
project already has, and the collisions above — as a ready-to-run command:

```shell
uv run --locked python tools/detect.py /path/to/existing-project
```

```
mode: adopt

kept (your files; adopt mode does not write them)
  .gitignore  CHANGELOG.md  LICENSE  README.md  pyproject.toml

COLLISIONS (exist and adopt mode would replace them -- keep them with --skip)
  .github/workflows/ci.yml
  renovate.json

next (keep your files, add the rest):
  python tools/detect.py <path> --answers answers.yml
  copier copy --trust --defaults --vcs-ref=<ref> --data-file answers.yml \
    --skip .github/workflows/ci.yml --skip renovate.json <TEMPLATE_URL> <path>
```

Copy those two lines. `--answers` writes a `--data-file` holding
`existing_project: true`, the protection list for the files you actually
have, and the Project Details that have exactly one answer on disk — it does
not guess the questionnaire's shape questions
([details](../how-to/detect.md)). Pass one `--skip` per collision: a path the
template would not render for your answers is harmless, so an over-long
`--skip` list is safe.

Then review the result the way you would any merge:

```shell
git diff          # delete the files you do not want, keep yours
git status        # untracked additions: CI, hygiene, AGENTS.md, ...
git add -A && git commit -m "chore: adopt python-copier-template"
```

Later updates: `copier update --trust` and review the diff (see
[Update Template](../how-to/update-template.md)).

## If you have a skeleton-based project

If you have a [python3-pip-skeleton](https://github.com/kasi-x/python3-pip-skeleton) based project then it is best to adopt the *first* release of this template (the tag the fork detach creates, see the warning above), then `copier update` to get to the latest. This is because `copier update` will try and merge file changes across renames done between releases, while `copier copy` cannot. This looks like:

```shell
uvx copier copy https://github.com/kasi-x/python-copier-template.git --trust --vcs-ref=<first-release-tag> /path/to/existing-project
git diff
# Examine the changes, put back anything you want to keep
git commit -m "Adopt python-copier-template <first-release-tag>"
uvx copier update /path/to/existing-project --trust
git diff
# Examine the changes, resolve any merge conflicts
git commit -m "Update to python-copier-template x.x.x"
```

## Without the detection tool

The recipe `detect` prints, by hand: answer `existing_project=true` so your
own files are protected, and `--skip` every file you want to keep that the
template also ships (check the template's tree, or run `detect` — it lists
them):

```shell
uvx copier copy --trust --vcs-ref=main --data existing_project=true \
    --skip .github/workflows/ci.yml --skip renovate.json \
    https://github.com/kasi-x/python-copier-template.git /path/to/existing-project
git diff
# Examine the changes, put back anything you want to keep
git commit -m "Adopt python-copier-template x.x.x"
```

Without those `--skip` flags copier stops at the first one of those files
(`Interactive session required`), so a half-written destination is the
failure mode to expect — not a silent replacement.

### Keep your own files (infra-only adoption)

To add only the infrastructure (CI workflows, hygiene, quality tooling
recipes) and keep your existing `README.md`, `LICENSE`, `pyproject.toml`
and `.gitignore`, protect them with `--skip`:

```shell
uvx copier copy --trust --vcs-ref=main \
    --skip README.md --skip LICENSE --skip pyproject.toml --skip .gitignore \
    https://github.com/kasi-x/python-copier-template.git /path/to/existing-project
git diff
git commit -m "chore: adopt python-copier-template (infra only)"
```

Your own files are left untouched; everything you do not have yet (CI
workflows, `.gitleaks.toml`, `AGENTS.md`, ...) is added. Wire the task
entries from `justfile` / `Taskfile.yml` into your own setup, and add the
dev dependencies the adoption flow prints.

The first-class alternative is the `existing_project` answer
(`--data existing_project=true`), which protects those same files by
default instead of listing each `--skip`; see `notes/SPEC-adoption.md`.

!!! note
    Adopting adds files; it does not remove or merge. Files of yours that the
    template does not ship — an old workflow the template has no counterpart
    for, a differently named CI job — stay exactly as they were, so delete or
    merge them yourself after reviewing `git status`.

!!! note
    Updating a project that was generated from an older template version:
    if your recorded template version still declared Jinja extensions
    (versions before the extensions removal), run your first
    `copier update` with
    `uvx --with copier-template-extensions copier update --trust ...`
    once — later updates need nothing extra.

## Getting started with your new structure

You can now read [Setup Repository](../how-to/setup-repo.md), [Developer Installation](../how-to/dev-install.md), and then follow some of the other [How-to Guides](../how-to.md).
