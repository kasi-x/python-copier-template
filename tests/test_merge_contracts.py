"""The adopt-time merge contracts, declared in tests/matrix/invariants.yml.

Every merge kind tools/adopt.py can apply to an adopter's file makes promises
about its outcome. §25.5/V5 asks for those promises as an *artifact* -- the
same oracle shape the render invariants use -- rather than as checks that live
only inside the merge implementations, so that a new merge kind has to declare
its contract and a contract change has to be deliberate:

- ``tests/matrix/invariants.yml``'s ``merges:`` section declares, per kind,
  the conditions that kind promises.
- ``tools/invariants.py`` parses that section and refuses unknown shape; this
  module owns the condition *implementations* (the same split the render
  predicates use) and holds the registry against the dispatch:
  a kind the code offers without a declared contract, or a declared contract
  whose kind the code lost, fails here.
- each condition is proved twice: it holds on a benign merge, and it *fails*
  on a faked violation (the repo's guard-the-guard pattern -- a checker that
  cannot detect its own violation is decoration).

The conditions, in the vocabulary the registry uses:

original_is_prefix
    The pre-merge content is still a byte prefix of the result: an adopter's
    own lines are never moved or rewritten. Checked with
    tools/file_merge.py's own ``original_is_preserved`` so the implementation
    and the contract cannot drift.
idempotent
    Applying the merge a second time changes nothing: the source's entries are
    recognized as present the second time around.
existing_declared
    Everything the target declared before the merge -- ignore lines, recipe
    blocks, tasks, workflow jobs, dependency constraints -- is still declared
    afterwards, unchanged.
reparse
    The merged file still parses in its own format.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import file_merge  # noqa: E402
from tools import pyproject_merge  # noqa: E402

INVARIANTS = TOP / "tests" / "matrix" / "invariants.yml"

# --------------------------------------------------------------------------- #
# per-kind drivers: a realistic (target, source) sample and the production
# merge call, on its writing path (`append=True` where the kind defaults to
# report-only). Kinds whose target is a file the adopter already has -- the
# case every contract below talks about. (ci_caller writes a *new* file and
# merge_tool_config merges a table, not a file; their own unit tests pin them.)
# --------------------------------------------------------------------------- #

Sample = tuple[Callable[[Path, Path, bool], Any], tuple[str, str]]


def _sample_gitignore(target: Path, source: Path, apply: bool) -> Any:
    return file_merge.merge_gitignore(target, source, apply=apply)


def _sample_makefile(target: Path, source: Path, apply: bool) -> Any:
    return file_merge.merge_recipes(target, source, "makefile", apply=apply)


def _sample_justfile(target: Path, source: Path, apply: bool) -> Any:
    return file_merge.merge_recipes(target, source, "justfile", apply=apply)


def _sample_taskfile(target: Path, source: Path, apply: bool) -> Any:
    return file_merge.merge_taskfile(target, source, append=apply)


def _sample_python_tasks(target: Path, source: Path, apply: bool) -> Any:
    return file_merge.merge_python_tasks(target, source, append=apply)


def _sample_ci_jobs(target: Path, source: Path, apply: bool) -> Any:
    return file_merge.merge_ci_jobs(target, source, append=apply)


def _sample_pyproject_dependencies(target: Path, source: Path, apply: bool) -> Any:
    return pyproject_merge.merge_dependencies(target, source, apply=apply)


SAMPLES: dict[str, Sample] = {
    "gitignore": (_sample_gitignore, (".venv/\n*.pyc\n", "*.pyc\n__pycache__/\n")),
    "makefile": (_sample_makefile, ("lint:\n\t@echo lint\n", "lint:\n\t@echo lint\n\ntest:\n\t@echo test\n")),
    "justfile": (_sample_justfile, ("lint:\n    echo lint\n", "lint:\n    echo lint\n\ntest:\n    echo test\n")),
    "taskfile": (
        _sample_taskfile,
        (
            "version: '3'\ntasks:\n  lint:\n    cmds: [echo lint]\n",
            "version: '3'\ntasks:\n  lint:\n    cmds: [echo lint]\n  test:\n    cmds: [echo test]\n",
        ),
    ),
    "python_tasks": (
        _sample_python_tasks,
        (
            'from duty import duty\n\n\n@duty\ndef lint():\n    """Lint."""\n',
            'from duty import duty\n\n\n@duty\ndef lint():\n    """Lint."""\n\n\n@duty\ndef test():\n    """Test."""\n',
        ),
    ),
    "ci_jobs": (
        _sample_ci_jobs,
        (
            "name: my-ci\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: make\n",
            (
                "name: CI\non: [push]\njobs:\n"
                "  lint:\n    uses: ./.github/workflows/_tasks.yml\n    with:\n      task_runner: task\n      task: lint\n"
                "  test:\n    uses: ./.github/workflows/_test.yml\n"
            ),
        ),
    ),
    "pyproject_dependencies": (
        _sample_pyproject_dependencies,
        (
            '[project]\nname = "x"\nversion = "0"\ndependencies = ["rich"]\n',
            '[project]\nname = "x"\nversion = "0"\ndependencies = ["rich", "httpx>=0.27"]\n',
        ),
    ),
}

CODE_KINDS = tuple(sorted(SAMPLES))

# --------------------------------------------------------------------------- #
# the condition implementations: checker(kind, before, after, target) raises
# AssertionError on violation. `before`/`after` are the target file's bytes
# pre- and post-merge.
# --------------------------------------------------------------------------- #


def _check_original_is_prefix(
    kind: str,
    before: bytes,
    after: bytes,
    target: Path,  # noqa: ARG001  # pyright: ignore[reportUnusedParameter]  WHYNOT: every checker shares the (kind, before, after, target) contract-call signature
) -> None:
    assert file_merge.original_is_preserved(before, after), (
        f"{kind}: the merge moved or rewrote bytes the adopter already had"
    )


def _check_idempotent(
    kind: str,
    before: bytes,  # pyright: ignore[reportUnusedParameter]  WHYNOT: shared contract-call signature; the second pass compares against the file, not the bytes
    after: bytes,
    target: Path,
) -> None:
    runner, (_target_text, source_text) = SAMPLES[kind]
    source = target.parent / "source"
    source.write_text(source_text, encoding="utf-8")
    runner(target, source, True)
    assert target.read_bytes() == after, f"{kind}: merging the same source twice changed the file again"


def _declared(kind: str, text: str) -> Any:
    """What a text declares, read back in the kind's own format."""
    if kind == "gitignore":
        return {line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")}
    if kind in ("makefile", "justfile"):
        pattern = file_merge.MAKEFILE_TARGET if kind == "makefile" else file_merge.JUST_RECIPE
        skip = frozenset() if kind == "makefile" else file_merge.IGNORED_JUST_NAMES
        # the implementation's own block parser is the point: reading the same
        # blocks it reads is what stops the contract and the merge from drifting
        return set(file_merge._recipe_blocks(text, pattern, skip=skip))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    if kind == "taskfile":
        return yaml.safe_load(text)["tasks"]
    if kind == "python_tasks":
        return {node.name for node in ast.parse(text).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if kind == "ci_jobs":
        return yaml.safe_load(text)["jobs"]
    if kind == "pyproject_dependencies":
        document = tomllib.loads(text)
        return sorted(str(entry) for entry in document["project"]["dependencies"])
    msg = f"no declared-reader for {kind}"
    raise AssertionError(msg)


def _check_existing_declared(
    kind: str,
    before: bytes,
    after: bytes,
    target: Path,  # pyright: ignore[reportUnusedParameter]  WHYNOT: shared contract-call signature
) -> None:
    before_declared = _declared(kind, before.decode())
    after_declared = _declared(kind, after.decode())
    if isinstance(before_declared, dict):
        lost = {name: value for name, value in before_declared.items() if after_declared.get(name) != value}
        assert not lost, f"{kind}: the merge changed what the target already declared: {sorted(lost)}"
    else:
        gone = sorted(set(before_declared) - set(after_declared))
        assert not gone, f"{kind}: the merge dropped declared entries: {gone}"


def _check_reparse(
    kind: str,
    before: bytes,  # pyright: ignore[reportUnusedParameter]  WHYNOT: shared contract-call signature; reparse reads the result only
    after: bytes,
    target: Path,  # pyright: ignore[reportUnusedParameter]  WHYNOT: shared contract-call signature
) -> None:
    text = after.decode()
    try:
        if kind in ("taskfile", "ci_jobs"):
            parsed: Any = yaml.safe_load(text)
            assert parsed is not None, f"{kind}: the merged file no longer parses to a mapping"
        elif kind == "pyproject_dependencies":
            parsed = tomllib.loads(text)
        elif kind == "python_tasks":
            parsed = ast.parse(text)
        else:
            msg = f"{kind} declares reparse but the checker has no parser for it"
            raise AssertionError(msg)
        assert parsed is not None
    except (yaml.YAMLError, tomllib.TOMLDecodeError, SyntaxError) as exc:
        # a parse failure arrives as the parser's own exception; the contract
        # speaks AssertionError, so translate before it escapes
        msg = f"{kind}: the merged file no longer parses in its own format: {exc}"
        raise AssertionError(msg) from exc


CONDITIONS: dict[str, Callable[[str, bytes, bytes, Path], None]] = {
    "original_is_prefix": _check_original_is_prefix,
    "idempotent": _check_idempotent,
    "existing_declared": _check_existing_declared,
    "reparse": _check_reparse,
}


# The faked violation per condition: how (before, after) is tampered with so a
# correct checker must fail. Tampering the *inputs* keeps the merge itself
# honest and tests only the checker's sight.
def _phantom_before(kind: str, before: str) -> str:  # noqa: PLR0911  WHYNOT: one branch per merge kind; a dispatch table of lambdas would hide each kind's shape
    """`before` augmented with a declared entry the merge never produced."""
    if kind == "gitignore":
        return before + "phantom/\n"
    if kind == "makefile":
        return before + "phantom:\n\t@echo phantom\n"
    if kind == "justfile":
        return before + "phantom:\n    echo phantom\n"
    if kind == "taskfile":
        return before.replace("tasks:\n", "tasks:\n  phantom:\n    cmds: [echo phantom]\n", 1)
    if kind == "python_tasks":
        return before + "\n\ndef phantom():\n    pass\n"
    if kind == "ci_jobs":
        return before.replace("jobs:\n", "jobs:\n  phantom:\n    runs-on: ubuntu-latest\n", 1)
    if kind == "pyproject_dependencies":
        return before.replace('["rich"]', '["rich", "phantom-pkg"]')
    msg = f"no phantom for {kind}"
    raise AssertionError(msg)


def _violation(kind: str, condition: str, before: bytes, after: bytes) -> tuple[bytes, bytes]:
    if condition == "original_is_prefix":
        cut = len(before) // 2
        return before, before[:cut] + b"# tampered\n" + after[cut:]
    if condition == "idempotent":
        return before, after + b"\n# a second pass would not add this\n"
    if condition == "existing_declared":
        return _phantom_before(kind, before.decode()).encode(), after
    if condition == "reparse":
        return before, after + b"\n  [[[ not parseable\n"
    msg = f"no violation fake for {condition}"
    raise AssertionError(msg)


def _registry() -> dict[str, list[str]]:
    payload = yaml.safe_load(INVARIANTS.read_text(encoding="utf-8"))
    return payload["merges"]


def test_the_registry_and_the_dispatch_name_the_same_kinds():
    """A kind the code offers without a declared contract -- or the reverse -- fails here."""
    assert set(_registry()) == set(CODE_KINDS), (
        "invariants.yml's merges: and the merge dispatch disagree; "
        f"registry-only: {sorted(set(_registry()) - set(CODE_KINDS))}, "
        f"code-only: {sorted(set(CODE_KINDS) - set(_registry()))}"
    )


@pytest.mark.parametrize("kind", CODE_KINDS)
@pytest.mark.parametrize("condition", sorted(CONDITIONS))
def test_each_declared_condition_holds_and_catches_its_violation(kind: str, condition: str, tmp_path: Path):
    """Hold on a benign merge; fail on a faked violation of the checker's own inputs.

    A checker that cannot see its own violation is decoration, so the second
    half fakes the violation against the (before, after) pair rather than
    trusting the merge to misbehave on cue.
    """
    if condition not in _registry().get(kind, []):
        pytest.skip(f"{kind} does not declare {condition}")
    checker = CONDITIONS[condition]
    runner, (target_text, source_text) = SAMPLES[kind]
    target = tmp_path / "target"
    target.write_text(target_text, encoding="utf-8")
    source = tmp_path / "source"
    source.write_text(source_text, encoding="utf-8")

    result = runner(target, source, True)
    assert result.applied, f"{kind}: the sample merge did not apply, so it proves nothing: {result.notes}"
    before, after = target_text.encode(), target.read_bytes()
    checker(kind, before, after, target)

    fake_before, fake_after = _violation(kind, condition, before, after)
    with pytest.raises(AssertionError, match=kind.split("_", maxsplit=1)[0]):
        checker(kind, fake_before, fake_after, target)


def test_the_registry_promises_no_condition_no_checker_implements():
    """A declared condition without an implementation is a promise nobody keeps."""
    unknown = {
        kind: [name for name in conditions if name not in CONDITIONS]
        for kind, conditions in _registry().items()
        if any(name not in CONDITIONS for name in conditions)
    }
    assert not unknown, f"invariants.yml promises conditions no checker implements: {unknown}"
