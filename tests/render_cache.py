"""Persistent cache of copier renders, for this repo's own test suite.

test_generated_lint.py, test_pyproject_fmt.py, test_workflow_security.py and
test_witness_matrix.py need the same (answers, template) combinations over and
over (each of test_generated_lint's four parametrized tiers re-renders every
path), and a copier render dominates a case (~1.3s of ~1.7s: copier clones the
template, evaluates every .jinja source, then renames it). The cache renders
each combination once and copies that tree into the requesting test's
tmp_path, so every assertion still sees its own, byte-identical render -- the
repeats are what go away.

The cache lives in the repo's own, already-gitignored ``.cache/renders/``
(``.gitignore:42``) instead of pytest's basetemp, which every run throws away:
"render once per combination" was really "once per *session*", so each run paid
for the same renders again. Layout::

    .cache/renders/
      .lock                  # root lock: renders and copies share it,
                             # eviction takes it exclusively
      <fingerprint>/         # one namespace per tree state -- the eviction unit
        <key>/               # a rendered tree, copied per consumer
        <key>.done           # completion marker: never serve a half-written tree
        <key>.lock           # per-key render mutex

``<key>`` hashes the answers together with the fingerprint of the render
inputs, so an entry in another namespace can never be a hit: after any edit
under ``template/``, ``_shared/``, ``copier.yml`` or ``_tasks.jinja`` the old
entries are dead weight. That is the eviction rule, too -- opening the cache
keeps the two most recently used namespaces and deletes the rest, recency
being the namespace's mtime, refreshed by every session that opens it. Two and
not one, because the state you just left is exactly the one an
``edit, test, revert, test`` loop comes back to; the directory stays bounded at
~2 x the render combinations this suite can ask for.

Nothing deletes a namespace while a peer is using it: renders and copies hold
the root lock shared, eviction takes it exclusively and gives up on the first
try (``LOCK_NB``). Housekeeping must never block or fail a test run, so a busy
cache simply defers eviction to the next quiet session.

A missing ``.cache/renders/`` is created on first use. A *read-only* one
(``.cache`` owned by another user, or the checkout mounted read-only) cannot be
written at all, so the cache falls back to a private temporary directory for
that session and says so in its summary, rather than failing the suite. Foreign
leftovers -- a directory under the root not named like a fingerprint, or a
stray file -- are not this module's business and are left alone. An entry
inside a live namespace with no ``<key>.done`` marker is a half-written tree
from a killed run: it is re-rendered under its own lock, never served.

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
import sys
import tempfile
import warnings
from collections.abc import Generator
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from copier import run_copy

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_batch.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools.render_inputs import render_fingerprint  # noqa: E402

CACHE_ROOT = TOP / ".cache" / "renders"

# Fingerprint namespaces kept by the eviction rule (see the module docstring).
_KEEP_NAMESPACES = 2


def _template_fingerprint() -> str:
    """The shared render-input digest (`tools/render_inputs.py`)."""
    return render_fingerprint(TOP)[0]


def _is_namespace(name: str) -> bool:
    """True for a directory named after a fingerprint, i.e. one of ours."""
    return len(name) == 64 and all(char in "0123456789abcdef" for char in name)


def _current_test_module() -> str:
    """The module the running test belongs to (pytest's own env var)."""
    return os.environ.get("PYTEST_CURRENT_TEST", "").split("::")[0] or "<unknown>"


def _worker_label() -> str:
    """Who is reporting: xdist's worker name, or this process."""
    return os.environ.get("PYTEST_XDIST_WORKER") or f"pid{os.getpid()}"


class RenderCache:
    """One render per (answers, template fingerprint), copied per consumer."""

    def __init__(self, root: Path) -> None:
        # Hashed once per session -- one session holds one RenderCache, and
        # render() only ever reads this -- so the tree is walked once per
        # session, never once per render.
        self.fingerprint = _template_fingerprint()
        self.root = root
        self.ephemeral = False
        try:
            self._open()
        except OSError:
            # The cache must never be the reason a run fails: fall back to a
            # root this session can write (see the module docstring).
            self.root = Path(tempfile.mkdtemp(prefix="render-cache-"))
            self.ephemeral = True
            self._open()
        self.renders = 0
        self.reuses = 0
        self._consumer_counts: dict[str, tuple[int, int]] = {}

    @property
    def namespace(self) -> Path:
        """This session's fingerprint namespace."""
        return self.root / self.fingerprint

    def _open(self) -> None:
        """Create (and refresh) this session's namespace, then evict old ones."""
        self.root.mkdir(parents=True, exist_ok=True)
        # Probe for writability here: an existing namespace would let its own
        # mkdir succeed on a read-only root, and the first render -- not the
        # constructor -- would then be what fails.
        probe = self.root / f".write-probe-{os.getpid()}"
        probe.touch()
        probe.unlink()
        namespace = self.namespace
        namespace.mkdir(exist_ok=True)
        # Recency for the eviction rule below: the namespace in use is newest.
        os.utime(namespace)
        self._evict()

    def _evict(self) -> None:
        """Keep the newest ``_KEEP_NAMESPACES`` namespaces, drop the rest.

        The namespace just opened is the newest, so this keeps it plus
        ``_KEEP_NAMESPACES - 1`` of the others.
        """
        others = [
            entry
            for entry in self.root.iterdir()
            if entry != self.namespace and entry.is_dir() and _is_namespace(entry.name)
        ]
        others.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
        victims = others[_KEEP_NAMESPACES - 1 :]
        if not victims:
            return
        with self._root_lock(fcntl.LOCK_EX | fcntl.LOCK_NB) as held:
            if not held:
                return
            for victim in victims:
                shutil.rmtree(victim, ignore_errors=True)

    @contextmanager
    def _root_lock(self, mode: int) -> Generator[bool, None, None]:
        """Hold the root lock; yields False when a non-blocking try lost.

        ``LOCK_SH`` for a render or a copy, ``LOCK_EX | LOCK_NB`` for eviction:
        a namespace may only be deleted while no peer is reading it.
        """
        with (self.root / ".lock").open("w") as lock:
            try:
                fcntl.flock(lock, mode)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _key(self, data: dict[str, object]) -> str:
        # Sorted and JSON-encoded so dict ordering can't twin a key and a
        # bool can't collide with the string "True".
        payload = json.dumps([sorted(data.items()), self.fingerprint], default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    def render(self, dst: Path, data: dict[str, object]) -> Path:
        """Copy the render of ``data`` into ``dst``, rendering it at most once."""
        key = self._key(data)
        namespace = self.namespace
        rendered = namespace / key
        # The completion marker sits *outside* the rendered tree: a crashed
        # run's half-written tree must not be served as a cache hit, and an
        # extra file inside the tree would show up in the consumers' renders.
        complete = namespace / f"{key}.done"
        with self._root_lock(fcntl.LOCK_SH):
            # A peer's eviction may have dropped the namespace since we opened
            # it; this lock is what keeps it alive while we read from it.
            namespace.mkdir(parents=True, exist_ok=True)
            with (namespace / f"{key}.lock").open("w") as lock:
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
            # Outside the key lock: the marker guarantees `rendered` is
            # complete and nothing writes it again, so consumers only read it.
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
        lines = [f"render cache: {self.renders} renders, {self.reuses} reuses, fingerprint {self.fingerprint[:12]}"]
        if self.ephemeral:
            lines.append(f"  private root {self.root}: {CACHE_ROOT} is not writable")
        lines += [
            f"  {consumer}: {renders} renders, {reuses} reuses"
            for consumer, (renders, reuses) in sorted(self._consumer_counts.items())
        ]
        return lines


@pytest.fixture(scope="session")
def render_cache() -> Iterator[RenderCache]:
    """Session-shared render cache; see RenderCache for keys and semantics."""
    cache = RenderCache(CACHE_ROOT)
    yield cache
    # The summary leaves as a warning, not a print: xdist only forwards a
    # session fixture's stdout for failing tests, while the controller
    # aggregates every worker's warnings into the terminal's warnings summary.
    # The worker label keeps the lines distinct, so none is deduplicated away.
    # A warm cache says it in one line (per session: xdist ends a worker's
    # session at module boundaries, so a worker may report more than once);
    # the per-consumer detail is only worth its lines when something rendered.
    lines = cache.summary()
    for line in lines if cache.renders else lines[:1]:
        warnings.warn(f"[{_worker_label()}] {line}", pytest.PytestWarning, stacklevel=2)
    if cache.ephemeral:
        shutil.rmtree(cache.root, ignore_errors=True)
