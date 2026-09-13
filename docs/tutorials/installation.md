# Install template pre-requisites

This tutorial will take you through installing copier, the templating engine that will allow you
to create new projects from the template, update existing projects in line with it, and keep projects in sync with changes to it.

`git` is required too: copier expands a revision of the template repository, and the projects it
generates are git repositories.

## Install uv

We recommend that you invoke copier via `uvx`, which will download, install, and run it in its own isolated `venv`. 

Please follow the [uv installation instructions](https://docs.astral.sh/uv/getting-started/installation).


## Try it out

If you run `uvx copier --version` then `copier` will be downloaded, installed, and run, and will print its version.

## Get the template's CLI

The repository also ships a one-command wrapper, `python-copier-template new`, which picks the
release tag to expand, decides between creating a project and adopting an existing one, and warns
about — or protects — the files the target already has. No `--vcs-ref` or other copier flag is
needed:

```shell
git clone https://github.com/kasi-x/python-copier-template.git
uv run --project python-copier-template python-copier-template --help
```

`uv` installs the CLI's dependencies into the checkout's environment on the first run. Inside the
checkout the equivalent forms are `uv run python-copier-template …` and
`uv run python -m tools.cli …`; add `--preset <name>` for a fully non-interactive run (see
[Create a New Project](./create-new.md)).

## Conclusion

You now have the pre-requisites to allow you to [create a new project](./create-new.md) and [adopt an existing one](./adopt-existing.md).
