#!/usr/bin/env python3
"""The update rehearsal: replay `copier update` for every witness leaf, nightly.

A user's project moves forward with `copier update`, which renders the
template at the project's recorded revision and at the target revision and
merges the difference into their tree. That path is where template edits
actually bite: an edit that renders fine can still produce conflict markers,
a whitespace mess, or a stale recorded revision when replayed over an
existing project. tests/test_update_path.py verifies the merge for a
hand-picked matrix; this tool rehearses it for **every witness leaf**, so a
release ships knowing update was exercised for each configuration it claims.

Per leaf, the rehearsal replays a user's lifecycle: render at the released
ref, commit the result (`copier copy` leaves a project with one commit),
then `copier update` to the target ref, and checks what
tests/test_update_path.py established as the contract -- (a) no conflict
residue, (b) `git diff --check` clean, (c) the recorded `_commit` advanced.

Scope: the merge mechanics. A user-*modified* project is a different
universe (copier's conflict handling is the user's to resolve), and the
update's convergence to a fresh render is reported as information, not
verdict -- the known divergences (per-render stamps) are normalized first,
and what remains is a map of what update does differently, kept for study.

Usage:
    python tools/update_rehearsal.py                          # all leaves, release tag -> HEAD
    python tools/update_rehearsal.py --only oj=ctf --jobs 8   # one axis, 8 workers
    python tools/update_rehearsal.py --json                   # machine report on pure stdout

Exits 0 when every rehearsed leaf passes, 1 when any fails, 2 on usage
errors. Prose goes to stderr so `--json` stays pure.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import copier
import yaml

TOP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOP))

from tools.check_questionnaire_diff import release_tag  # noqa: E402

CACHE = TOP / ".cache" / "update-rehearsal"
WITNESSES = TOP / "tests" / "matrix" / "witnesses.jsonl"


@dataclass(frozen=True)
class LeafVerdict:
    """One leaf's rehearsal: which checks ran and what they saw."""

    leaf_id: str
    ok: bool
    failed: list[str]
    convergence: list[str]  # update-vs-fresh-render divergences (informational)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # argv built by this module from literals and paths; no shell involved.
    return subprocess.run(  # noqa: S603  WHYNOT: fixed git argv of our own checkout, like tests/test_update_path.py.
        ["git", "-C", str(repo), *args],  # noqa: S607  WHYNOT: same.
        capture_output=True,
        text=True,
        check=False,  # the callers assert on the verdict; a failed lookup is a message, not a crash
    )


def _git_out(repo: Path, *args: str) -> str:
    result = _git(repo, *args)
    assert result.returncode == 0, f"git {' '.join(args)} failed in {repo}:\n{result.stdout}{result.stderr}"
    return result.stdout


def _read_leaves() -> dict[str, dict[str, Any]]:
    leaves: dict[str, dict[str, Any]] = {}
    for line in WITNESSES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        leaves[record["id"]] = record.get("answers", {})
    return leaves


def _answers(project: Path) -> dict[str, Any]:
    return yaml.safe_load((project / ".copier-answers.yml").read_text(encoding="utf-8"))


def _conflict_residue(project: Path) -> list[str]:
    """Files copier left conflict markers or `.rej` hunks in."""
    residue: list[str] = []
    for path in project.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(project).as_posix()
        if path.suffix == ".rej":
            residue.append(relative)
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue  # a binary artifact cannot carry an inline conflict
        if any(line.startswith(("<<<<<<< ", ">>>>>>> ", "||||||| ")) for line in text.splitlines()):
            residue.append(relative)
    return residue


def _manifest(project: Path) -> dict[str, str]:
    """{relpath: sha256} with the answers file's per-render stamps removed."""
    manifest: dict[str, str] = {}
    for path in sorted(project.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        rel = path.relative_to(project).as_posix()
        data = path.read_bytes()
        if rel == ".copier-answers.yml":
            parsed = yaml.safe_load(data.decode("utf-8")) or {}
            for key in ("_commit", "_src_path"):
                parsed.pop(key, None)
            data = json.dumps(parsed, sort_keys=True).encode("utf-8")
        manifest[rel] = _sha(data)
    return manifest


class ReleasedRenders:
    """One render of the released ref per leaf, cached and copied out per run.

    The render is produced once and copied into each rehearsal's workspace:
    the rehearsal git-inits and commits the copy, so the original must never
    be touched. The cache key is everything the tree depends on -- the base
    commit, the answers, the copier version that produced it, and the
    checkout (a render's `.copier-answers.yml` records the absolute template
    path `copier update` clones, so renders must never cross checkouts).
    A completion marker sits outside the tree so a crashed render is never
    served as a hit, and an flock keeps parallel workers from rendering the
    same leaf twice.
    """

    def __init__(self, base_ref: str, base_rev: str, copier_version: str) -> None:
        self.base_ref = base_ref
        self._rev = base_rev
        self._copier_version = copier_version
        self.root = CACHE / "rendered" / base_rev
        self.root.mkdir(parents=True, exist_ok=True)
        self.renders = 0
        self.reuses = 0

    def _key(self, leaf_id: str, answers: dict[str, Any]) -> str:
        payload = json.dumps([str(TOP), self._rev, self._copier_version, leaf_id, sorted(answers.items())], default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    def render(self, leaf_id: str, answers: dict[str, Any], dst: Path) -> None:
        key = self._key(leaf_id, answers)
        rendered = self.root / key
        complete = self.root / f"{key}.done"
        lock_path = self.root / f"{key}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            hit = complete.exists()
            if not hit:
                shutil.rmtree(rendered, ignore_errors=True)
                copier.run_copy(
                    src_path=str(TOP),
                    dst_path=rendered,
                    data=dict(answers),
                    vcs_ref=self.base_ref,
                    defaults=True,
                    unsafe=True,
                    overwrite=True,
                    skip_tasks=True,  # the merge is what is rehearsed; tasks need no rehearsal here
                )
                complete.touch()
        if hit:
            self.reuses += 1
        else:
            self.renders += 1
        shutil.copytree(rendered, dst, symlinks=True, dirs_exist_ok=True)


@dataclass(frozen=True)
class _Job:
    """One rehearsal unit: plain data, so a process pool can carry it."""

    leaf_id: str
    answers: dict[str, Any]
    base_ref: str
    base_rev: str
    target_rev: str
    target_dirty: bool
    fresh: bool


def _rehearse_job(job: _Job) -> LeafVerdict:
    """Module-level entry for the process pool (closures do not pickle)."""
    work = Path(tempfile.mkdtemp(prefix=f"rehearsal-{job.leaf_id.replace('/', '__')}-"))
    try:
        return rehearse_leaf(
            job.leaf_id,
            job.answers,
            base_rev=job.base_rev,
            target_rev=job.target_rev,
            target_dirty=job.target_dirty,
            renders=ReleasedRenders(job.base_ref, job.base_rev, copier.__version__),
            fresh_render_available=job.fresh,
            work=work,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def rehearse_leaf(  # noqa: PLR0913 C901  WHYNOT: the arguments are the replay's own coordinates and each branch is one soundness rule; a bag object would hide the union.
    leaf_id: str,
    answers: dict[str, Any],
    *,
    base_rev: str,
    target_rev: str,
    target_dirty: bool,
    renders: ReleasedRenders,
    fresh_render_available: bool,
    work: Path,
) -> LeafVerdict:
    """Replay a user's lifecycle for one leaf and return the verdict."""
    project = work / "project"
    project.mkdir(parents=True)
    renders.render(leaf_id, answers, project)
    recorded = _answers(project).get("_commit", "")

    # The state a user's repo is in after `copier copy`: one commit.
    _git_out(project, "init", "-q", "-b", "main")
    _git_out(project, "add", "-A")
    _git_out(
        project,
        "-c",
        "user.name=rehearsal",
        "-c",
        "user.email=rehearsal@example.com",
        "commit",
        "-qm",
        f"scaffold from {base_rev}",
    )

    failed: list[str] = []
    copier.run_update(
        dst_path=project,
        vcs_ref="HEAD",
        defaults=True,
        unsafe=True,
        overwrite=True,
        skip_tasks=True,
    )

    # (a) copier's merge left no unresolved hunk behind.
    residue = _conflict_residue(project)
    if residue:
        failed.append(f"conflict residue: {residue}")

    # (b) nothing the update wrote trips git's whitespace/conflict check; the
    # update's new files are staged first or `git diff` would not see them.
    _git_out(project, "add", "-A")
    check = _git(project, "diff", "--cached", "--check")
    if check.returncode != 0 or check.stdout:
        failed.append(f"`git diff --check` flagged the update: {check.stdout}{check.stderr}")

    # (c) the answers record the revision the update rendered -- as git
    # describes it (copier records `6.0.0-127-g<sha>`, not a raw sha).
    updated = _answers(project).get("_commit", "")
    describe = _git_out(TOP, "describe", "--tags", "--always").strip()
    if not updated:
        failed.append("copier must record the template revision it rendered")
    elif target_rev != base_rev:
        if updated == recorded:
            failed.append("the update did not move off the released revision")
        if not target_dirty and updated != describe:
            failed.append(f"a clean template tree must record exactly {describe!r}, got {updated!r}")
    elif not target_dirty and updated != recorded:
        failed.append("target equals the base revision: the update should have been a no-op")

    # Informational: does the updated tree converge to a fresh render at the
    # target? Divergence is a map of what update does differently -- studied,
    # not failed. Only meaningful when a fresh render of this leaf is cached.
    convergence: list[str] = []
    if fresh_render_available:
        fresh = work / "fresh"
        fresh.parent.mkdir(parents=True, exist_ok=True)
        copier.run_copy(
            src_path=str(TOP),
            dst_path=fresh,
            data=dict(answers),
            vcs_ref="HEAD",
            defaults=True,
            unsafe=True,
            overwrite=True,
            skip_tasks=True,
        )
        before, after = _manifest(fresh), _manifest(project)
        convergence.extend(rel for rel in sorted(set(before) | set(after)) if before.get(rel) != after.get(rel))

    return LeafVerdict(leaf_id=leaf_id, ok=not failed, failed=failed, convergence=convergence)


def run(
    base_ref: str, target_ref: str, only: str | None, jobs: int, *, audit_fresh: bool
) -> tuple[int, dict[str, Any]]:
    leaves = _read_leaves()
    if only:
        leaves = {leaf_id: answers for leaf_id, answers in leaves.items() if only in leaf_id}
        if not leaves:
            msg = f"--only {only!r}: no witness leaf id contains it"
            print(msg, file=sys.stderr)
            return 2, {}

    base_rev = _git_out(TOP, "rev-parse", f"{base_ref}^{{commit}}").strip()
    target_rev = _git_out(TOP, "rev-parse", f"{target_ref}^{{commit}}").strip()
    renders = ReleasedRenders(base_ref, base_rev, copier.__version__)

    target_dirty = bool(_git_out(TOP, "status", "--porcelain").strip())
    jobs_to_run: list[_Job] = []
    jobs_to_run.extend(
        _Job(leaf_id, answers, base_ref, base_rev, target_rev, target_dirty, audit_fresh)
        for leaf_id, answers in sorted(leaves.items())
    )
    # copier's update juggles the process-wide cwd through plumbum, which is
    # why the workers are processes and not threads -- the same lesson batch.py
    # recorded when its own --jobs landed.
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        verdicts = list(pool.map(_rehearse_job, jobs_to_run))

    failures = [v for v in verdicts if not v.ok]
    convergence = {v.leaf_id: v.convergence for v in verdicts if v.convergence}
    # the pool workers each hold their own counters; the cache is the one place
    # the numbers live after a parallel run
    rendered_done = len(list((CACHE / "rendered" / base_rev).glob("*.done")))
    payload = {
        "base": base_ref,
        "base_rev": base_rev,
        "target": target_ref,
        "target_rev": target_rev,
        "rehearsed": len(verdicts),
        "failures": {v.leaf_id: v.failed for v in failures},
        "convergence": convergence,
        "renders": {"cached": rendered_done, "fresh": renders.renders, "reused": renders.reuses},
    }
    return (1 if failures else 0), payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="replay copier update for every witness leaf")
    parser.add_argument("--base", default=None, help="the ref to start from (default: the newest release tag)")
    parser.add_argument("--target", default="HEAD", help="the ref to update to (default HEAD)")
    parser.add_argument("--only", default=None, help="rehearse only leaves whose id contains this substring")
    parser.add_argument("--jobs", type=int, default=4, help="leaves rehearsed concurrently (default 4)")
    parser.add_argument(
        "--fresh", action="store_true", help="also compare each updated tree to a fresh render (informational)"
    )
    parser.add_argument("--json", action="store_true", help="machine report on pure stdout")
    args = parser.parse_args(argv)

    base_ref = args.base or release_tag(TOP) or ""
    if not base_ref:
        print(
            "no release tag in this repository: copier update has no released questionnaire to start from",
            file=sys.stderr,
        )
        return 2

    code, payload = run(base_ref, args.target, args.only, args.jobs, args.fresh)
    if args.json:
        print(json.dumps(payload, indent=1, sort_keys=True))
    else:
        print(
            f"update rehearsal: {payload['rehearsed']} leaves, {payload['base']} ({payload['base_rev'][:10]}) -> "
            f"{payload['target']} ({payload['target_rev'][:10]}), {payload['renders']['cached']} cached render(s)",
            file=sys.stderr,
        )
        for leaf_id, failed in payload["failures"].items():
            print(f"[FAIL]   {leaf_id}: {'; '.join(failed)}", file=sys.stderr)
        for leaf_id, files in payload["convergence"].items():
            print(f"[INFO]   {leaf_id}: update diverges from a fresh render in {len(files)} file(s)", file=sys.stderr)
        if not payload["failures"]:
            print(f"PROVEN: all {payload['rehearsed']} rehearsed leaves update cleanly.", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
