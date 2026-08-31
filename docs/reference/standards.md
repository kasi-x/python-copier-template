# Standards

This document defines the code and documentation standards used in this repository.

## Code Standards

The code in this repository conforms to standards set by the following tools:

- [ruff](https://github.com/astral-sh/ruff) for code formatting and linting
- [basedpyright](https://github.com/detachhead/basedpyright) for static type checking

See also: How-to guides [lint](../how-to/lint.md) and [static-analysis](../how-to/static-analysis.md).

## Documentation Standards

Docstrings are pre-processed using `mkdocstrings`. [Google-style docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings) are considered standard for this repository. Please use type hints in function signatures. For example:

```python
def func(arg1: str, arg2: int) -> bool:
    """Summary line.

    Extended description of function.

    Args:
        arg1: Description of arg1
        arg2: Description of arg2

    Returns:
        Description of return value
    """
    return True
```

Documentation is contained in the `docs` directory.

See also: How-to guide [build-docs](../how-to/build-docs.md).
