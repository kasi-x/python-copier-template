# Run static analysis using basedpyright or pyrefly

Static type analysis is done with [basedpyright](https://docs.basedpyright.com) or [pyrefly](https://github.com/facebook/pyrefly) dependent on the settings in `pyproject.toml`. It checks type definition in source files without running them, and highlights potential issues where types do not match. You can run it with:

```
$ task type-check
```
