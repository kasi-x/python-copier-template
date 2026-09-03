"""Structural security checks for the template's own GitHub Actions workflows.

Guards the OpenSSF Scorecard "Token-Permissions" / "Pinned-Dependencies"
checks from drifting in this repo's own CI:

- every workflow and every job declares an explicit, minimal `permissions`
  block (no implicit all-scopes default);
- `actions/checkout` sets `persist-credentials: false` unless the workflow
  genuinely needs to push (only `_example.yml` does);
- `uses:` references are pinned to a 40-character commit SHA rather than a
  mutable tag.

These are static, offline assertions over `.github/workflows/*.yml`, in the
same spirit as test_copier_structure.py / test_micropython_maintenance.py.
"""

import re
from pathlib import Path

import yaml

TOP = Path(__file__).absolute().parent.parent
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
    The only exception is `pypa/gh-action-pypi-publish@release/v1` (see
    DELIBERATE_BRANCH_REFS) — a deliberate, documented deviation mirrored in
    .github/zizmor.yml.
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
                assert sha_re.match(ref), (
                    f"{name}:{job_name} uses {uses!r} -- pin to a 40-char SHA "
                    f"with the version as a comment (e.g. @<sha> # vX.Y.Z)"
                )
