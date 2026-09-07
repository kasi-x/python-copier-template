Title: UnsafeTemplateError message should state that generation was refused and nothing was written

## Summary

When a template uses unsafe features and the user does not pass `--trust`, copier prints a message that reads like a suggestion and exits with status 4. Nothing states that **generation was refused and the destination was left untouched**, so users assume generation succeeded (or half-succeeded) and hunt for output files that were never written. The wording was already improved once in #1269; this proposes going one step further.

## Current behavior

```console
$ copier copy --defaults ./tpl ./dest
Template uses potentially unsafe feature: tasks.
If you trust this template, consider adding the `--trust` option when running `copier copy/update`.
$ echo $?
4
$ ls dest
ls: cannot access 'dest': No such file or directory
```

(with `tpl/copier.yml` containing `_tasks: [echo hi]`)

Two problems:

1. The message is phrased as a suggestion ("consider adding..."), not as a refusal. It does not say that nothing was generated.
2. The exit status 4 is not documented anywhere user-facing (see #1328 discussion; the code itself carries only a GitHub-comment URL as its rationale in `copier/_cli.py:88-92`).

Source (v9.18.1): the message is built in `copier/errors.py:157-166` (`UnsafeTemplateError.__init__`), raised from `copier/_main.py:314-328` (`_check_unsafe`), and mapped to `return 0b100` in `copier/_cli.py:88-92`.

## Expected behavior

State the refusal and its consequence explicitly, e.g.:

```
Refusing to generate: template uses potentially unsafe feature(s): tasks.
Nothing was written to the destination.
If you trust this template, re-run with `--trust`, or add it to the trust list in your Copier settings.
```

## Environment

Copier 9.18.1, Python 3.11.14, Linux (Ubuntu)
