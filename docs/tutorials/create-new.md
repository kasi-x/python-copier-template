# Create a new repo from the template

Once you have followed the [installation](./installation.md) tutorial, you can use `copier` to make a new project from the template:

```
git init --initial-branch=main /path/to/my-project
# $_ resolves to /path/to/my-project
uvx --with copier-template-extensions copier copy --trust --vcs-ref=main \
    https://github.com/kasi-x/python-copier-template.git $_
```

`--vcs-ref=main` asks for the current main branch. Without it copier checks
out the **latest git tag**, and this repository still carries inherited
upstream tags that point at the old, pre-fork template (they are re-tagged
at the v1.0 fork detach). `--with copier-template-extensions` is required
because the template ships custom Jinja extensions that must be importable
by copier itself — a bare `uvx copier` runs in an isolated environment
without them.

This will:

- Ask some questions about the project to be created (each area first asks
  whether to use its [recommended settings](../reference/questionnaire.md))
- Expand the template with the answers give
- Record the answers in the project so they can be used in later updates
- Create a git repository if the directory is not already one

## Committing the results

You can now check what the template has created, tweak the results if desired, [lock the requirements](../how-to/lock-requirements.md), and commit the results:
```shell
$ cd /path/to/my-project
$ uv sync
$ git add .
$ git commit -m "Expand from python-copier-template x.x.x"
```

## Uploading to GitHub

You can now [create a new blank project on GitHub](https://github.com/new). Choose the same GitHub owner, repo name and description that you answered in the questions earlier. GitHub will now give you the commands needed to upload your repo from GitHub.


## Getting started with your new repo

You can now [set up the repo](../how-to/setup-repo.md), [set up a dev environment](../how-to/dev-install.md), and then follow some of the other [how-to guides](../how-to.md).
