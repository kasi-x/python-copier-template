"""Structural security checks for the template's own GitHub Actions workflows.

Guards the OpenSSF Scorecard "Token-Permissions" / "Pinned-Dependencies"
checks from drifting in this repo's own CI:

- every workflow and every job declares an explicit, minimal `permissions`
  block (no implicit all-scopes default);
- `actions/checkout` sets `persist-credentials: false` unless the workflow
  genuinely needs to push (only `_example.yml` does);
- `uses:` references are pinned to a 40-character commit SHA rather than a
  mutable tag.

All but the renovate contract are static, offline assertions over
`.github/workflows/*.yml`, in the same spirit as test_copier_structure.py /
test_micropython_maintenance.py; the renovate contract parses a real render
of `template/renovate.json.jinja` (see render_cache.py).
"""

import json
import re
import sys
from pathlib import Path

import yaml

from render_cache import RenderCache

# Imported so pytest can inject the fixture (the cache lives here, not in
# conftest.py: the template renders that file into generated projects).
from render_cache import render_cache as render_cache  # noqa: PLC0414

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/support.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools.answers import BASE  # noqa: E402

WORKFLOWS_DIR = TOP / ".github" / "workflows"

# Workflows that intentionally keep checkout credentials (they push).
CREDENTIAL_KEEPERS = {"_example.yml"}

# Reusable workflows run with the caller's permissions; they still declare
# `contents: read` as the least they need. Jobs inside a reusable workflow
# may inherit from the top-level block.
WORKFLOW_CALL = "workflow_call"


def _workflows() -> dict[str, dict]:
    workflows: dict[str, dict] = {}
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        workflows[path.name] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return workflows


def _jobs(wf: dict) -> dict:
    return wf.get("jobs", {}) or {}


def _has_own_permissions(wf: dict) -> bool:
    return "permissions" in wf


def test_all_workflows_parse_and_declare_permissions():
    """Every workflow declares top-level permissions (least privilege)."""
    workflows = _workflows()
    assert workflows, "no workflows found"
    for name, wf in workflows.items():
        # Non-reusable workflows run with the repo's default token; they must
        # scope it down explicitly. Reusable ones declare contents: read too.
        assert _has_own_permissions(wf), f"{name} is missing a top-level permissions block"


def test_no_workflow_uses_write_all():
    """No workflow may grant the broadest scope."""
    workflows = _workflows()
    for name, wf in workflows.items():
        perms = wf.get("permissions") or {}
        assert perms != "write-all", f"{name} grants write-all"


def test_reusable_workflows_scope_contents_read():
    """Reusable workflows declare `contents: read` (their minimum)."""
    workflows = _workflows()
    for name, wf in workflows.items():
        if wf.get("on") == WORKFLOW_CALL:
            perms = wf.get("permissions")
            assert perms == {"contents": "read"}, f"{name} should declare contents: read, got {perms}"


def test_every_job_declares_permissions():
    """Non-reusable workflows: each job either inherits a workflow-level block
    or declares its own. We assert the workflow-level block exists (checked
    above), so this is a sanity pass that no job grants extra scopes
    implicitly.
    """
    workflows = _workflows()
    for name, wf in workflows.items():
        if wf.get("on") == WORKFLOW_CALL:
            continue
        for job_name, job in _jobs(wf).items():
            # A job may add scopes on top of the workflow block (e.g.
            # `issues: write` for issue-creating jobs). That is fine; the
            # workflow-level `contents: read` default is what we enforce.
            job_perms = job.get("permissions") or {}
            if job_perms == "write-all":
                assert False, f"{name}: job {job_name} grants write-all"


def test_checkout_uses_persist_credentials_false():
    """checkout must not persist the GITHUB_TOKEN unless the workflow pushes."""
    workflows = _workflows()
    for name, wf in workflows.items():
        for job_name, job in _jobs(wf).items():
            for step in job.get("steps") or []:
                uses = step.get("uses", "")
                if not uses.startswith("actions/checkout"):
                    continue
                with_ = step.get("with") or {}
                persist = with_.get("persist-credentials", True)
                if name in CREDENTIAL_KEEPERS:
                    # Intentionally keeps credentials to push (deploy key).
                    continue
                assert persist is False, f"{name}:{job_name} checkout should set persist-credentials: false"


def test_checkout_not_used_with_default_credentials_for_pushing_jobs():
    """Only workflows that push may keep checkout credentials."""
    workflows = _workflows()
    for name, wf in workflows.items():
        for job_name, job in _jobs(wf).items():
            for step in job.get("steps") or []:
                uses = step.get("uses", "")
                if not uses.startswith("actions/checkout"):
                    continue
                with_ = step.get("with") or {}
                persist = with_.get("persist-credentials", True)
                if persist is False:
                    continue  # fine: credentials dropped
                # Credentials are kept. That is only acceptable for the
                # dedicated push workflow (_example.yml, via deploy key).
                assert name in CREDENTIAL_KEEPERS, (
                    f"{name}:{job_name} keeps checkout credentials but is not in {sorted(CREDENTIAL_KEEPERS)}"
                )


# The single deliberate non-SHA reference: pypa/gh-action-pypi-publish is used
# at its upstream-recommended release line @release/v1 (a branch ref renovate
# cannot digest-pin). Mirrored in .github/zizmor.yml's unpinned-uses ignore.
DELIBERATE_BRANCH_REFS = {
    "pypa/gh-action-pypi-publish@release/v1",
}


def test_uses_are_pinned_to_full_sha():
    """Scorecard Pinned-Dependencies: every third-party action is SHA-pinned.

    renovate's `helpers:pinGitHubActionDigests` keeps these digests current.
    The only exceptions are `pypa/gh-action-pypi-publish@release/v1` (see
    DELIBERATE_BRANCH_REFS) and `docker://` steps, which must be pinned to a
    full sha256 image digest.
    """
    workflows = _workflows()
    sha_re = re.compile(r"^[0-9a-f]{40}$")
    for name, wf in workflows.items():
        for job_name, job in _jobs(wf).items():
            for step in job.get("steps") or []:
                uses = step.get("uses", "")
                if not uses:
                    continue
                # Local reusable workflows (.github/workflows/*.yml) are not
                # third-party.
                if uses.startswith("./"):
                    continue
                _owner_repo, _, ref = uses.partition("@")
                if uses in DELIBERATE_BRANCH_REFS:
                    continue
                if _owner_repo.startswith("docker://"):
                    _image, _, digest = ref.partition(":")
                    assert digest and len(digest) == 64, (
                        f"{name}:{job_name} uses {uses!r} -- pin the docker image to a full sha256 digest"
                    )
                    continue
                assert sha_re.match(ref), (
                    f"{name}:{job_name} uses {uses!r} -- pin to a 40-char SHA "
                    f"with the version as a comment (e.g. @<sha> # vX.Y.Z)"
                )


COMPOSITE = TOP / ".github" / "actions" / "setup-runner" / "action.yml"
"""The shared setup the four reusable workflows call (TODO archive §19)."""

COMPOSITE_USERS = ("_tasks.yml", "_test.yml", "_docs.yml", "_dist.yml")
"""The workflows whose duplicated setup block the composite replaced."""


def test_setup_runner_composite_is_pinned_and_used():
    """The extracted setup composite keeps the security bar, and the four
    workflows that once repeated the block actually call it.

    Two directions, the registry idiom: the composite itself is held to the
    same static checks as the workflows (SHA-pinned `uses`, checkout without
    persisted credentials), and each COMPOSITE_USERS workflow keeps exactly
    one reference to it — so a caller reverting to inline steps (or a new
    copy of the block) fails here instead of quietly re-forking the setup.
    """
    action = yaml.safe_load(COMPOSITE.read_text(encoding="utf-8"))
    assert action.get("runs", {}).get("using") == "composite", "the action must be a composite"
    steps = action["runs"].get("steps") or []
    assert steps, "the composite has no steps"
    sha_re = re.compile(r"^[0-9a-f]{40}$")
    for step in steps:
        uses = step.get("uses", "")
        if not uses:
            continue  # a run step
        _owner_repo, _, ref = uses.partition("@")
        assert sha_re.match(ref), f"composite step {step.get('name')!r} uses {uses!r} -- pin to a 40-char SHA"
        if uses.startswith("actions/checkout"):
            assert step.get("with", {}).get("persist-credentials") is False, (
                "the composite's checkout must not persist credentials"
            )

    for name in COMPOSITE_USERS:
        wf = _workflows()[name]
        references = [
            step.get("uses")
            for job in _jobs(wf).values()
            for step in job.get("steps") or []
            if str(step.get("uses", "")).startswith("./.github/actions/setup-runner")
        ]
        assert references == ["./.github/actions/setup-runner"], (
            f"{name} must call the setup-runner composite exactly once, got {references}"
        )


def test_setup_runner_ships_to_generated_projects(render_cache: RenderCache, tmp_path: Path):
    """Generated projects calling the workflows must have the action too.

    The reusable workflows reference `./.github/actions/setup-runner`, which
    resolves inside the *generated* repository -- without the symlinked
    action dir, every generated project's CI would break on its first run
    (the archived item's own "CI 実走が要る" caveat). One render proves the
    link survives as the composite's bytes.
    """
    render_cache.render(tmp_path, {**BASE, "project_type": "library"})
    shipped = tmp_path / ".github" / "actions" / "setup-runner" / "action.yml"
    assert shipped.is_file(), "the composite action is missing from the generated project"
    assert shipped.read_text(encoding="utf-8") == COMPOSITE.read_text(encoding="utf-8"), (
        "the shipped action must be content-identical to the repository's"
    )


def test_renovate_baseline_matches_generated_template(tmp_path: Path, render_cache: RenderCache):
    """Root and generated renovate.json share the update baseline.

    Both must extend the same presets (recommended + digest pinning +
    vulnerability alerts) with lockFileMaintenance automerge on. The
    per-manager rules intentionally differ: the root groups non-major
    action updates (its digests are renovate-tracked), while generated
    projects disable template-owned actions per category (updates flow
    through copier update). This test pins that contract on the parsed
    documents -- the generated one comes from a real render, so a jinja
    branch (docker/pypi/docs/...) that emits invalid JSON fails here too.
    """
    root = json.loads((TOP / "renovate.json").read_text(encoding="utf-8"))
    render_cache.render(tmp_path, {**BASE, "project_type": "library"})
    generated = json.loads((tmp_path / "renovate.json").read_text(encoding="utf-8"))

    for preset in (
        "config:recommended",
        ":configMigration",
        ":enableVulnerabilityAlerts",
        "helpers:pinGitHubActionDigests",
    ):
        assert preset in root["extends"], f"root renovate.json lost {preset}"
        assert preset in generated["extends"], f"generated renovate.json lost {preset}"
    for name, document in (("root", root), ("generated", generated)):
        assert document["lockFileMaintenance"]["automerge"] is True, name
        assert document["vulnerabilityAlerts"]["automerge"] is True, name
    # generated: template-owned actions are disabled per category, so copier
    # update (not renovate) owns their versions
    disabled = [rule for rule in generated["packageRules"] if rule.get("enabled") is False]
    assert any("actions/checkout" in rule.get("matchPackageNames", []) for rule in disabled), (
        "generated renovate.json must disable the template-owned core actions"
    )
    assert len(disabled) >= 4, "one disabling rule per dependency category"
    # root keeps digest-tracked actions grouped, not disabled
    group_rules = [rule for rule in root["packageRules"] if rule.get("groupName") == "GitHub Actions"]
    assert group_rules, "root renovate.json lost the GitHub Actions group rule"
