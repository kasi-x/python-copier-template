"""Session-wide cache of copier renders, for this repo's own test suite.

test_generated_lint.py and test_pyproject_fmt.py need the same (answers,
template) combinations over and over (each of test_generated_lint's four
parametrized tiers re-renders every path), and a copier render dominates a
case (~1.3s of ~1.7s: copier clones the template, evaluates every .jinja
source, then renames it). The cache renders each combination once per session
and copies that tree into the requesting test's tmp_path, so every assertion
still sees its own, byte-identical render -- the repeats are what go away.

This deliberately does not live in conftest.py: the template renders the
repo's conftest.py into every generated project (the
``template/.../tests/conftest.py`` symlink points at it and copier resolves
it), and a generated project has neither copier nor fcntl to import.
"""

import fcntl
import hashlib
import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from copier import run_copy

TOP = Path(__file__).absolute().parent.parent

# Render inputs: the jinja sources and shared partials, plus copier.yml (the
# questions, defaults and _exclude patterns that decide what an answer set
# produces). Copier includes a *dirty* working tree's content in the render
# (it emits DirtyLocalWarning when it does), so hashing the bytes on disk --
# not a git revision -- is what makes a dirty tree invalidate the cache.
_TEMPLATE_GLOBS = ("template/**", "_shared/**")
_TEMPLATE_FILES = ("copier.yml", "_tasks.jinja")


def _template_fingerprint() -> str:
    """sha256 over every render input as sorted relative path + content hash."""
    paths = [path for pattern in _TEMPLATE_GLOBS for path in TOP.glob(pattern) if path.is_file()]
    paths += [TOP / name for name in _TEMPLATE_FILES if (TOP / name).is_file()]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(TOP).as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _current_test_module() -> str:
    """The module the running test belongs to (pytest's own env var)."""
    return os.environ.get("PYTEST_CURRENT_TEST", "").split("::")[0] or "<unknown>"


def _shared_cache_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The one cache directory every process of this session agrees on.

    pytest hands each xdist worker its own basetemp (``<controller>/popen-gwN``
    under the usual ``-n auto``), so the shared renders live in its parent:
    without that, every worker would re-render combinations its peers already
    rendered.
    """
    base = tmp_path_factory.getbasetemp()
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker and base.name == f"popen-{worker}":
        base = base.parent
    return base / "render-cache"


class RenderCache:
    """One render per (answers, template fingerprint), copied per consumer."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._fingerprint = _template_fingerprint()
        self.renders = 0
        self.reuses = 0
        self._consumer_counts: dict[str, tuple[int, int]] = {}

    def _key(self, data: dict[str, object]) -> str:
        # Sorted and JSON-encoded so dict ordering can't twin a key and a
        # bool can't collide with the string "True".
        payload = json.dumps([sorted(data.items()), self._fingerprint], default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    def render(self, dst: Path, data: dict[str, object]) -> Path:
        """Copy the render of ``data`` into ``dst``, rendering it at most once."""
        key = self._key(data)
        rendered = self.root / key
        # The completion marker sits *outside* the rendered tree: a crashed
        # run's half-written tree must not be served as a cache hit, and an
        # extra file inside the tree would show up in the consumers' renders.
        complete = self.root / f"{key}.done"
        with (self.root / f"{key}.lock").open("w") as lock:
            # xdist runs the tests in separate processes; the lock is what
            # keeps them from rendering the same combination concurrently.
            fcntl.flock(lock, fcntl.LOCK_EX)
            hit = complete.exists()
            if not hit:
                shutil.rmtree(rendered, ignore_errors=True)
                run_copy(
                    src_path=str(TOP),
                    dst_path=rendered,
                    data=dict(data),
                    vcs_ref="HEAD",
                    defaults=True,
                    unsafe=True,
                    overwrite=True,
                    skip_tasks=True,
                )
                complete.touch()
        self._count(_current_test_module(), hit=hit)
        # Outside the lock: the marker guarantees `rendered` is complete and
        # nothing writes it again, so consumers only ever read it.
        shutil.copytree(rendered, dst, symlinks=True, dirs_exist_ok=True)
        return dst

    def _count(self, consumer: str, *, hit: bool) -> None:
        """Track session-wide renders/reuses and per consumer, for the summary."""
        renders, reuses = self._consumer_counts.get(consumer, (0, 0))
        if hit:
            self._consumer_counts[consumer] = (renders, reuses + 1)
            self.reuses += 1
        else:
            self._consumer_counts[consumer] = (renders + 1, reuses)
            self.renders += 1

    def summary(self) -> list[str]:
        """Per-consumer render/reuse counts, for the terminal summary."""
        lines = [f"render cache: {self.renders} renders, {self.reuses} reuses"]
        lines += [
            f"  {consumer}: {renders} renders, {reuses} reuses"
            for consumer, (renders, reuses) in sorted(self._consumer_counts.items())
        ]
        return lines


@pytest.fixture(scope="session")
def render_cache(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RenderCache]:
    """Session-shared render cache; see RenderCache for keys and semantics."""
    cache = RenderCache(_shared_cache_root(tmp_path_factory))
    yield cache
    # Counters for the report: `-s` shows this line, while a parallel run's
    # counts come from the cache directory itself (one <key>.done per render --
    # xdist hides worker output, terminal-summary hooks included).
    print("\n".join(cache.summary()))
