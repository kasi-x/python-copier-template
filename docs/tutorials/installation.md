# Install template pre-requisites

This tutorial will take you through installing copier, the templating engine that will allow you
to create new projects from the template, update existing projects in line with it, and keep projects in sync with changes to it.

## Install uv

We recommend that you invoke copier via `uvx`, which will download, install, and run it in its own isolated `venv`. 

Please follow the [uv installation instructions](https://docs.astral.sh/uv/getting-started/installation).


## Try it out

If you run `uvx copier --version` then `copier` will be downloaded, installed, and run, and will print its version.

## Conclusion

You now have the pre-requisites to allow you to [create a new project](./create-new.md) and [adopt an existing one](./adopt-existing.md).
