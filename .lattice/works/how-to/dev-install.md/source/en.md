# Setup Developer Environment

These instructions will take you through the minimal steps required to get a dev environment setup, so you can run the tests locally.

## Clone the repository

First clone the repository locally using <lt-m v="["/>Git<lt-m v="](https://git-scm.com/downloads)"/>. There is a link on the GitHub interface to allow you to do this. SSH is recommended if you have setup a key. Enter the directory that it is cloned into to continue.

## Install dependencies

It is recommended that developers use a <lt-m v="["/>vscode devcontainer<lt-m v="](https://code.visualstudio.com/docs/devcontainers/containers)"/>. This repository contains configuration to set up a containerized development environment that suits its own needs.

Ensure you have the <lt-m v="["/>vscode devcontainer extension<lt-m v="](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)"/> installed.

```
code .
```

Click on 'Reopen in Container' when prompted on startup or, if vscode is already running, open the command menu with CTRL+SHIFT+P, search for and run 'Reopen in Container'.

The developer container creates and activates a venv (stored in `/cache/venv-for/path/to/project`) and this will be managed by any `uv sync` command as explained in <lt-m v="["/>lock-requirements<lt-m v="](./lock-requirements.md)"/>. Any rebuild of the container will recreate this venv, but the dependencies will be stored in a cross container cache so that rebuilds are quick.

## Build and test

Now you have a development environment you can run the tests in a new terminal:

```
task check
```

`task check` runs `lint`, `type-check`, `test` and `docs` as parallel task
dependencies — the loop behind them is [Check a Change Without the Full
Suite](test-loop.md):

- <lt-m v="["/>Build Documentation<lt-m v="](./build-docs.md)"/>
- <lt-m v="["/>Static Analysis<lt-m v="](./static-analysis.md)"/>
- <lt-m v="["/>Linting<lt-m v="](./lint.md)"/>
