# 25. Migrate repository documentation from Sphinx to Zensical

Date: 2026-08-31

## Status

Accepted

## Context

Previously, `python-copier-template` used Sphinx for its own documentation site in `docs/` (as recorded in ADR 0016), whereas generated projects created by the template recommend **Zensical** (an MkDocs fork with Material theme and `mkdocstrings`) as their default documentation engine.

Maintaining Sphinx for the root template repository created a mismatch between the template repository itself and the recommended documentation toolchain shipped to template users.

## Decision

We migrate the main repository documentation from Sphinx to Zensical:

1. Replace `docs/conf.py` with `zensical.toml` at the repository root.
2. Update `pyproject.toml` dev dependencies: remove Sphinx packages (`pydata-sphinx-theme`, `myst-parser`, `sphinx-autobuild`, `sphinx-copybutton`, `sphinx-design`) and add `zensical` and `mkdocstrings[python]`.
3. Update `Taskfile.yml` documentation commands to run `zensical build` and `zensical serve`.

## Consequences

- The repository documentation site engine is unified with the recommended template default (Zensical/MkDocs).
- Fast build times and clean Markdown documentation using MkDocs Material styling.
