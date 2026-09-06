Title: Do not emit DirtyLocalWarning when the template is an explicit local directory

## Summary

When the template source is a plain local path, copier warns `Dirty template changes included automatically.` on every invocation. Passing a local directory **is** the explicit statement "use this working tree as-is", so the warning carries no information and is pure noise — it shows up on every test run of every project that renders against a local checkout during development.

## Current behavior

```console
$ copier copy --defaults /home/me/my-template ./dest
/home/me/.venv/.../copier/_vcs.py:412: DirtyLocalWarning: Dirty template changes included automatically.
  warn(
```

Source (v9.18.1): `copier/_vcs.py:407-414` (`warn(..., DirtyLocalWarning)`).

## Expected behavior

Either:

- Do not warn when the template source is a local directory (the user pointed at a working tree on purpose), or
- Keep the warning but document that it is a `DirtyLocalWarning` (Python `Warning` category) that API users can filter, so CLI-only users at least know why they always see it.

The warning is meaningful for `copier update` workflows against tracked templates; the noise case is the local-directory `copy` flow.

## Environment

Copier 9.18.1, Python 3.11.14, Linux (Ubuntu)
