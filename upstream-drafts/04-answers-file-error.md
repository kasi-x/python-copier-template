Title: `--answers-file`: better error message (and/or accept absolute paths)

## Summary

`--answers-file` must be a path relative to the destination directory, but the error for getting this wrong gives no hint about the requirement or how to fix it.

## Current behavior

```console
$ copier copy --answers-file /tmp/answers.yml <template> ./dest
ValueError: "/tmp/answers.yml" is not a relative path
```

Source (v9.18.1): `copier/errors.py:111-115` (`PathNotRelativeError`).

## Expected behavior

At minimum, state the requirement and the fix in the message, e.g.:

```
"/tmp/answers.yml" is not a relative path. The answers file must be given as a path relative to the destination directory, e.g. --answers-file .copier-answers.yml
```

Alternatively, accept absolute paths and resolve them against the destination — but that changes documented behavior, so the message improvement is the safe fix.

## Environment

Copier 9.18.1, Python 3.11.14, Linux (Ubuntu)
