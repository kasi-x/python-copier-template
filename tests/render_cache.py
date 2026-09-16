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
        <answers>.done            # completion marker: never serve a half-written tree
        <answers>.lock            # per-entry render mutex

**Invalidation is per leaf, in two layers.** The namespace hashes what every
leaf shares: `copier.yml`, `questions/*.yml`, and the set of template paths.
The entry's ``inputs.json`` records the template files that render actually
consumed (its rendered files' sources, plus their include closure) with their
content hashes at render time. A lookup re-hashes exactly those files: a hit
proves every byte the render read is unchanged. So editing one scaffold body
re-renders only the leaves that render it -- the file's *path condition*
lives in its name on disk, so a condition flip is a rename, and a rename is
a namespace change that conservatively invalidates everything.

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

import fcntl
import hashlib
import json
import os
import re
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

from tools.render_inputs import render_input_paths  # noqa: E402

CACHE_ROOT = TOP / ".cache" / "renders"

# Namespaces kept by the eviction rule (see the module docstring).
_KEEP_NAMESPACES = 2

INCLUDE_TAG = re.compile(r'\{%-?\s+(?:include|import)\s+"([^"]+)"')

WATCHED_DIRS = ("template", "_shared")
WATCHED_FILES = ("copier.yml", "_tasks.jinja")
"""The trees a render expands (tools/render_inputs.py's own list)."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    """Hash of what every leaf shares: the questions, settings and path set."""
    digest = hashlib.sha256()
    digest.update((template_root / "copier.yml").read_bytes())
    for path in sorted((template_root / "questions").glob("*.yml")):
        digest.update(b"\0")
        digest.update(path.read_bytes())
    digest.update(
        json.dumps(sorted(str(p.relative_to(template_root)) for p in render_input_paths(template_root))).encode()
    )
    return digest.hexdigest()


def _output_name(template_rel: str) -> str:
    """The destination name a template path renders to, tags and `.jinja` stripped.

    The leading `template/` directory (copier's `_subdirectory`) strips out
    too -- the same normalization tools/render_delta.py uses -- so the names
    compare to rendered output paths by suffix: over-inclusive on collisions,
    the safe direction here.
    """
    stripped = re.sub(r"{%.*?%}|{{.*?}}|{#.*?#}", "", template_rel)
    stripped = stripped.removeprefix("template/")
    return stripped.removesuffix(".jinja") if stripped.endswith(".jinja") else stripped


def _watched_relative_paths(template_root: Path) -> list[str]:
    """Every watched template input, as a path relative to `template_root`."""
    paths: list[str] = []
    for directory in WATCHED_DIRS:
        base = template_root / directory
        if base.is_dir():
            paths += [str(path.relative_to(template_root)) for path in sorted(base.rglob("*")) if path.is_file()]
    for name in WATCHED_FILES:
        if (template_root / name).is_file():
            paths.append(name)
    return paths


def _resolve_include_target(target: str, watched: set[str]) -> str | None:
    """An include tag's target, resolved against the watched files.

    Include tags are repo-root-relative ("_shared/x.jinja" from a file in
    template/), so the raw target matches a watched file only when the file
    lives at that level; the suffix fallback covers tags written relative to
    the including file. None = the target names nothing we watch.
    """
    if target in watched:
        return target
    matches = [path for path in watched if path.endswith("/" + target)]
    return matches[0] if len(matches) == 1 else None


def _include_graph(root: Path) -> dict[str, set[str]]:
    """template-side file -> the files it pulls in via literal include/import tags."""
    graph: dict[str, set[str]] = {}
    watched = set(_watched_relative_paths(root))
    for rel in _watched_relative_paths(root):
        if not rel.endswith((".jinja", ".yml")):
            continue
        text = (root / rel).read_text(encoding="utf-8")
        for match in INCLUDE_TAG.finditer(text):
            resolved = _resolve_include_target(match.group(1), watched)
            if resolved is not None:
                graph.setdefault(rel, set()).add(resolved)
    return graph


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
            watched = _watched_relative_paths(self.template_root)
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
            inputs = self._consumed_inputs(key)
            hit = complete.is_file() and inputs is not None and self._inputs_current(inputs)
            with (namespace / f"{key}.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                inputs = self._consumed_inputs(key)
                hit = complete.is_file() and inputs is not None and self._inputs_current(inputs)
                if not hit:
                    shutil.rmtree(rendered, ignore_errors=True)
                    run_copy(
                        src_path=str(self.template_root),
                        dst_path=rendered,
                        data=dict(data),
                        vcs_ref="HEAD",
                        defaults=True,
                        unsafe=True,
                        overwrite=True,
                        skip_tasks=True,
                    )
                    complete.touch()
                    self._record_inputs(key, rendered)
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
        graph = _include_graph(self.template_root)
        outputs = {path.relative_to(rendered).as_posix() for path in rendered.rglob("*") if path.is_file()}
        matched = {rel for rel in _watched_relative_paths(self.template_root) if _output_name(rel) in outputs}
        consumed = _forward_closure(matched, graph)
        inputs = {
            rel: _sha((self.template_root / rel).read_bytes())
            for rel in sorted(consumed)
            if (self.template_root / rel).is_file()
        }
        (self.namespace / f"{key}.inputs.json").write_text(
            json.dumps(inputs, indent=1, sort_keys=True), encoding="utf-8"
        )

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
