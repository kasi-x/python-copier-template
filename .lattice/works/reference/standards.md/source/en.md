# Standards

This document defines the code and documentation standards used in this repository.

## Code Standards

The code in this repository conforms to standards set by the following tools:

- <lt-m v="["/>ruff<lt-m v="](https://github.com/astral-sh/ruff)"/> for code formatting and linting
- <lt-m v="["/>basedpyright<lt-m v="](https://github.com/detachhead/basedpyright)"/> for static type checking (with <lt-m v="["/>pyrefly<lt-m v="](https://github.com/facebook/pyrefly)"/> as a secondary pass)

See also: How-to guides <lt-m v="["/>lint<lt-m v="](../how-to/lint.md)"/> and <lt-m v="["/>static-analysis<lt-m v="](../how-to/static-analysis.md)"/>.

## Documentation Standards

Docstrings are pre-processed using `mkdocstrings`. <lt-m v="["/>Google-style docstrings<lt-m v="](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)"/> are considered standard for this repository. Please use type hints in function signatures. For example:

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

See also: How-to guide <lt-m v="["/>build-docs<lt-m v="](../how-to/build-docs.md)"/>.
