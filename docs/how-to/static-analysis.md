# Run static analysis using basedpyright (plus pyrefly or ty)

Static type analysis is done with [basedpyright](https://docs.basedpyright.com) —
always enabled — plus an optional secondary checker,
[pyrefly](https://github.com/facebook/pyrefly) (default) or
[ty](https://docs.astral.sh/ty/), depending on the `type_checker`
setting in `pyproject.toml`. The checkers validate type definitions in source
files without running them, and highlight potential issues where types do not
match. You can run them with:

```
$ task type-check
```

`type-check` runs basedpyright first (the primary checker), then the secondary
checker, then the static-analysis tools (vulture, deptry, typos). For
MicroPython projects it also runs a dedicated basedpyright pass against the
firmware type stubs (`firmware/pyrightconfig.json`).

## typos: the spellchecker that rewrites code

`typos` scans every text file, and its tokenizer splits identifiers
(`camelCase`/`snake_case`) into words — so a dictionary word inside an
identifier is checked like prose. That makes `task fix`'s `typos -w`
pass a **code-rewriting** tool, not just a docs tool:

- A word with exactly **one** dictionary correction is auto-applied by
  `-w`, identifiers included: `serie_total` becomes `series_total`,
  `SerieReader` becomes `SeriesReader`, silently. If the identifier
  mirrors an external name (an API field, a JSON key), that rename is a
  bug.
- A word with **multiple** corrections (`fpr` → for / far / fps) is
  never auto-applied, but still fails `type-check`.

The policy: a legitimate acronym or domain word lives in the
`[tool.typos.default]` ignore lists in `pyproject.toml`
(`extend-ignore-words-re` / `extend-ignore-identifiers-re`) — not in a
rename. The lists ship with the fairness-metrics acronyms (`fpr`, `fnr`)
the ethics appendix's examples use; add yours there when the checker
flags a word that is genuinely correct. Everything else the spellchecker
catches is probably a real typo — in a comment, a docstring, or your
identifier — and `typos -w` fixing it is the feature, visible in the
diff you review before committing.
