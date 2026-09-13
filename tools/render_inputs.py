r"""The render inputs, and the fingerprint that identifies one tree state.

A copier render is a pure function of the answers and the template tree, so the
tree state can be named by a content digest instead of a git revision: copier
renders a *dirty* working tree as it finds it (it warns `DirtyLocalWarning`),
which is exactly what the tests and the MCP tools want to key on.

Two callers share this module so their digests cannot drift apart: the test
suite's on-disk render cache (`tests/render_cache.py`, which namespaces its
entries by this digest) and the repo MCP server's `template_fingerprint()` tool
(which reports it to an agent deciding whether the render it holds is stale).

What is covered: every file under `template/` and `_shared/`, plus `copier.yml`
and `_tasks.jinja`, as `sha256(relative path + \\0 + sha256(content))` over the
sorted paths. Symlinks are followed, because copier follows them
(`preserve_symlinks` is off): the template's payload links
(`template/.vscode -> ../.vscode`, `template/.../tests/conftest.py -> the repo's
tests/conftest.py`, ...) put the *linked* bytes into the render, so editing
either side of a link must change the digest. `Path.rglob` does not descend a
symlinked directory and a trailing `**` matches directories rather than the
files inside them, so directory links are queued explicitly; the queue is keyed
on resolved paths, so a link pointing back into a tree already walked cannot
loop.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent

RENDER_INPUT_DIRS = ("template", "_shared")
"""The trees a render expands: every file under them is a render input."""

RENDER_INPUT_FILES = ("copier.yml", "_tasks.jinja")
"""The questions, defaults, `_exclude` patterns and task list that steer it."""


def render_input_paths(root: Path = TOP) -> list[Path]:
    """Every file a render reads under `root`, sorted by relative path."""
    inputs: list[Path] = []
    walked: set[Path] = set()
    queue = [root / name for name in RENDER_INPUT_DIRS]
    while queue:
        directory = queue.pop()
        real = directory.resolve()
        if real in walked:
            continue
        walked.add(real)
        for path in directory.rglob("*"):
            if path.is_dir():
                if path.is_symlink():
                    queue.append(path)
            elif path.is_file():
                inputs.append(path)
    inputs += [root / name for name in RENDER_INPUT_FILES if (root / name).is_file()]
    return sorted(inputs)


def render_fingerprint(root: Path = TOP) -> tuple[str, int, int]:
    """`(digest, path count, total bytes)` of `root`'s render inputs.

    Sorted paths make the digest independent of directory iteration order, and
    the counts let a caller report what it hashed.
    """
    digest = hashlib.sha256()
    total = 0
    paths = render_input_paths(root)
    for path in paths:
        body = path.read_bytes()
        total += len(body)
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(body).digest())
    return digest.hexdigest(), len(paths), total
