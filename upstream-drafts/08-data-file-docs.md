Title: Document that --data/--data-file values count as answers for skipped questions

## Summary

Values supplied via `--data` / `--data-file` are recorded as answers even for questions whose `when` condition is false (i.e. that were skipped). This is reasonable and consistent behavior, but it is undocumented and surprising when writing non-interactive generation scripts. Relatedly, answers for skipped questions are only validated when the question's `when` is true at the moment of evaluation.

## Current behavior

Observed with v9.18.1 against a template with a `when`-gated question and a `when: false` internal variable:

- `--data-file` providing a value for a gated question drives that question's answer even when the gate skips it (`answers.init` values win).
- Validation of an answer runs only `if self.get_when() and not self.secret` — see the code comment at `copier/_user_data.py:289-294` ("Computed values (i.e., `when: false`) are intentionally not validated at the moment", referencing #1779 / #1785).
- Dynamic (Jinja-rendered) `choices` strings render and validate correctly in 9.18.1.

The behavior is fine — it is just undocumented, which makes non-interactive answer files hard to reason about.

## Expected behavior

The non-interactive generation docs should state:

1. `--data` / `--data-file` values are treated as if the question had been answered, including questions that end up skipped by `when`.
2. Answers are validated only when the question's `when` condition is true at evaluation time.

## Related

- #1951 (boolean handling in `--data-file`, open)
- #2142 (process substitution not supported in `--data-file`, open)

## Environment

Copier 9.18.1, Python 3.11.14, Linux (Ubuntu)
