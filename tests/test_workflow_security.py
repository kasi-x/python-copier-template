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


# Entry points that resolve this repository's newest release tag with git --
# `check_questionnaire_diff.release_tag` delegates to copier's own
# `get_latest_tag`, which reads the checkout's own tag refs via
# `git ls-remote --tags` and falls back to HEAD (or None) when it finds none.
# `actions/checkout` defaults are depth 1 and `--no-tags`, so a job running one
# of these must ask for the tags explicitly; without them the fallback is a
# silent HEAD, or a hard exit. The 2026-09-20 nightly Update rehearsal failed
# exactly there (exit 2, "no release tag in this repository") on the workflow
# that forgot it, while its sibling update-path.yml carried `fetch-depth: 0`.
TAG_RESOLVING_ENTRY_POINTS = {
    "tools/check_questionnaire_diff.py": "the guard's default --base is the newest release tag",
    "tools/update_rehearsal.py": "the rehearsal's default --base is the newest release tag",
    "tests/test_update_path.py": "the matrix renders at the released ref",
    "tests/test_update_rehearsal.py": "the rehearsal tests resolve the release tag",
}
"""Entry point (a file this repo owns) -> why its job needs the tags."""

TAG_RESOLVING_ALIASES = {
    "task update-rehearsal": "tools/update_rehearsal.py",
}
"""How a workflow invokes one of those entry points without naming its path.

The Taskfile spells the rehearsal as a task, so a run step may say
`task update-rehearsal`; the alias maps it onto the file whose requirement it
inherits. Kept out of the registry above so the staleness check there stays a
statement about files.

A job that reaches one of these through a reusable workflow (the `task:`
input of `_test.yml`) is tag-capable by construction: that path runs
`./.github/actions/setup-runner`, whose checkout already sets
`fetch-depth: 0`. This guard therefore only has to cover the jobs that invoke
an entry point directly, which is the shape that failed.
"""


def _invoked_entry_points(steps: list[dict]) -> list[str]:
    """The registered entry points these steps run, paths and aliases alike.

    Matched against the steps' `run` commands -- prose (`name`) is ignored, so
    a step that merely mentions a tool creates no requirement.
    """
    commands = " ".join(str(step.get("run", "")) for step in steps)
    found = [entry for entry in TAG_RESOLVING_ENTRY_POINTS if entry in commands]
    found.extend(entry for alias, entry in TAG_RESOLVING_ALIASES.items() if alias in commands)
    return sorted(set(found))


def _is_tag_capable(with_: dict) -> bool:
    """Whether a checkout fetches the tags `release_tag` reads.

    `fetch-depth: 0` is this repository's spelling everywhere it is needed
    (update-path.yml, the setup-runner composite); `fetch-tags: true` is the
    other way to get the same refs, so both are accepted.
    """
    return with_.get("fetch-depth") == 0 or with_.get("fetch-tags") is True


def _jobs_running_tag_resolvers() -> list[tuple[str, str, list[str], list[dict]]]:
    """(workflow, job, entry points invoked, its checkout steps) for every job
    that runs a tag-resolving entry point."""
    return [
        (name, job_name, resolvers, checkouts)
        for name, wf in _workflows().items()
        for job_name, job in _jobs(wf).items()
        if (resolvers := _invoked_entry_points(job.get("steps") or []))
        for checkouts in [
            [s for s in (job.get("steps") or []) if str(s.get("uses", "")).startswith("actions/checkout")]
        ]
    ]


def test_workflows_resolving_the_release_tag_check_out_the_tags():
    """A job that reads the release tag must check the tags out.

    The guard is driven by the workflows themselves: any step running a
    tag-resolving entry point requires that job's `actions/checkout` to be
    tag-capable. Static and offline -- the failure it prevents is a scheduled
    run discovering the omission on GitHub, which is where it last happened.
    """
    jobs = _jobs_running_tag_resolvers()
    assert jobs, "no workflow runs a tag-resolving entry point: the registry below is stale"
    unchecked = [
        f"{name}:{job_name} runs {', '.join(resolvers)} but never checks the repo out"
        for name, job_name, resolvers, checkouts in jobs
        if not checkouts
    ]
    offenders = [
        f"{name}:{job_name}: checkout needs `fetch-depth: 0` for "
        f"{', '.join(resolvers)} ({TAG_RESOLVING_ENTRY_POINTS[resolvers[0]]}), but declares {step.get('with') or {}}"
        for name, job_name, resolvers, checkouts in jobs
        for step in checkouts
        if not _is_tag_capable(step.get("with") or {})
    ]
    assert not unchecked + offenders, "\n  ".join(
        ["a workflow reads the release tag without fetching it:", *unchecked, *offenders]
    )


def test_the_tag_resolving_registry_names_real_entry_points():
    """The registry's other direction: every entry point still resolves tags.

    Same idiom as test_tool_layers' ALLOWED_UPWARD_IMPORTS and
    test_render_convention's SANCTIONED: a list that only grows stale is a
    list that lies. Each named file must exist and must reach `release_tag`
    itself (define, import or call it) -- a tool that stopped resolving the
    tag would keep its workflow requirement alive forever otherwise.
    """
    missing = [entry for entry in TAG_RESOLVING_ENTRY_POINTS if not (TOP / entry).is_file()]
    assert not missing, f"the registry names files that do not exist: {missing}"
    without = [
        entry for entry in TAG_RESOLVING_ENTRY_POINTS if "release_tag" not in (TOP / entry).read_text(encoding="utf-8")
    ]
    assert not without, (
        f"these entry points no longer name `release_tag`, so their workflow requirement is stale: {without}"
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


def test_the_composite_does_not_check_the_repository_out():
    """The composite must not fetch the repository it lives in.

    A local action's files have to be on disk before the runner can resolve
    it, so `uses: actions/checkout` *inside* this composite can never run:
    the caller fails first with "Can't find 'action.yml' ... Did you forget
    to run actions/checkout before running your local action?" -- which is
    exactly how the §19 extraction broke every reusable workflow on the
    first push that ran it (lint, test, test-meta and docs all died in
    "Set up the runner" before a single task ran).

    Both directions: the composite holds no checkout, and every caller that
    invokes it checks out *before* that step.
    """
    action = yaml.safe_load(COMPOSITE.read_text(encoding="utf-8"))
    steps = action["runs"].get("steps") or []
    assert not any(str(s.get("uses", "")).startswith("actions/checkout") for s in steps), (
        "the setup-runner composite must not call actions/checkout: a local action "
        "cannot fetch the repository that has to contain it"
    )
    for name in COMPOSITE_USERS:
        wf = _workflows()[name]
        for job_name, job in _jobs(wf).items():
            steps = job.get("steps") or []
            order = [str(step.get("uses", "")) for step in steps]
            if not any(u.startswith("./.github/actions/setup-runner") for u in order):
                continue
            composite_at = next(i for i, u in enumerate(order) if u.startswith("./.github/actions/setup-runner"))
            checkout_at = next((i for i, u in enumerate(order) if u.startswith("actions/checkout")), None)
            assert checkout_at is not None, f"{name}:{job_name} calls the composite without checking the repository out"
            assert checkout_at < composite_at, (
                f"{name}:{job_name} calls the composite before its checkout -- the local action "
                f"cannot resolve until the repository is on disk"
            )


def _version3(text: str) -> tuple[int, int, int]:
    """Parse an `X.Y.Z` (optionally `v`-prefixed) version into comparable ints."""
    parts = [int(part) for part in text.lstrip("v").split(".")]
    assert len(parts) == 3, f"expected an X.Y.Z version, got {text!r}"
    return parts[0], parts[1], parts[2]


def test_zizmor_cli_pin_is_inside_the_actions_allowlist():
    """The zizmor action and its cli pin must be a released pair.

    `zizmorcore/zizmor-action` ships `support/versions`, a digest allowlist
    of the cli releases that action can run, and `action.sh` dies with
    "Unknown version" for anything else -- so a cli pin newer than the
    action's allowlist turns the Security job red before it scans. The
    static half needs no network: the action's *minor* release that first
    carried a cli version is recorded below, and the pin is checked against
    it. (The 2026-09-20 break: cli 1.30.1 pinned against action v0.6.3,
    whose allowlist ends at 1.30.0.)
    """
    security = (TOP / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")
    action_m = re.search(r"zizmorcore/zizmor-action@[0-9a-f]{40} # (v\d+\.\d+\.\d+)", security)
    cli_m = re.search(r'version: "(\d+\.\d+\.\d+)"', security)
    assert action_m and cli_m, "security.yml must pin both the action and its cli"
    action_version = _version3(action_m.group(1))
    cli_version = _version3(cli_m.group(1))
    # action release that first shipped each cli version in its allowlist
    first_action_for_cli: dict[tuple[int, int, int], tuple[int, int, int]] = {
        (1, 30, 0): (0, 6, 3),
        (1, 30, 1): (0, 6, 4),
    }
    minimum = first_action_for_cli.get(cli_version)
    assert minimum is not None, (
        f"cli {cli_m.group(1)} is not in MINIMUM_ACTION_FOR_CLI -- add the action release whose "
        f"support/versions first listed it (check the action's support/versions on GitHub), or "
        f"drop the cli pin back to a version the pinned action carries"
    )
    assert action_version >= minimum, (
        f"security.yml pins zizmor cli {cli_m.group(1)} against action {action_m.group(1)}, but that "
        f"cli version needs action v{'.'.join(map(str, minimum))} or newer: the action's allowlist "
        f"ends lower and it exits with 'Unknown version'"
    )
    # The shipped copy is what generated projects actually run, and it is a
    # separate file (a .jinja, not a symlink): a fix applied to one side only
    # would leave every generated project red. Compare the pin lines.
    jinja = (
        TOP
        / "template"
        / "{% if is_github %}.github{% endif %}"
        / "{% if ci_provider == 'github_actions' %}workflows{% endif %}"
        / "security.yml.jinja"
    ).read_text(encoding="utf-8")
    assert action_m.group(0) in jinja, (
        "template security.yml.jinja pins a different zizmor action than the root workflow"
    )
    assert cli_m.group(0) in jinja, "template security.yml.jinja pins a different zizmor cli than the root workflow"


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
