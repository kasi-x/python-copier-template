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
- Expand the template with the answers given
- Ask if you would like to overwrite conflicting files (always choose yes)
- Record the answers in the project so they can be used in later updates

!!! note
    Copier will *overwrite* files with the template files. Please check the changes using `git diff` and put back anything you would like to keep from the existing project files.

## If you have a skeleton-based project

If you have a [python3-pip-skeleton](https://github.com/kasi-x/python3-pip-skeleton) based project then it is best to adopt the `1.0.0` release of this template, then `copier update` to get to the latest. This is because `copier update` will try and merge file changes across renames done between releases, while `copier copy` cannot. This looks like:

```shell
uvx copier copy https://github.com/kasi-x/python-copier-template.git --trust --vcs-ref=1.0.0 /path/to/existing-project
git diff
# Examine the changes, put back anything you want to keep
git commit -m "Adopt python-copier-template 1.0.0"
uvx copier update /path/to/existing-project --trust
git diff
# Examine the changes, resolve any merge conflicts
git commit -m "Update to python-copier-template x.x.x"
```

## If you do not have a skeleton-based project

If you have a project with a different structure then it is best to go straight to the current main branch (`--vcs-ref=main` — without it copier picks the latest git tag, which here still points at the old, pre-fork template):

```shell
uvx copier copy --trust --vcs-ref=main \
    https://github.com/kasi-x/python-copier-template.git /path/to/existing-project
git diff
# Examine the changes, put back anything you want to keep
git commit -m "Adopt python-copier-template x.x.x"
```

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
dev dependencies the adoption flow prints. A first-class
`existing_project` answer (protect-by-default without `--skip`) is
specified in `notes/SPEC-adoption.md` for a future release.

!!! note
    Copier does not touch any already existing files that do not conflict with the ones in the template. Therefore, you may end up with files in your project you no longer need such as old github workflows. These would need to be manually deleted.

!!! note
    Updating a project that was generated from an older template version:
    if your recorded template version still declared Jinja extensions
    (versions before the extensions removal), run your first
    `copier update` with
    `uvx --with copier-template-extensions copier update --trust ...`
    once — later updates need nothing extra.

## Getting started with your new structure

You can now read [Setup Repository](../how-to/setup-repo.md), [Developer Installation](../how-to/dev-install.md), and then follow some of the other [How-to Guides](../how-to.md).
