# 8. Use tox and pre-commit

Date: 2023-01-18

## Status

Accepted (Historical - tox later replaced by Task Runner in ADR 0024)

## Context

We require an easy way to locally run the same checks as CI. This provides a rapid inner-loop developer experience.

## Decision

Use tox and pre-commit.

tox is an automation tool that we use to run all checks in parallel.

pre-commit provides a hook into git commit which runs some of the checks against the changes you are about to commit.

## Decision detail

There are a number of things that CI needs to run:

- pytest
- black
- mypy
- flake8
- isort
- build documentation

The initial approach this module took was to integrate everything under pytest that had a plugin:

```
[pytest] -> [pytest-black], [pytest-mypy], [pytest-flake8 -> flake8-isort]
```

To address performance issues, the structure was rearranged:

```
pytest
black
mypy
flake8 -> flake8-isort
```

Pre-commit was added for git hooks:

```bash
$ pre-commit install
```

Finally tox was added to run all of the CI checks including the documentation build:

```bash
$ tox -p
```

The workflow looks like this:

- Save file, editor runs formatting and linting
- Run `tox -p` and fix issues until it succeeds
- Commit files and pre-commit runs checks
- Push to remote and CI runs checks

## Consequences

Running `tox -p` before pushing verifies that CI will most likely succeed.
