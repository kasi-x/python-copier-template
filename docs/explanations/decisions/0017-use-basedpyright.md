# 17. Use basedpyright (or pyrefly) for type checking

Date: 2024-02-15 (updated 2026-08)

## Status

Accepted

## Context

Pyright is faster than mypy, and catches more errors. In practice (lifelog
refactor), basedpyright — a pyright fork — proved most effective:

- **0 errors / 0 warnings** achievable on a large existing codebase
- warning-level control per-rule (`reportPrivateUsage`, `reportUnusedParameter`,
  etc.) lets you disable **duplicated detection** that ruff/vulture already cover
- `enableTypeIgnoreComments` supports mypy-style `# type: ignore` for code shared
  across checkers

pyrefly (Meta) is a lightweight alternative useful as a secondary check.

## Decision

Replace pyright/mypy with **basedpyright** as the primary type checker and
**pyrefly** as an alternative. Drop mypy entirely.

A single `strictness` question controls both the type-annotation requirements
and the toolchain strictness:
`none` / `basic` / `recommended` (default) / `full`.

## Consequences

- New projects get basedpyright with sensible defaults out of the box.
- `partial` (default) fits both new and existing code, avoiding the "thousands of
  errors on retrofit" problem.
- Type-stub packages (`types-boto3`, `types-boto3-s3`, etc.) are dev-dependencies
  that give precise types without bloating the runtime (Lambda) zip.
