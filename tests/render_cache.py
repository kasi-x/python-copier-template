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
instead of pytest's basetemp, which every run throws away: "render once per
combination" was really "once per *session*", so each run paid for the same
renders again. Layout::

    .cache/renders/
      .lock                       # root lock: renders and copies share it,
                                  # eviction takes it exclusively
      <namespace>/                # one namespace per questionnaire+path-set state
        <answers>/                # a rendered tree, copied per consumer
        <answers>.inputs.json     # the template files this render consumed
        <answers>.answers.json    # the render's post-questionnaire answers
                                  # (copier's resolved answer set, for the
                                  # task replay in tests/support.py)
        <answers>.done            # completion marker: never serve a half-written tree
        <answers>.lock            # per-entry render mutex

**Invalidation is per leaf, in two layers.** The namespace hashes what every
leaf shares: `copier.yml`, `questions/*.yml`, and the set of template paths,
plus the render toolchain itself (the installed `copier` and `jinja2`
versions, and a scheme tag for the digest recipe itself) -- renovate bumping
copier must not keep serving renders made by the previous version, and the
tag makes every recipe change a clean break. The entry's ``inputs.json``
records the template files that render actually consumed (its rendered
files' sources, plus their include closure) with their content hashes at
render time. A lookup re-hashes exactly those files: a hit proves every byte
the render read is unchanged. So editing one scaffold body re-renders only
the leaves that render it -- the file's *path condition* lives in its name
on disk, so a condition flip is a rename, and a rename is a namespace change
that conservatively invalidates everything.

Housekeeping: opening the cache prunes stale entries (an entry whose recorded
inputs no longer match the current files would miss anyway) and keeps the two
most recently used namespaces -- the state you just left is exactly what an
``edit, test, revert, test`` loop comes back to. Nothing deletes an entry or
namespace while a peer is using it: renders and copies hold the root lock
shared, eviction takes it exclusively and gives up on the first try
(``LOCK_NB``). Housekeeping must never block or fail a test run, so a busy
cache simply defers eviction to the next quiet session.

A missing cache is created on first use. A *read-only* one (``.cache`` owned
by another user, or the checkout mounted read-only) cannot be written at all,
so the cache falls back to a private temporary directory for that session and
says so in its summary, rather than failing the suite.

This deliberately does not live in conftest.py: the template renders the
repo's conftest.py into every generated project (the
``template/.../tests/conftest.py`` symlink points at it and copier resolves
it), and a generated project has neither copier nor fcntl to import.
"""

from __future__ import annotations

import atexit
import fcntl
import functools
import hashlib
import importlib.metadata
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
from typing import Any

import pytest
from copier import run_copy
from copier._main import Worker
from copier._user_data import DEFAULT_DATA
from copier._user_data import AnswersMap

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_batch.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools.render_inputs import include_graph  # noqa: E402
from tools.render_inputs import output_name  # noqa: E402
from tools.render_inputs import render_input_paths  # noqa: E402
from tools.render_inputs import watched_relative_paths  # noqa: E402

CACHE_ROOT = TOP / ".cache" / "renders"

# Namespaces kept by the eviction rule (see the module docstring).
_KEEP_NAMESPACES = 2

# The digest recipe's own version, hashed into every namespace: changing what
# goes into the namespace state (or how) must change the namespace itself, so
# namespaces made by an older recipe are simply evicted by the keep-2 rule.
# v3: the watched-file set (and so the recorded consumed inputs) moved to
# tools/render_inputs.py, which descends directory symlinks the old rglob
# loop skipped -- entries recorded under v2 do not carry those files, so a
# clean break re-renders them once under the complete watch.
# v4: the consumed-input matching gained the suffix rule, so pkg-tree-owned
# bodies ({{ pkg_dir }} paths) are recorded at last -- v3 entries lack them
# and would keep serving stale bot renders after a _shared body edit.
CACHE_SCHEME = "render-cache/4: pkg-tree inputs recorded"

# The render toolchain whose behaviour the cached trees encode. A bump of any
# of these changes every namespace (they are hashed into the state below).
RENDER_TOOLCHAIN = ("copier", "jinja2")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dist_version(distribution: str) -> str:
    """The installed version of one render-toolchain distribution."""
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:  # never seen in this repo; be kind to odd envs
        return "missing"


def _is_namespace(name: str) -> bool:
    """True for a directory named after a state digest, i.e. one of ours."""
    return len(name) == 64 and all(char in "0123456789abcdef" for char in name)


def _current_test_module() -> str:
    """The module the running test belongs to (pytest's own env var)."""
    return os.environ.get("PYTEST_CURRENT_TEST", "").split("::")[0] or "<unknown>"


def _worker_label() -> str:
    """Who is reporting: xdist's worker name, or this process."""
    return os.environ.get("PYTEST_XDIST_WORKER") or f"pid{os.getpid()}"


def _questionnaire_state(template_root: Path) -> str:
    """Hash of what every leaf shares: the questions, settings, path set and toolchain."""
    digest = hashlib.sha256()
    digest.update(f"scheme={CACHE_SCHEME}\0".encode())
    for distribution in RENDER_TOOLCHAIN:
        digest.update(f"{distribution}={_dist_version(distribution)}\0".encode())
    digest.update((template_root / "copier.yml").read_bytes())
    for path in sorted((template_root / "questions").glob("*.yml")):
        digest.update(b"\0")
        digest.update(path.read_bytes())
    digest.update(
        json.dumps(sorted(str(p.relative_to(template_root)) for p in render_input_paths(template_root))).encode()
    )
    return digest.hexdigest()


def _forward_closure(sources: set[str], graph: dict[str, set[str]]) -> set[str]:
    """`sources` plus every file they (transitively) include."""
    consumed = set(sources)
    frontier = list(sources)
    while frontier:
        current = frontier.pop()
        for target in graph.get(current, ()):
            if target not in consumed:
                consumed.add(target)
                frontier.append(target)
    return consumed


def _answers_payload(answers_map: AnswersMap) -> dict[str, object]:
    """The on-disk form of one questionnaire pass: `combined` answers + hidden names.

    DEFAULT_DATA (`now`, `make_secret`) and the external-data slot are
    dropped: they are live context singletons (callables, a lazy loader), and
    an AnswersMap rebuilt by `answers_map_from_payload` re-supplies them from
    copier itself, exactly as a direct run would.
    """
    combined = {
        name: value
        for name, value in dict(answers_map.combined).items()
        if name not in DEFAULT_DATA and name != "_external_data"
    }
    return {"combined": combined, "hidden": sorted(answers_map.hidden)}


def answers_map_from_payload(payload: dict[str, Any]) -> AnswersMap:
    """Rebuild a `Worker._ask` result from `stored_answers`' payload.

    The resolved answers go in as `init`, which `AnswersMap.combined` serves
    back verbatim (the same priority chain a direct run produces, minus the
    dropped live singletons, which copier re-adds); `hidden` -- the
    `when: false` internals the pass suppressed from `.copier-answers.yml` --
    is restored directly.
    """
    answers_map = AnswersMap(init=payload["combined"])
    answers_map.hidden = set(payload["hidden"])
    return answers_map


class RenderCache:
    """One render per (answers, consumed template bytes), copied per consumer."""

    def __init__(self, root: Path, template_root: Path = TOP) -> None:
        self.template_root = template_root
        # The state digest is hashed once per session -- one session holds one
        # RenderCache, and render() only ever reads this.
        self.state = _questionnaire_state(template_root)
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
        self.summary_reported = False
        self._consumer_counts: dict[str, tuple[int, int]] = {}

    @property
    def namespace(self) -> Path:
        """This session's namespace: the questionnaire and path-set state."""
        return self.root / self.state

    def _open(self) -> None:
        """Create (and refresh) this session's namespace, then housekeep."""
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
        self._housekeep()

    def _housekeep(self) -> None:
        """Prune stale entries, then keep the newest namespaces, under the root lock.

        An entry whose recorded inputs no longer match the current files would
        miss on lookup anyway -- pruning it keeps the namespace from growing
        once per edit. Housekeeping defers entirely when a peer holds the root
        lock, and must never block or fail a test run.
        """
        with self._root_lock(fcntl.LOCK_EX | fcntl.LOCK_NB) as held:
            if not held:
                return
            watched = watched_relative_paths(self.template_root)
            current = {rel: _sha((self.template_root / rel).read_bytes()) for rel in watched}
            for marker in sorted(self.namespace.glob("*.inputs.json")):
                entry = marker.name.removesuffix(".inputs.json")
                try:
                    inputs = json.loads(marker.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    inputs = None
                stale = not isinstance(inputs, dict) or any(
                    current.get(name) != digest for name, digest in inputs.items()
                )
                if stale:
                    shutil.rmtree(self.namespace / entry, ignore_errors=True)
                    (self.namespace / f"{entry}.done").unlink(missing_ok=True)
                    (self.namespace / f"{entry}.answers.json").unlink(missing_ok=True)
                    marker.unlink(missing_ok=True)
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

    def _answers_key(self, data: dict[str, object]) -> str:
        # Sorted and JSON-encoded so dict ordering can't twin a key and a
        # bool can't collide with the string "True".
        payload = json.dumps(sorted(data.items()), default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    def _consumed_inputs(self, key: str) -> dict[str, str] | None:
        """The recorded render inputs of one entry, or None when unrecorded."""
        marker = self.namespace / f"{key}.inputs.json"
        if not marker.is_file():
            return None
        try:
            return json.loads(marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _inputs_current(self, inputs: dict[str, str]) -> bool:
        """True when every recorded input file still has its recorded bytes."""
        for rel, digest in inputs.items():
            path = self.template_root / rel
            if not path.is_file() or _sha(path.read_bytes()) != digest:
                return False
        return True

    def render(self, dst: Path, data: dict[str, object]) -> Path:
        """Copy the render of ``data`` into ``dst``, rendering it at most once."""
        key = self._answers_key(data)
        namespace = self.namespace
        rendered = namespace / key
        complete = namespace / f"{key}.done"
        with self._root_lock(fcntl.LOCK_SH):
            # A peer's housekeeping may have dropped the namespace since we
            # opened it; this lock is what keeps it alive while we read.
            namespace.mkdir(parents=True, exist_ok=True)
            with (namespace / f"{key}.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                # Exactly one hit evaluation, under the key lock: on a warm
                # hit it is a full re-hash of the entry's recorded inputs, so
                # evaluating it again outside the lock would pay that twice.
                inputs = self._consumed_inputs(key)
                hit = complete.is_file() and inputs is not None and self._inputs_current(inputs)
                if not hit:
                    shutil.rmtree(rendered, ignore_errors=True)
                    worker = run_copy(
                        src_path=str(self.template_root),
                        dst_path=rendered,
                        data=dict(data),
                        vcs_ref="HEAD",
                        defaults=True,
                        unsafe=True,
                        overwrite=True,
                        skip_tasks=True,
                    )
                    self._record_inputs(key, rendered)
                    self._record_answers(key, worker)
                    complete.touch()
            self._count(_current_test_module(), hit=hit)
            # Outside the key lock: the marker guarantees `rendered` is
            # complete and nothing writes it again, so consumers only read it.
            shutil.copytree(rendered, dst, symlinks=True, dirs_exist_ok=True)
        return dst

    def _record_inputs(self, key: str, rendered: Path) -> None:
        """Record the template bytes this render consumed, as {relpath: sha256}.

        The consumed set is the rendered files' template sources (matched by
        the stripped output names -- over-inclusive on collisions, the safe
        direction) plus their transitive include/import closure. Files that no
        render consumed are deliberately absent: their edits must not
        invalidate this leaf.
        """
        graph = include_graph(self.template_root)
        outputs = {path.relative_to(rendered).as_posix() for path in rendered.rglob("*") if path.is_file()}
        # Suffix match, not exact membership: a `{{ pkg_dir }}` interpolation
        # strips out of the template path (`.../bot_discord.py`), while the
        # rendered name carries the real directory (`src/<pkg>/bot_discord.py`)
        # -- an exact `in outputs` never matches, and every pkg-tree-owned body
        # (_shared/bot-*.py.jinja, ...) would silently drop out of the recorded
        # inputs, so its edits stopped invalidating cached bot renders (found
        # while landing the gmail slice). tools/render_delta.py matches the
        # same way. Empty names (a path that strips to nothing) match nothing.
        matched = set()
        for rel in watched_relative_paths(self.template_root):
            # The `template/` prefix and the stripped interpolation leave (and
            # sometimes begin with) a `/`; normalize so the suffix rule sees
            # `bot.py`, not `/bot.py`.
            name = output_name(rel).strip("/")
            if name and any(out == name or out.endswith("/" + name) for out in outputs):
                matched.add(rel)
        consumed = _forward_closure(matched, graph)
        inputs = {
            rel: _sha((self.template_root / rel).read_bytes())
            for rel in sorted(consumed)
            if (self.template_root / rel).is_file()
        }
        (self.namespace / f"{key}.inputs.json").write_text(
            json.dumps(inputs, indent=1, sort_keys=True), encoding="utf-8"
        )

    def _record_answers(self, key: str, worker: Worker) -> None:
        """Record the render's post-questionnaire answers (see `stored_answers`)."""
        self.store_answers_key(key, _answers_payload(worker.answers))

    def store_answers(self, data: dict[str, object], answers_map: AnswersMap) -> None:
        """Persist one entry's resolved answers, keyed like the render itself.

        The complement of `stored_answers`, for a caller that resolved the
        questionnaire pass itself (tests/support.py's replay fallback).
        """
        self.store_answers_key(self._answers_key(data), _answers_payload(answers_map))

    def store_answers_key(self, key: str, payload: dict[str, object]) -> None:
        (self.namespace / f"{key}.answers.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def stored_answers(self, data: dict[str, object]) -> dict[str, Any] | None:
        """One entry's persisted post-questionnaire answers, or None.

        copier's `_tasks` render against the questionnaire pass's *resolved*
        answer set -- the `when: false` internals (`reuse_effective`, ...) and
        the defaults it filled in, which `.copier-answers.yml` deliberately
        hides -- so tests/support.py's task replay loads it from here instead
        of running the pass again (it is the expensive half of a replay). The
        answers are a pure function of (questionnaire state, input answers),
        exactly what the entry key identifies, and they ride the entry's
        lifecycle: pruned with it when its template bytes move on.
        """
        marker = self.namespace / f"{self._answers_key(data)}.answers.json"
        if not marker.is_file():
            return None
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

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
        lines = [f"render cache: {self.renders} renders, {self.reuses} reuses, state {self.state[:12]}"]
        if self.ephemeral:
            lines.append(f"  private root {self.root}: {CACHE_ROOT} is not writable")
        lines += [
            f"  {consumer}: {renders} renders, {reuses} reuses"
            for consumer, (renders, reuses) in sorted(self._consumer_counts.items())
        ]
        return lines


@functools.cache
def shared_cache() -> RenderCache:
    """The process-wide cache, shared by the fixture and tests/support.py.

    One instance per process so the render/reuse counts are one story, not
    two: tests/support.py's helpers request it directly (they are plain
    functions, not tests, and get no fixture injection), while fixture-based
    consumers keep their session-scoped entry point.
    """
    cache = RenderCache(CACHE_ROOT)
    # Support-routed runs may never request the fixture; the summary is what
    # proves the reuse on a warm run, so fall back to reporting it at exit
    # (a no-op once the fixture has reported).
    atexit.register(_finish_session)
    return cache


def _finish_session() -> None:
    """Report the summary once per process, then drop an ephemeral root."""
    cache = shared_cache()
    if cache.summary_reported:
        return
    cache.summary_reported = True
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


@pytest.fixture(scope="session")
def render_cache() -> Iterator[RenderCache]:
    """Session-shared render cache; see RenderCache for keys and semantics."""
    cache = shared_cache()
    yield cache
    _finish_session()
