"""Repository QA checks for the template repo itself (Aqua.jl spirit).

Aqua.jl tests the *quality* of a Julia package's metadata and public API:
dependency integrity, absence of undefined imports, and public-API
consistency. This repo is not a pip package — it is the copier template
itself — so the same ideas apply to the maintenance tooling (``tools/``):

- every module under ``tools/`` imports cleanly;
- those modules only import stdlib or dependencies declared in the repo's
  own ``pyproject.toml``.

The template sources in ``template/`` are deliberately not scanned: they are
rendered by copier, not imported here, and are validated downstream in the
generated project (see the generated ``tests/test_qa.py``).
"""

import ast
import importlib
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
PYPROJECT = TOP / "pyproject.toml"

# Maintenance-script modules (tools/ has no __init__.py by design: it is a
# script directory, not a package. Import it via an explicit path hook so
# tests can import tools.* without changing the shipped layout).

# Modules that run as maintenance scripts.
QA_MODULES = [
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
    """Every tools/ module must import cleanly."""
    if str(TOP) not in sys.path:
        sys.path.insert(0, str(TOP))
    for name in QA_MODULES:
        importlib.import_module(name)


def test_qa_modules_only_import_declared_or_stdlib() -> None:
    """Imports in QA modules are stdlib or declared dev-dependencies.

    An import name is not always its distribution name (``yaml`` ships in
    ``PyYAML``), so the installed environment's own mapping resolves it --
    the same job ``deptry --package-module-name-map`` does.
    """
    declared = {name.lower() for name in _declared_dev_deps()}
    stdlib = set(sys.stdlib_module_names)
    # tools/ modules import each other (`tools` is their namespace, and the
    # bare module names work when they are run as scripts): that is internal
    # wiring, not an undeclared dependency.
    internal = {"tools", *(name.rsplit(".", 1)[-1].lower() for name in QA_MODULES)}
    provided = {
        module: {d.replace("-", "_").lower() for d in dists} for module, dists in packages_distributions().items()
    }

    def is_declared(module: str) -> bool:
        if module.lower() in internal:
            return True
        return module.replace("-", "_").lower() in declared or bool(provided.get(module, set()) & declared)

    for name in QA_MODULES:
        path = TOP / f"{name.replace('.', '/')}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] != "__future__":
                imported = [node.module.split(".")[0]]
            else:
                continue
            for top in imported:
                assert top in stdlib or is_declared(top), (
                    f"{path}: imports {top!r} which is neither stdlib nor declared"
                )


def test_no_custom_jinja_extensions_needed() -> None:
    """Generation needs no custom Jinja extensions.

    Regression guard for the copier-template-extensions removal: copier.yml
    must not declare ``_jinja_extensions`` entries, and the questionnaire
    must not reference the old ``extensions.py`` globals (git_user_name,
    git_user_email, github_username, current_year, cuda_hint). Generation
    uses only copier builtins (now/today) and jinja2-ansible-filters
    (regex_search, to_nice_yaml) shipped with copier itself.
    """
    from copier._template import load_template_config

    config = load_template_config(TOP / "copier.yml")
    assert config.get("_jinja_extensions", []) == []

    old_globals = ("git_user_name", "git_user_email", "github_username", "current_year", "cuda_hint")
    for path in [TOP / "copier.yml", *(TOP / "questions").glob("*.yml")]:
        text = path.read_text(encoding="utf-8")
        for name in old_globals:
            assert name not in text, f"{path.name} still references removed global {name!r}"
