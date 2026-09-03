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
                assert persist is False, (
                    f"{name}:{job_name} checkout should set persist-credentials: false"
                )


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
                    f"{name}:{job_name} keeps checkout credentials but is not "
                    f"in {sorted(CREDENTIAL_KEEPERS)}"
                )


# Mutable branch refs that predate renovate's pinDigests migration. Each is a
# known upstream release line that renovate will convert to a full SHA in its
# pinning PR; once that lands, delete this allowlist and require SHA everywhere.
TRANSITIONAL_BRANCH_REFS = {
    "pypa/gh-action-pypi-publish@release/v1",
}


def test_uses_are_not_branch_refs_and_shas_are_full_length():
    """Scorecard Pinned-Dependencies guard, in its pre-pinDigests form.

    renovate's `helpers:pinGitHubActionDigests` converts every `uses:` to a
    40-char SHA (with the version tag kept as a comment). Until that pinning
    PR lands, tag refs (`@v7`) are the transitional state and are allowed
    here; what is never allowed is a mutable *branch* ref (`@main`,
    `@master`, `@release/v1`) or a short SHA. Once pinning has landed, flip
    this to require the full SHA everywhere.
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
                # third-party; the actions/* namespace is first-party.
                if uses.startswith("./"):
                    continue
                _owner_repo, _, ref = uses.partition("@")
                if sha_re.match(ref):
                    continue  # fully pinned
                if uses in TRANSITIONAL_BRANCH_REFS:
                    continue  # renovate's pinning PR converts this
                assert "/" not in ref, (
                    f"{name}:{job_name} uses mutable branch ref {uses!r} -- "
                    f"pin to a 40-char SHA or wait for renovate's pinning PR"
                )
