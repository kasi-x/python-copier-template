Title: Report all missing required answers at once in non-interactive mode (and raise a clean error, not a bare ValueError)

## Summary

Two related issues when running non-interactively (`--defaults` / `--data` / `--data-file`) with an incomplete answer set:

1. Copier aborts on the **first** missing required answer. After fixing that one answer and re-running, it fails on the next one. In CI this means one round-trip per missing answer instead of seeing the full list at once.
2. The failure is raised as a bare `ValueError`, which produces a full traceback instead of a clean one-line user message.

## Current behavior

```console
$ copier copy --defaults ./tpl ./dest
Traceback (most recent call last):
  ...
  File "copier/_main.py", line 659, in _ask
    raise ValueError(f'Question "{var_name}" is required')
ValueError: Question "package_name" is required
$ echo $?
1
```

Source (v9.18.1): `copier/_main.py:659` (`_ask`) raises `ValueError` on the first question whose default is `MISSING` while `--defaults` is active. `ValueError` is not handled by `_handle_exceptions` (`copier/_cli.py:76-95`), so it escapes as a traceback.

## Expected behavior

- Collect **all** questions that would fail and report them in one message, e.g.:
  `Missing answers for required questions: package_name, git_platform`
- Raise it as a `UserMessageError` (clean stderr message, exit 1) rather than a bare `ValueError` with traceback.

## Environment

Copier 9.18.1, Python 3.11.14, Linux (Ubuntu)
