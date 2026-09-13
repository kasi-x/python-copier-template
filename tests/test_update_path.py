"""`copier update` from the released ref to the working tree.

A user's project moves forward with `copier update`, which renders the
template at the project's recorded revision and at the target revision and
merges the difference into their tree. That path only ever runs in the field
(after a release), so it is the last thing CI can break silently: a template
edit that renders fine can still produce conflict markers, a whitespace mess,
or a stale recorded revision when replayed over an existing project.

The matrix below replays exactly that: render each fixture at the newest
release tag, commit it (the state a user's repo is in after `copier copy`),
then `copier update` to HEAD and assert (a) no conflict residue, (b)
`git diff --check` is clean, and (c) the recorded `_commit` moved to the
target revision.

Refs (see notes/PLAN-improvements.md C1): `vcs_ref` is always resolved from
this local repository -- the release tag on the old side, HEAD on the new one
-- so the test is offline. `vcs_ref="HEAD"` renders the *working tree*, which
is what a reviewer's uncommitted edit would ship. That makes the assertions
weaker right now, and the released ref is the reason: `6.0.0` is the fork's
only tag and currently equals HEAD, so a clean working tree makes the update a
genuine no-op -- nothing to merge, nothing to conflict with -- and the recorded
`_commit` legitimately stays put. The moment a commit lands on top of the tag
(or the worktree is dirty), `_commit` must move off the released revision, and
these assertions tighten with it: `_commit` is then pinned to `git describe` of
the target revision rather than only compared against the old one. The matrix
grew out of the network-dependent `test_example_repo_updates`, which cloned an
external example repo for the same coverage.

The released-ref renders are cached (see ReleasedRenders), so a second run of
this module -- or the same case selected twice, or another xdist worker -- does
not pay for them again: only the merge on top of each render is repeated.

The static half of the same protection, `tools/check_questionnaire_diff.py`,
is exercised here too: it is what CI gates the update path on, and its only
output is an exit code, so a throwaway repository walks it through the breaks a
merge cannot replay and through the `_migrations` entry that clears them.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import copier
import pytest
import yaml
from copier import run_copy
from copier import run_update

from test_recommended_path import BASE
from test_recommended_path import FAST_PATHS

TOP = Path(__file__).absolute().parent.parent

if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

# The guard's ref resolution is the one W0 fixed (copier's own tag order):
# resolving it twice could disagree, so the matrix asks the guard.
from tools.check_questionnaire_diff import release_tag  # noqa: E402

# One fast-path case per single-type layout a user lands on by accepting every
# recommendation. Picked out of test_recommended_path.py's own matrix (rather
# than re-listed here) so these cannot drift from the paths that module renders.
FAST_PATH_TYPES = ("library", "web_api", "script")


def _fast_path_cases() -> list[dict[str, object]]:
    cases = [case for case in FAST_PATHS if len(case) == 1 and case.get("project_type") in FAST_PATH_TYPES]
    assert [str(case["project_type"]) for case in cases] == list(FAST_PATH_TYPES), (
        f"FAST_PATHS no longer has exactly one case per fast layout: {cases}"
    )
    return cases


EXAMPLE_ANSWERS: dict[str, Any] = yaml.safe_load((TOP / "example-answers.yml").read_text())

# (case id, answers) for the released-ref side of the matrix: the exhaustive
# answers file, plus the recommended path's three single-type layouts.
MATRIX: list[tuple[str, dict[str, Any]]] = [
    ("example-answers", EXAMPLE_ANSWERS),
    *((f"fast-{case['project_type']}", {**BASE, **case}) for case in _fast_path_cases()),
]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # argv built by this module from literals and paths; no shell involved.
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)  # noqa: S603


def _out(repo: Path, *args: str) -> str:
    result = _git(repo, *args)
    assert result.returncode == 0, f"git {' '.join(args)} failed in {repo}:\n{result.stdout}{result.stderr}"
    return result.stdout


def _answers(project: Path) -> dict[str, Any]:
    return yaml.safe_load((project / ".copier-answers.yml").read_text())


def _conflict_residue(project: Path) -> list[str]:
    """Files copier left conflict markers or `.rej` hunks in."""
    residue: list[str] = []
    for path in project.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = str(path.relative_to(project))
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


class ReleasedRenders:
    """One render of the released ref per answers set, reusable across runs.

    A render costs copier a clone plus a full jinja pass, and every case needs
    its own copy of it (the test commits it and then lets `copier update`
    rewrite it), so the render is produced once and copied out per case.

    The cache lives in the system tmp dir -- not in pytest's basetemp, which is
    per-run and would make only the *first* case of a session cheap -- so any
    worker of a session and any later run of this module reuse whatever has
    already been rendered. Renders are keyed by everything the tree depends on:
    the released commit, the answers, the copier version that produced it, and
    the checkout itself -- a render's `.copier-answers.yml` records the
    absolute template path it came from, and that is the path `copier update`
    clones, so a render must never be served to another checkout. Nothing else
    can invalidate a render: the released ref is an immutable tag and this
    module never renders HEAD as the *old* side (unlike render_cache.py, which
    fingerprints the dirty working tree it renders).
    """

    def __init__(self, root: Path, ref: str, rev: str, copier_version: str) -> None:
        self.root = root
        self.ref = ref
        self._rev = rev
        self._copier_version = copier_version
        self.root.mkdir(parents=True, exist_ok=True)
        self.renders = 0
        self.reuses = 0

    def _key(self, answers: dict[str, Any]) -> str:
        # Sorted and JSON-encoded so dict ordering cannot twin a key and a bool
        # cannot collide with the string "True".
        payload = json.dumps([str(TOP), self._rev, self._copier_version, sorted(answers.items())], default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    def render(self, dst: Path, answers: dict[str, Any]) -> None:
        """Copy the released ref's render of `answers` into `dst`."""
        key = self._key(answers)
        rendered = self.root / key
        # The completion marker sits outside the rendered tree: a crashed run's
        # half-written tree must not be served as a cache hit, and an extra
        # file inside the tree would leak into the project under test.
        complete = self.root / f"{key}.done"
        with (self.root / f"{key}.lock").open("w") as lock:
            # xdist runs the tests in separate processes; the lock is what
            # keeps two workers from rendering the same case concurrently.
            fcntl.flock(lock, fcntl.LOCK_EX)
            hit = complete.exists()
            if not hit:
                shutil.rmtree(rendered, ignore_errors=True)
                run_copy(
                    src_path=str(TOP),
                    dst_path=rendered,
                    data=dict(answers),
                    vcs_ref=self.ref,
                    defaults=True,
                    unsafe=True,
                    overwrite=True,
                    skip_tasks=True,  # REUSE-copy tasks need a checkout; the merge is what is tested
                )
                complete.touch()
        if hit:
            self.reuses += 1
        else:
            self.renders += 1
        # Outside the lock: the marker guarantees the render is complete and
        # nothing writes it again, so consumers only ever read it.
        shutil.copytree(rendered, dst, symlinks=True, dirs_exist_ok=True)


@pytest.fixture(scope="session")
def released_ref() -> str:
    """The released ref every case starts from (copier's own tag resolution)."""
    ref = release_tag(TOP)
    assert ref is not None, (
        "no release tag in this repository, so `copier update` has no released questionnaire to start "
        "from (see notes/PLAN-improvements.md W0)"
    )
    return ref


@pytest.fixture(scope="session")
def released_rev(released_ref: str) -> str:
    """The commit the released ref points at, as the renders record it."""
    return _out(TOP, "rev-parse", f"{released_ref}^{{commit}}").strip()


@pytest.fixture(scope="session")
def released_renders(released_ref: str, released_rev: str) -> Iterator[ReleasedRenders]:
    cache = ReleasedRenders(
        Path(tempfile.gettempdir()) / "python-copier-template-update-path",
        released_ref,
        released_rev,
        copier.__version__,
    )
    yield cache
    print(f"\nupdate-path render cache: {cache.renders} renders, {cache.reuses} reuses")


@pytest.mark.slow
@pytest.mark.parametrize(("case", "answers"), MATRIX, ids=[case for case, _ in MATRIX])
def test_update_from_the_released_ref_to_head(
    tmp_path: Path,
    answers: dict[str, Any],
    case: str,
    released_renders: ReleasedRenders,
    released_rev: str,
):
    """Replay a real `copier update` onto a project generated at the release."""
    project = tmp_path / case
    released_renders.render(project, answers)
    metadata = _answers(project)
    # The update clones this path, so a render served from another checkout
    # would drag the merge (and the assertions below) to that tree instead.
    assert metadata["_src_path"] == str(TOP), f"{case}: the render points at {metadata['_src_path']!r}"
    recorded = metadata["_commit"]
    assert _out(TOP, "rev-parse", f"{recorded}^{{commit}}").strip() == released_rev, (
        f"{case}: the released render must record the released revision, got {recorded!r}"
    )

    # The state a user's repo is in after `copier copy`: one commit.
    _out(project, "init", "-q", "-b", "main")
    _out(project, "add", "-A")
    _out(
        project,
        "-c",
        "user.name=update-path",
        "-c",
        "user.email=update-path@example.com",
        "commit",
        "-qm",
        f"scaffold from {released_rev}",
    )

    run_update(
        dst_path=project,
        vcs_ref="HEAD",
        defaults=True,
        unsafe=True,
        overwrite=True,
        skip_tasks=True,
    )

    # (a) copier's merge left no unresolved hunk behind.
    residue = _conflict_residue(project)
    assert residue == [], f"{case}: update left conflict residue in {residue}"

    # (b) nothing the update wrote trips git's whitespace/conflict-marker check.
    # New files are staged first: `git diff` alone would not look at them.
    _out(project, "add", "-A")
    check = _git(project, "diff", "--cached", "--check")
    assert check.returncode == 0 and not check.stdout, (
        f"{case}: `git diff --check` flagged the update:\n{check.stdout}{check.stderr}"
    )

    # (c) the answers now record the revision the update rendered.
    head_rev = _out(TOP, "rev-parse", "HEAD").strip()
    dirty = bool(_out(TOP, "status", "--porcelain").strip())
    describe = _out(TOP, "describe", "--tags", "--always").strip()
    updated = _answers(project)["_commit"]
    assert updated, f"{case}: copier must record the template revision it rendered"
    if head_rev == released_rev and not dirty:
        # Released ref == HEAD and a clean tree: the update is a no-op, so the
        # revision is legitimately unchanged (see the module docstring).
        assert updated == recorded
    else:
        assert updated != recorded, f"{case}: the update did not move off the released revision"
    if not dirty:
        assert updated == describe, (
            f"{case}: a clean template tree must be recorded exactly as git describes it ({describe!r})"
        )
    else:
        # A dirty tree makes copier commit its own private wip child of HEAD,
        # whose hash exists nowhere else; only the release track is assertable.
        assert updated.split("-", 1)[0] == describe.split("-", 1)[0], (
            f"{case}: recorded revision {updated!r} is not on the release track of {describe!r}"
        )


# A throwaway questionnaire for the guard: one question inline in copier.yml,
# one behind an `!include` (so the guard has to resolve includes to see it),
# and nothing else -- the guard never renders, so no template is needed.
SCRATCH_CONFIG = """---
base_question:
    type: str
    default: base
---
!include questions/extra.yml
"""

SCRATCH_FRAGMENT = """---
extra_question:
    type: str
    default: extra
"""

# Appended as its own YAML document: copier merges underscore settings by
# document order, so the last `_migrations` wins.
SCRATCH_MIGRATION = """---
_migrations:
    - version: 1.0.1
      command: echo rename base_question
"""


def _scratch_questionnaire(tmp_path: Path) -> tuple[Path, Callable[..., subprocess.CompletedProcess[str]]]:
    """A throwaway repository whose tagged questionnaire the guard can judge.

    It carries the guard itself (the tool resolves the repository it lives in)
    and a `1.0.0` tag, so the comparison has a released base like the real
    repository has. The questionnaire is synthetic on purpose: what is under
    test is the guard's verdict, not the shape of this repo's own questions.
    """
    repo = tmp_path / "scratch"
    (repo / "questions").mkdir(parents=True)
    (repo / "tools").mkdir()
    (repo / "copier.yml").write_text(SCRATCH_CONFIG)
    (repo / "questions" / "extra.yml").write_text(SCRATCH_FRAGMENT)
    shutil.copy(TOP / "tools" / "check_questionnaire_diff.py", repo / "tools")
    _out(repo, "init", "-q", "-b", "main")
    _out(repo, "add", "-A")
    _out(repo, "-c", "user.name=guard", "-c", "user.email=guard@example.com", "commit", "-qm", "questionnaire")
    _out(repo, "tag", "1.0.0")

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "tools/check_questionnaire_diff.py", *args],
            cwd=repo,
            capture_output=True,
            text=True,
        )

    return repo, run


def test_guard_fails_a_rename_or_default_change_without_a_migration(tmp_path: Path):
    """The guard's verdicts, in the order a contributor meets them."""
    repo, run = _scratch_questionnaire(tmp_path)
    assert run().returncode == 0, "an unchanged questionnaire has nothing to guard"
    assert run("--json").stdout.strip() == json.dumps(
        {
            "base": "1.0.0",
            "target": "working tree",
            "missing_migrations": [],
            "when_changes": [],
            "covered_by": [],
            "ok": True,
        },
        indent=2,
    )

    config = repo / "copier.yml"
    config.write_text(config.read_text().replace("base_question:", "renamed_question:", 1))
    renamed = run()
    assert renamed.returncode == 1
    assert "[MISSING MIGRATION] base_question (renamed to renamed_question)" in renamed.stdout
    assert json.loads(run("--json").stdout)["missing_migrations"] == [
        {"name": "base_question", "change": "renamed", "detail": "renamed to renamed_question"}
    ]

    fragment = repo / "questions" / "extra.yml"
    fragment.write_text(SCRATCH_FRAGMENT.replace("default: extra", "default: other"))
    defaulted = run()
    assert defaulted.returncode == 1
    assert "[MISSING MIGRATION] extra_question (default: 'extra' -> 'other')" in defaulted.stdout

    # A `when` change is a different kind of break: reported, never fatal on
    # its own (copier replays it instead of dropping the answer).
    fragment.write_text(
        SCRATCH_FRAGMENT.replace("default: extra", "default: other").replace(
            "    type: str\n", "    type: str\n    when: false\n", 1
        )
    )
    conditioned = run()
    assert conditioned.returncode == 1, "the uncovered default change still fails the run"
    assert "[CHANGED WHEN] extra_question (None -> False)" in conditioned.stdout

    with config.open("a") as handle:
        handle.write(SCRATCH_MIGRATION)
    covered = run()
    assert covered.returncode == 0, covered.stdout
    assert "covered by new _migrations entries: 1.0.1" in covered.stdout
    # Both breaks stay on the record, but a green run must not print the
    # failure marker `[MISSING MIGRATION]` CI greps for.
    assert "base_question (renamed to renamed_question)" in covered.stdout
    assert "extra_question (default: 'extra' -> 'other')" in covered.stdout
    assert "[MISSING MIGRATION]" not in covered.stdout
    assert "[CHANGED WHEN] extra_question (None -> False)" in covered.stdout

    # A question that is only added needs no migration: existing projects
    # answer it with its default.
    fragment.write_text(fragment.read_text() + "added_question:\n    type: str\n    default: added\n")
    added = run()
    assert added.returncode == 0, added.stdout
    assert "added_question" not in added.stdout
