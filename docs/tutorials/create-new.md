# Create a new repo from the template

Once you have followed the [installation](./installation.md) tutorial, you can use `copier` to make a new project from the template:

```
git init --initial-branch=main /path/to/my-project
# $_ resolves to /path/to/my-project
uvx copier copy --trust https://github.com/kasi-x/python-copier-template.git $_
```

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
