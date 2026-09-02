# 17. Use basedpyright (plus a secondary checker) for type checking

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

A second, independent checker adds a different analysis pass:
pyrefly (Meta) is a lightweight, well-tested secondary checker;
ty (Astral) is a fast Rust checker that complements basedpyright but is still
in beta.

## Decision

**basedpyright is always the primary type checker.** The `type_checker`
question chooses the secondary checker that runs alongside it:
**pyrefly** (default — longest track record in this template) or **ty**
(Astral, optional). Drop mypy entirely.

A single `strictness` question controls both the type-annotation requirements
and the toolchain strictness:
`none` / `basic` / `recommended` (default) / `full`.

For MicroPython projects the secondary checker (pyrefly or ty) runs over the
CPython-side code (`tests/` + `firmware/core/`); the firmware's hardware files
are checked only by a dedicated basedpyright pass against the port stubs.

## Consequences

- New projects get basedpyright (always) plus the chosen secondary checker
  (pyrefly by default) out of the box.
- `partial` (default) fits both new and existing code, avoiding the "thousands of
  errors on retrofit" problem.
- Type-stub packages (`types-boto3`, `types-boto3-s3`, etc.) are dev-dependencies
  that give precise types without bloating the runtime (Lambda) zip.
