"""`copier.run_copy` is called in exactly one place: tools/batch.py's `render`.

`render`'s docstring declares itself the one render-call convention for this
repository's tools, and TODO.md's audit (§28.3 3b, §28.5 R2) found the
convention was bypassed wherever a knob was missing: cli and update_rehearsal
used to call copier directly. The knobs exist now, so the convention is
physical: exactly one tool module may call `copier.run_copy`, and the
exception list below is what keeps it that way.

`copier.update` is a different verb -- it merges into an existing tree instead
of rendering a fresh one -- and stays sanctioned in the two modules whose
subject is an update: batch (its per-request update phase) and
update_rehearsal (the tool that rehearses updates). Merely importing copier is
not a violation: cli catches `copier.errors.InteractiveSessionError`, and
update_rehearsal reads `copier.__version__`.

The check is structural -- an `ast` scan of the call expressions and the
import statements, no runtime import -- the tests/test_tool_layers.py idiom:
it costs milliseconds and cannot go red because a tool grew an expensive
import. It is stale-proofed in both directions, like test_tool_layers'
ALLOWED_UPWARD_IMPORTS: an unsanctioned direct call fails, and so does a
sanctioned module whose direct calls have vanished.
"""

from __future__ import annotations

import ast
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
TOOLS = TOP / "tools"

# The tools/ modules allowed to name copier's run_copy/run_update directly,
# each with the one-line reason the bypass (or the update verb) stays.
SANCTIONED: dict[str, str] = {
    "batch.py": "hosts the convention itself: render() wraps run_copy, and the per-request update phase calls run_update",
    "update_rehearsal.py": "its subject is `copier update` (run_update); its two run_copy renders go through batch.render",
}

COPIER_VERBS = frozenset({"run_copy", "run_update"})


def _direct_copier_calls(path: Path) -> list[str]:
    """The run_copy/run_update uses in one module (AST, no runtime).

    Caught in either spelling: the attribute call (`copier.run_copy(...)`,
    including `copier.errors`-style submodule imports) and the from-import
    (`from copier import run_copy`) that would smuggle the verb behind a bare
    name.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in COPIER_VERBS:
            found.append(f"{node.attr} (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "copier":
            names = [alias.name for alias in node.names if alias.name in COPIER_VERBS]
            if names:
                found.append(f"imports {', '.join(names)} from {node.module} (line {node.lineno})")
    return found


def test_only_sanctioned_tool_modules_call_copiers_run_verbs() -> None:
    """Every direct run_copy/run_update under tools/ sits in SANCTIONED -- and
    every sanctioned module still earns its entry.

    The one direction keeps the convention from regressing (a knob-missing
    bypass is how it eroded last time); the other keeps the exception list
    from outliving the calls it excuses.
    """
    found: dict[str, list[str]] = {
        path.name: calls for path in sorted(TOOLS.glob("*.py")) if (calls := _direct_copier_calls(path))
    }
    unsanctioned = sorted(set(found) - set(SANCTIONED))
    stale = sorted(name for name in SANCTIONED if name not in found)
    assert not unsanctioned and not stale, (
        "the single render-call convention is broken:"
        + "".join(
            f"\n  tools/{name} calls copier's run verbs directly: {', '.join(found[name])}"
            f" -- route renders through tools/batch.py:render (see its docstring for the knobs:"
            f" defaults, skip_tasks, overwrite, skip_if_exists)"
            for name in unsanctioned
        )
        + "".join(
            f"\n  tools/{name} is sanctioned ({SANCTIONED[name]}) but no longer calls"
            " copier's run verbs -- drop the stale entry from SANCTIONED (tests/test_render_convention.py)"
            for name in stale
        )
        + "\n  If a direct call is genuinely the update verb or the convention itself,"
        " name the module in SANCTIONED (tests/test_render_convention.py) with the reason."
    )


# The same convention on the test side (TODO.md §28.2-2f / §28.6-D5): every
# render a test asks for goes through the render cache (tests/render_cache.py,
# via tests/support.py's explicit-tasks helpers or the `render_cache`
# fixture). A direct `run_copy` re-pays copier's full render in the edit loop
# and re-introduces the second "1 render" semantics the cache retired, so each
# module that still names the verb must have declared why it cannot route.
SANCTIONED_TEST_MODULES: dict[str, str] = {
    "render_cache.py": "hosts the test-side entrance itself: the cached run_copy every other module reuses",
    "test_detect.py": (
        "replays the adopt recipe's skip_if_exists knob for real -- the cache's entrance pins"
        " the plain copy flags, and the knob is the contract under test"
    ),
    "test_example_adopt.py": (
        "renders a fresh git clone of the template: the subject is the adopt/update path,"
        " which needs the clone's git history, not a cached tree"
    ),
    "test_example_docs_ci.py": (
        "expects the questionnaire's validator ValueError -- a refusal before any render, so there is nothing to cache"
    ),
    "test_generation_docs.py": (
        "its subject is vcs_ref resolution (no vcs_ref: the released tag); the cache pins HEAD,"
        " so routing would stop testing the resolution"
    ),
    "test_update_path.py": (
        "its subject is the copier update merge contract, and its cache renders at declared refs"
        " (released tags) -- a revision axis the working-tree cache does not key"
    ),
}

TESTS = TOP / "tests"


def test_only_sanctioned_test_modules_call_copiers_run_verbs() -> None:
    """Every direct run_copy/run_update under tests/ sits in SANCTIONED_TEST_MODULES.

    The tools-side rule, applied to the suite: the cache is the one render
    entrance, and the exception list -- not a quiet bypass -- is where a
    render that cannot be cached says so. Stale-proofed like the tools side:
    a sanctioned module whose direct calls vanished must drop its entry.
    """
    found: dict[str, list[str]] = {
        path.name: calls for path in sorted(TESTS.glob("*.py")) if (calls := _direct_copier_calls(path))
    }
    unsanctioned = sorted(set(found) - set(SANCTIONED_TEST_MODULES))
    stale = sorted(name for name in SANCTIONED_TEST_MODULES if name not in found)
    assert not unsanctioned and not stale, (
        "the test-side single render entrance (the render cache) is bypassed:"
        + "".join(
            f"\n  tests/{name} calls copier's run verbs directly: {', '.join(found[name])}"
            " -- render through tests/render_cache.py (fixture or shared_cache()), with tests/support.py's"
            " helpers when the _tasks must run"
            for name in unsanctioned
        )
        + "".join(
            f"\n  tests/{name} is sanctioned ({SANCTIONED_TEST_MODULES[name]}) but no longer calls"
            " copier's run verbs -- drop the stale entry from SANCTIONED_TEST_MODULES"
            " (tests/test_render_convention.py)"
            for name in stale
        )
        + "\n  If a direct call is genuinely un-cacheable (a vcs_ref subject, a refusal, a git clone),"
        " name the module in SANCTIONED_TEST_MODULES (tests/test_render_convention.py) with the reason."
    )
