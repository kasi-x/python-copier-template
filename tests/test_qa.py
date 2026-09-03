"""Repository QA checks for the template repo itself (Aqua.jl spirit).

Aqua.jl tests the *quality* of a Julia package's metadata and public API:
dependency integrity, absence of undefined imports, and public-API
consistency. This repo is not a pip package — it is the copier template
itself — so the same ideas apply to the code that *runs* during generation
(``extensions.py``) and the maintenance tooling (``tools/``):

- every importable module under ``extensions.py`` and ``tools/`` imports
  cleanly;
- those modules only import stdlib or dependencies declared in the repo's
  own ``pyproject.toml``;
- the public names ``copier.yml`` references as question defaults
  (``git_user_name()`` etc.) actually exist — a dangling reference would
  abort every generation.

The template sources in ``template/`` are deliberately not scanned: they are
rendered by copier, not imported here, and are validated downstream in the
generated project (see the generated ``tests/test_qa.py``).
"""

import ast
import importlib
import sys
import tomllib
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
PYPROJECT = TOP / "pyproject.toml"

# Modules that run inside `copier copy` / maintenance scripts.
QA_MODULES = [
    "extensions",
    *sorted(
        str(p.relative_to(TOP)).removesuffix(".py").replace("/", ".")
        for p in (TOP / "tools").rglob("*.py")
        if p.name != "__init__.py"
    ),
]


def _declared_dev_deps() -> set[str]:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    declared: set[str] = set()
    for group in pyproject.get("dependency-groups", {}).values():
        for entry in group:
            name = entry.split("[")[0].strip()
            for sep in (">=", "==", "<=", "~=", "!=", ">", "<", " "):
                name = name.split(sep)[0].strip()
            if name:
                declared.add(name.replace("-", "_"))
    return declared


def test_every_qa_module_imports() -> None:
    """extensions.py and every tools/ module must import cleanly."""
    for name in QA_MODULES:
        importlib.import_module(name)


def test_qa_modules_only_import_declared_or_stdlib() -> None:
    """Imports in QA modules are stdlib or declared dev-dependencies."""
    declared = _declared_dev_deps()
    stdlib = set(sys.stdlib_module_names)
    for name in QA_MODULES:
        path = TOP / f"{name.replace('.', '/')}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top in stdlib or top.replace("-", "_") in declared, (
                        f"{path}: imports {top!r} which is neither stdlib nor declared"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top == "__future__":
                    continue
                assert top in stdlib or top.replace("-", "_") in declared, (
                    f"{path}: imports {top!r} which is neither stdlib nor declared"
                )


def test_copier_question_defaults_reference_real_functions() -> None:
    """The globals copier.yml depends on are registered by the extensions.

    copier.yml loads GitExtension / CurrentYearExtension via
    ``_jinja_extensions``; the author questions' ``default:`` call
    ``git_user_name()``, ``git_user_email()`` and ``github_username()``, and
    the LICENSE year uses ``current_year()``. These are registered onto a
    jinja2 Environment when copier instantiates the extensions — if a
    referenced global were missing, every generation would abort.
    """
    import extensions
    from jinja2 import Environment

    env = Environment(extensions=[extensions.GitExtension, extensions.CurrentYearExtension])
    for name in ("git_user_name", "git_user_email", "github_username", "current_year"):
        assert callable(env.globals.get(name)), f"copier.yml default references missing global {name!r}"
