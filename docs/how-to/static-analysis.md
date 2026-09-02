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
