Title: Document the CLI exit codes (1 = error, 4 = unsafe template refused)

## Summary

The CLI returns meaningfully distinct exit codes, but they are not documented anywhere user-facing. In particular, exit status **4** (`0b100`, a bitflag-era leftover) means "the template uses unsafe features and `--trust` was not given" — a condition scripts genuinely need to distinguish (e.g. to tell a user "re-run with --trust" versus "the generation failed").

## Current behavior

- `UserMessageError` → exit status 1 (message printed to stderr)
- `UnsafeTemplateError` → exit status `0b100` (= 4)

Source (v9.18.1): `copier/_cli.py:80-92` (`_handle_exceptions`). The `0b100` value carries only a code comment linking to https://github.com/copier-org/copier/issues/1328#issuecomment-1723214165 as its rationale; no docs page lists the exit codes.

## Expected behavior

A documented table of exit codes (in the docs and/or `copier --help`), e.g.:

| Exit code | Meaning |
|---|---|
| 0 | success |
| 1 | error (message printed to stderr) |
| 4 | template uses unsafe features and was run without `--trust`; nothing was generated |

Whether `4` stays as-is or migrates to a more conventional value is a maintainer decision — but either way the meaning should be documented, since CI wrappers around `copier copy` can only react to documented codes.

## Environment

Copier 9.18.1, Python 3.11.14, Linux (Ubuntu)
