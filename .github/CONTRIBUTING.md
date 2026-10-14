# Contribute to the template
Contributions and issues are most welcome! All issues and pull requests are handled through [GitHub](https://github.com/politeuma/architekton-py/issues). Also, please check for any existing issues before filing a new one. If you have a great idea but it involves big changes, please file a ticket before making a pull request! We want to make sure you don't spend your time coding something that might not fit the scope of the project.

## Security

Please do not open a public issue for security vulnerabilities. Report them
privately via the [Security Advisory workflow](https://github.com/politeuma/architekton-py/security/advisories/new) — see [SECURITY.md](../SECURITY.md) for details.

## Issue or Discussion?

Github also offers [discussions](https://github.com/politeuma/architekton-py/discussions) as a place to ask questions and share ideas. If your issue is open ended and it is not obvious when it can be "closed", please raise it as a discussion instead.

## Getting changes into the template

This template is a place to pull together agreed best practices from various sources. As such, it is difficult to demonstrate a change without seeing it in action in another repo. Please link to a repo that has the desired behaviour when proposing changes to the template.


## Ethics / regional / operational rule sections

The section texts live in [law-map's guidance tree](https://github.com/politeuma/law-map/tree/main/guidance/sections)
(CC BY 4.0), which owns their content, sources, and review cadence. New sections and
corrections are pull requests there, not here; obligation-level changes go
through [law-map](https://github.com/politeuma/law-map)'s Legal
RFC issue. This repo owns only the wiring — the derived `when` conditions
(`_shared/daimonion-when.jinja`) — governed by [GOVERNANCE.md](../GOVERNANCE.md).

## Blast radius

What a change touches decides what must pass before the PR. CI gates the
render matrix by change scope (the docs-only detector in ci.yml), so the
table below is what *you* run locally — the cheapest tier that covers the
blast radius, never the whole suite.

| Change scope | Required verification |
| --- | --- |
| Docs only (`README.md`, `docs/*.md`) | `task lint type-check` — CI skips the render matrix for docs-only PRs, so typos and format debt must be caught locally |
| Template payload (`template/`, `_shared/`, `questions/`) | `task test-fast` plus `task verify-delta` — the render twin proves which witness leaves the change can affect: a semantic diff narrows the candidate set, then only candidates are re-rendered from a baseline checkout and compared by manifest (file list + sha256, answers normalized); it exits 0 when every candidate is byte-identical |
| Questionnaire (`copier.yml`, `questions/*.yml`) | `task regen` then `task test-fast` — regen is the one-command pipeline: witness leaves, batch verdicts, tier ledger, generated docs, predicate report |

## Contributing 101

The cheapest real change an outsider can make: add or correct an ethics /
regional / operational rule section in
[law-map's guidance tree](https://github.com/politeuma/law-map/tree/main/guidance/sections)
(copy its `guidance/sections/_template.md`, fill every field, run
`just manifest`). It needs no knowledge of this template's questionnaire.
Section files are `guidance/sections/<tier>/<slug>.md` (YAML front matter
plus prose body); the generated index is `guidance/sections/MANIFEST.yml`.
In this repo, the next-cheapest change is a docs fix — see the blast-radius table
above.


## Checking your changes before making a PR

The template has tests for:

- Generating a new project from scratch
- Updating the [example project](https://github.com/politeuma/architekton-py-example)
- Checking that both of the above produce the same results

However, this does not test whether processes like CI and docs work correctly. You can ensure that these are checked by:

- Making your changes on a branch of <https://github.com/politeuma/architekton-py>
- Running `uvx copier update --vcs-ref=<branch_name>` in the repo where you would like to demonstrate the behaviour
- Linking to that demonstration repo in the PR

## Developer Information

It is recommended that developers use a [vscode devcontainer](https://code.visualstudio.com/docs/devcontainers/containers). This repository contains configuration to set up a containerized development environment that suits its own needs.

For more information on common tasks like setting up a developer environment, running the tests, and the lint workflow, see the [How-to guides](https://politeuma.github.io/architekton-py/main/how-to.html)
