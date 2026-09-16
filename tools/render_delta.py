#!/usr/bin/env python3
"""The render twin: prove which witness leaves a template change can affect.

Every recent template refactor was verified the same way by hand: render a
hand-picked set of answer combinations at a baseline checkout and at the
working tree, and diff the trees. The pick is human judgement, and the
coverage is a sample. This tool mechanizes it:

**Layer A — semantic diff (cheap, conservative).** A leaf's rendered tree is
a function of its render context (every question answer and every internal
value) and of the template files copier reads for it. So the candidate set —
leaves whose render *can* have changed — is the union of: leaves whose
context hash differs, leaves whose rendered file set (plus its
include/import closure) contains a template file whose bytes differ, and —
conservatively — every leaf when the template path set or `copier.yml`
changed. A candidate is an upper bound, never a claim.

**Layer B — exact verdict (candidates only).** Each candidate leaf is
rendered from both the baseline checkout and the working tree, and the two
trees are compared by manifest: the file list plus one sha256 per file, with
`.copier-answers.yml` normalized first (its `_commit`/`_src_path` vary with
dirty-template renders — a known artifact, not content). A candidate only one
side declares — the witness list is itself a template input, so a leaf-space
change moves it — has no counterpart to compare: it is reported as added or
removed, never as a diff.

A non-candidate leaf is proven unaffected by the semantic diff; a candidate
that comes back byte-identical is proven unchanged by direct observation.
Scope: the rendered tree. Task *execution* semantics and the `copier update`
path are other checks (the witness matrix and tests/test_update_path.py).

Usage:
    python tools/render_delta.py                     # base HEAD, verdict + report
    python tools/render_delta.py --base 6.0.0        # diff against a tag
    python tools/render_delta.py --audit 5           # also re-render 5 unaffected leaves as a soundness probe
    python tools/render_delta.py --json              # machine report on pure stdout

Exits 0 when every candidate is proven identical, 1 when a leaf differs,
2 on usage errors. Prose goes to stderr so `--json` stays pure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

TOP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOP))

from copier import Worker  # noqa: E402  # pyright: ignore[reportPrivateImportUsage]  WHYNOT: copier ships no stubs.
from tools import batch  # noqa: E402

CACHE = TOP / ".cache" / "render-delta"
ANSWERS_FILE = ".copier-answers.yml"
DEFAULT_JOBS = 8

# The render-context hash definition (which entries are hashed). Bumped when
# that changes, so a cache directory written under the old definition is not
# served under the new one.
CONTEXT_HASH_SCHEME = "answers-only-v1"

# Rendered content comes from these roots; copier.yml holds the settings and
# the generation tasks, so any byte there conservatively affects every leaf.
WATCHED_DIRS = ("template", "_shared")
WATCHED_FILES = ("_tasks.jinja", "copier.yml")

INCLUDE_TAG = re.compile(r'\{%-?\s+(?:include|import)\s+"([^"]+)"')


@dataclass(frozen=True)
class State:
    """Everything a leaf's render depends on, tabulated for one template state."""

    context_hashes: dict[str, str]  # leaf id -> hash of the full render context
    file_hashes: dict[str, str]  # watched template input -> content hash
    path_set: tuple[str, ...]  # every template/ path (order-insensitive)
    leaves: frozenset[str]  # the witness leaf ids
    include_graph: dict[str, set[str]] = field(default_factory=dict)  # file -> files it pulls in
    manifests: dict[str, dict[str, str]] = field(default_factory=dict)  # leaf -> {relpath: sha256}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _template_hashes(root: Path) -> dict[str, str]:
    """Content hash of every watched template input file."""
    hashes: dict[str, str] = {}
    for directory in WATCHED_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                hashes[f"{directory}/{path.relative_to(base).as_posix()}"] = _sha(path.read_bytes())
    for name in WATCHED_FILES:
        path = root / name
        if path.is_file():
            hashes[name] = _sha(path.read_bytes())
    return hashes


def _path_set(root: Path) -> tuple[str, ...]:
    base = root / "template"
    if not base.is_dir():
        return ()
    return tuple(sorted(path.relative_to(base).as_posix() for path in base.rglob("*") if path.is_file()))


def _read_leaves(root: Path) -> dict[str, dict[str, Any]]:
    """Leaf id -> answers, from that tree's committed witness list."""
    path = root / "tests" / "matrix" / "witnesses.jsonl"
    leaves: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        leaves[record["id"]] = record.get("answers", {})
    return leaves


def _context_key(root: Path) -> str:
    """The context hash cache key: contexts change only when these change.

    ``CONTEXT_HASH_SCHEME`` is part of the key so a change to *which* entries
    are hashed invalidates every cached pass instead of mixing two hash
    definitions in one cache directory.
    """
    parts = [root / "copier.yml", root / "tests" / "matrix" / "witnesses.jsonl"]
    parts += sorted((root / "questions").glob("*.yml"))
    digest = hashlib.sha256()
    digest.update(CONTEXT_HASH_SCHEME.encode())
    digest.update(b"\0")
    for path in parts:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _context_hashes(root: Path, leaves: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Hash of copier's answer-derived render context, one pass per leaf, cached by question state.

    Only the context's public entries are hashed -- the answers and the
    internals copier derived from them. Its underscore-prefixed entries
    (``_src_path``, ``_commit``, ``_copier_conf``, ``_copier_answers``,
    ``_folder_name``) name the run's own paths, revision and objects, so they
    differ between the baseline worktree and the working tree for reasons that
    are not the template's content: hashing them makes every leaf a candidate
    whenever the two sides do not share one cache entry (measured 2026-09-16:
    a leaf-space change -- the witness list is itself an input -- made all 228
    leaves candidates and the semantic diff stopped narrowing). What is left
    is exactly what the cache key already promises: template body edits never
    change the context, and the pass runs only when the questionnaire, the
    witness list or the leaf answers moved.
    """
    cache_dir = CACHE / "contexts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{_context_key(root)}.json"
    if cache_path.is_file():
        return {leaf_id: str(h) for leaf_id, h in json.loads(cache_path.read_text(encoding="utf-8")).items()}

    hashes: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as dst:
        worker = Worker(src_path=str(root), dst_path=Path(dst), defaults=True, quiet=True, vcs_ref="HEAD")
        for leaf_id in sorted(leaves):
            worker.data = dict(leaves[leaf_id])
            worker._ask()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  WHYNOT: copier's own questionnaire pass is the oracle (tests/test_when_model.py precedent).
            context = worker._render_context()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  WHYNOT: same.
            answers_only = {key: value for key, value in context.items() if not key.startswith("_")}
            serialized = json.dumps(answers_only, sort_keys=True, default=repr)
            hashes[leaf_id] = _sha(serialized.encode())
    cache_path.write_text(json.dumps(hashes, indent=1, sort_keys=True), encoding="utf-8")
    return hashes


def _include_graph(root: Path) -> dict[str, set[str]]:
    """template-side file -> the files it pulls in via literal include/import tags."""
    graph: dict[str, set[str]] = {}
    for rel in _template_hashes(root):
        if not rel.endswith((".jinja", ".yml")):
            continue
        path = root / rel
        if not path.is_file():
            continue
        for match in INCLUDE_TAG.finditer(path.read_text(encoding="utf-8")):
            graph.setdefault(rel, set()).add(match.group(1))
    return graph


def load_manifests(state: State) -> dict[str, dict[str, str]]:
    """The stored manifests for this state's content address, or {} on a first visit."""
    path = CACHE / "manifests" / f"{state_hash(state)}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifests(state: State, manifests: dict[str, dict[str, str]]) -> None:
    directory = CACHE / "manifests"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{state_hash(state)}.json"
    path.write_text(json.dumps(manifests, indent=1, sort_keys=True), encoding="utf-8")


def build_state(root: Path) -> State:
    """Tabulate one template state: context hashes, input hashes, paths, leaves."""
    state = State(
        context_hashes=_context_hashes(root, _read_leaves(root)),
        file_hashes=_template_hashes(root),
        path_set=_path_set(root),
        leaves=frozenset(_read_leaves(root)),
        include_graph=_include_graph(root),
    )
    manifests = load_manifests(state)
    return replace(state, manifests=manifests)


def state_hash(state: State) -> str:
    """A content address for the state: input hashes and leaf ids, nothing else."""
    digest = hashlib.sha256()
    digest.update(json.dumps(sorted(state.file_hashes.items()), sort_keys=True).encode())
    digest.update(json.dumps(sorted(state.path_set)).encode())
    digest.update(json.dumps(sorted(state.leaves)).encode())
    return digest.hexdigest()[:16]


def _output_name(template_rel: str) -> str:
    """The destination name a template path renders to, tags and `.jinja` stripped.

    `{{ pkg_dir }}`-style interpolations strip out too, so the comparison to
    manifest keys is by suffix: over-inclusive on name collisions, which is
    the safe direction for a candidacy rule.
    """
    stripped = re.sub(r"{%.*?%}|{{.*?}}|{#.*?#}", "", template_rel)
    return stripped.removesuffix(".jinja") if stripped.endswith(".jinja") else stripped


def _reverse_closure(changed: set[str], graph: dict[str, set[str]]) -> set[str]:
    """`changed` plus every file that (transitively) includes a changed file."""
    reverse: dict[str, set[str]] = {}
    for source, targets in graph.items():
        for target in targets:
            reverse.setdefault(target, set()).add(source)
    reach = set(changed)
    frontier = list(changed)
    while frontier:
        current = frontier.pop()
        for parent in reverse.get(current, ()):
            if parent not in reach:
                reach.add(parent)
                frontier.append(parent)
    return reach


def compute_candidates(old: State, new: State) -> tuple[frozenset[str], dict[str, Any]]:  # noqa: C901 PLR0912  WHYNOT: each branch is one soundness rule of the four-way union; splitting would hide the union.
    """The candidate set (an upper bound on affected leaves) and the semantic report.

    Soundness: the four ways a rendered tree can change -- a condition outcome,
    a value, a file's content, the file set -- are each an inclusion rule here,
    and every rule errs toward inclusion. A leaf outside the candidate set has
    an identical context, and none of the changed template bytes are reachable
    from its rendered file set.
    """
    all_leaves = frozenset(old.leaves | new.leaves)
    changed_files = {
        path
        for path in set(old.file_hashes) | set(new.file_hashes)
        if old.file_hashes.get(path) != new.file_hashes.get(path)
    }
    copier_changed = "copier.yml" in changed_files
    path_set_changed = old.path_set != new.path_set
    reasons: dict[str, list[str]] = {leaf_id: [] for leaf_id in sorted(all_leaves)}

    if copier_changed:
        for why in reasons.values():
            why.append("copier.yml changed (settings and generation tasks are shared by every leaf)")
    if path_set_changed:
        for why in reasons.values():
            why.append("the template path set changed (files added or removed)")

    graph: dict[str, set[str]] = {}
    for source, targets in (*old.include_graph.items(), *new.include_graph.items()):
        graph.setdefault(source, set()).update(targets)
    reach = _reverse_closure({rel for rel in changed_files if rel != "copier.yml"}, graph)
    reach_outputs = {_output_name(rel) for rel in reach}

    for leaf_id, why in sorted(reasons.items()):
        if old.context_hashes.get(leaf_id) != new.context_hashes.get(leaf_id):
            why.append("the render context changed (an answer, an internal, or its derivation)")
        rendered = old.manifests.get(leaf_id)
        if rendered is None:
            # no recorded render for this leaf: there is no evidence its output
            # survived the change, so it renders (the first run of a new state
            # is therefore total, and every later state inherits full manifests)
            if changed_files:
                why.append("no render manifest: every changed byte could reach this leaf")
            continue
        touched = sorted(set(rendered) & reach_outputs)
        if touched:
            why.append(f"changed template bytes reach its rendered files: {', '.join(touched[:4])}")

    candidates = frozenset(leaf_id for leaf_id, why in reasons.items() if why)
    report = {
        "candidates": len(candidates),
        "leaves": len(all_leaves),
        "changed_files": sorted(changed_files),
        "copier_changed": copier_changed,
        "path_set_changed": path_set_changed,
        "reasons": {k: v for k, v in reasons.items() if v},
    }
    return candidates, report


def _normalize(data: bytes, rel: str) -> bytes:
    """File bytes, with the answers file's per-render stamps removed."""
    if Path(rel).name != ANSWERS_FILE:
        return data
    parsed = yaml.safe_load(data.decode("utf-8")) or {}
    for key in ("_commit", "_src_path"):
        parsed.pop(key, None)
    return json.dumps(parsed, sort_keys=True).encode("utf-8")


def _manifest(dest: Path) -> dict[str, str]:
    return {
        path.relative_to(dest).as_posix(): _sha(_normalize(path.read_bytes(), path.relative_to(dest).as_posix()))
        for path in sorted(dest.rglob("*"))
        if path.is_file()
    }


def _baseline_checkout(base_ref: str) -> Path:
    """A disposable checkout of `base_ref`, for rendering the before-side."""
    path = Path(tempfile.mkdtemp(prefix="render-delta-base-"))
    subprocess.run(  # noqa: S603  WHYNOT: fixed git invocation of our own checkout; no shell, no untrusted input.
        ["git", "worktree", "add", "--detach", "--force", str(path), base_ref],  # noqa: S607  WHYNOT: same.
        cwd=TOP,
        check=True,
        capture_output=True,
    )
    return path


def _render_side(
    repo: Path, leaf_ids: list[str], leaves: dict[str, dict[str, Any]], work: Path, jobs: int
) -> dict[str, dict[str, str]]:
    """Render the leaves `repo` declares, returning a manifest per leaf.

    Ids `repo` does not declare are skipped: a baseline checkout cannot render
    a leaf the working tree added, nor the working tree one the baseline never
    had (the witness list is itself a template input, tools/z3_witnesses.py).
    `verify` names those ids as added / removed instead of diffing them.
    """
    renderable = [leaf_id for leaf_id in leaf_ids if leaf_id in leaves]
    # flat dests: leaf ids contain "/", and batch refuses nested work dirs
    lines = [
        json.dumps({"id": leaf_id, "dest": leaf_id.replace("/", "__"), "answers": leaves[leaf_id], "src": str(repo)})
        for leaf_id in renderable
    ]
    if not lines:
        return {}
    jsonl = work / "requests.jsonl"
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    requests = batch.load_requests([jsonl])
    with batch.report_stream_only():
        results = batch.run_requests(requests, work / "renders", repo, jobs=jobs)
    return {result.id: _manifest(Path(result.dest)) for result in results}


def _classify(
    render_list: list[str],
    old_leaves: dict[str, dict[str, Any]],
    new_leaves: dict[str, dict[str, Any]],
    old_manifests: dict[str, dict[str, str]],
    new_manifests: dict[str, dict[str, str]],
) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """Split the re-rendered leaves into diff failures, additions and removals.

    The verdict is about renders that *changed*, so a leaf only one side
    declares is never a failure: an added leaf has no baseline render to
    differ from, and a removed leaf has no working-tree render left to compare.
    Both are reported by name; only the leaves both sides declare are compared
    by manifest.
    """
    added = [leaf_id for leaf_id in render_list if leaf_id in new_leaves and leaf_id not in old_leaves]
    removed = [leaf_id for leaf_id in render_list if leaf_id in old_leaves and leaf_id not in new_leaves]
    uncomparable = {*added, *removed}
    failures: dict[str, list[str]] = {}
    for leaf_id in render_list:
        if leaf_id in uncomparable:
            continue
        before = old_manifests.get(leaf_id, {})
        after = new_manifests.get(leaf_id, {})
        diff = sorted(
            {f for f in before if f not in after}
            | {f for f in after if f not in before}
            | {f for f in set(before) & set(after) if before[f] != after[f]}
        )
        if diff:
            failures[leaf_id] = diff
    return failures, added, removed


def verify(base_ref: str = "HEAD", jobs: int = DEFAULT_JOBS, audit: int = 0) -> tuple[int, dict[str, Any]]:
    """The whole pipeline: tables, diff, candidate renders, verdict."""
    base_checkout = _baseline_checkout(base_ref)
    try:
        old_state = build_state(base_checkout)
        new_state = build_state(TOP)
        candidates, report = compute_candidates(old_state, new_state)
        # leaves the two sides do not share cannot be compared by table; render them
        candidates = frozenset(candidates | (frozenset(old_state.leaves) ^ frozenset(new_state.leaves)))

        base_leaves = _read_leaves(base_checkout)
        new_leaves = _read_leaves(TOP)
        render_list = sorted(candidates)
        work = Path(tempfile.mkdtemp(prefix="render-delta-work-"))
        old_manifests = _render_side(base_checkout, render_list, base_leaves, work / "old", jobs)
        new_manifests = _render_side(TOP, render_list, new_leaves, work / "new", jobs)

        failures, added, removed = _classify(render_list, base_leaves, new_leaves, old_manifests, new_manifests)

        # a non-candidate is proven identical, so it inherits its old manifest:
        # the next diff against this state has the full per-leaf picture again.
        carried = {leaf_id: old_state.manifests.get(leaf_id, {}) for leaf_id in new_state.leaves - candidates}
        save_manifests(new_state, {**new_manifests, **carried})

        audited = 0
        audit_failures: dict[str, list[str]] = {}
        unaffected = sorted(frozenset(new_state.leaves) - candidates)
        if audit and unaffected:
            rng = random.Random(20260914)  # noqa: S311  WHYNOT: picks which leaf to re-probe, not a secret.
            probe = rng.sample(unaffected, min(audit, len(unaffected)))
            old_probe = _render_side(base_checkout, probe, base_leaves, work / "audit-old", jobs)
            new_probe = _render_side(TOP, probe, new_leaves, work / "audit-new", jobs)
            audited = len(probe)
            for leaf_id in probe:
                if old_probe.get(leaf_id) != new_probe.get(leaf_id):
                    audit_failures[leaf_id] = ["an unaffected leaf changed: Layer A missed a flow"]

        payload = {
            "base": base_ref,
            "leaves": len(new_state.leaves),
            "candidates": len(candidates),
            "proven": len(new_state.leaves) - len(failures),
            "failures": failures,
            "added": added,
            "removed": removed,
            "audit": {"requested": audit, "rendered": audited, "failures": audit_failures},
            "semantic_diff": {k: v for k, v in report.items() if k != "reasons"},
        }
        code = 1 if failures or audit_failures else 0
        return code, payload
    finally:
        subprocess.run(  # noqa: S603  WHYNOT: the same fixed git invocation; a failed cleanup leaves a stray worktree, never a wrong verdict.
            ["git", "worktree", "remove", "--force", str(base_checkout)],  # noqa: S607  WHYNOT: same.
            cwd=TOP,
            capture_output=True,
            check=False,
        )
        shutil.rmtree(base_checkout, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="prove which witness leaves a template change can affect")
    parser.add_argument("--base", default="HEAD", help="the ref the working tree is diffed against (default HEAD)")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="parallel renders for the candidate leaves")
    parser.add_argument("--audit", type=int, default=0, help="re-render N unaffected leaves as a soundness probe")
    parser.add_argument("--json", action="store_true", help="machine report on pure stdout")
    args = parser.parse_args(argv)

    code, payload = verify(args.base, args.jobs, args.audit)
    if args.json:
        print(json.dumps(payload, indent=1, sort_keys=True))
    else:
        print(
            f"render twin: {payload['leaves']} leaves, {payload['candidates']} candidate(s) "
            f"re-rendered against {payload['base']}, audit {payload['audit']['rendered']}",
            file=sys.stderr,
        )
        for leaf_id, files in payload["failures"].items():
            print(f"[DIFF]   {leaf_id}: {', '.join(files)}", file=sys.stderr)
        for leaf_id in payload["added"]:
            print(f"[ADDED]  {leaf_id}: {payload['base']} declares no such leaf", file=sys.stderr)
        for leaf_id in payload["removed"]:
            print(f"[GONE]   {leaf_id}: the working tree dropped it", file=sys.stderr)
        for leaf_id, files in payload["audit"]["failures"].items():
            print(f"[AUDIT]  {leaf_id}: {', '.join(files)}", file=sys.stderr)
        if code == 0:
            compared = payload["candidates"] - len(payload["added"]) - len(payload["removed"])
            moved = ""
            if payload["added"] or payload["removed"]:
                moved = f" ({len(payload['added'])} added, {len(payload['removed'])} removed, no baseline to compare)"
            print(
                f"PROVEN render-identical: {compared} candidate(s) re-rendered byte-identical, "
                f"{payload['leaves'] - payload['candidates']} unaffected by the semantic diff{moved}.",
                file=sys.stderr,
            )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
