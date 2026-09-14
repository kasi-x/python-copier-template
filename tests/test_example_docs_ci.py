"""The docs engines and the quality/CI gates: which docs tree each docs_type
renders, what the generated workflows jobs run, hygiene/secrets, the license +
FAIR/security metadata, and the ruff/basedpyright configurations the generated
projects are checked with."""

import json
import re
import tomllib
from pathlib import Path

import pytest
import yaml
from copier import run_copy

from support import TOP
from support import ci_requested_tasks
from support import copy_project
from support import copy_project_recommended
from support import make_venv


def _renovate_rules(path: Path) -> list[dict]:
    """The generated renovate.json's packageRules."""
    return json.loads(path.read_text())["packageRules"]


def _renovate_disables(path: Path, action: str) -> bool:
    """True if renovate is told to leave this action's version to copier."""
    return any(
        action in rule.get("matchPackageNames", []) and rule.get("enabled") is False for rule in _renovate_rules(path)
    )


def _renovate_mentions(path: Path, needle: str) -> bool:
    return any(needle in name for rule in _renovate_rules(path) for name in rule.get("matchPackageNames", []))


@pytest.mark.heavy
@pytest.mark.network
def test_template_with_extra_code_and_api_docs(tmp_path: Path):
    copy_project(tmp_path, docs_type="sphinx", project_type="library")
    run = make_venv(tmp_path)
    # add some code
    init = tmp_path / "src" / "python_copier_template_example" / "__init__.py"
    init.write_text(
        init.read_text().replace(
            'from ._version import __version__\n\n__all__ = ["__version__"]',
            '''from python_copier_template_example import extra_pkg

from ._version import __version__


class TopCls:
    """A top level class."""


__all__ = ["TopCls", "__version__", "extra_pkg"]''',
        )
    )
    extra_pkg = tmp_path / "src" / "python_copier_template_example" / "extra_pkg"
    extra_pkg.mkdir()
    (extra_pkg / "__init__.py").write_text('"""Extra Package."""\n')
    code = '''"""A module."""


class Thing:
    """A docstring."""
'''
    (extra_pkg / "extra_module.py").write_text(code)
    run("git add .")  # track the added code so the docs build sees it
    # Build
    run("uvx --from go-task-bin task check")
    run("uvx --from go-task-bin task docs")
    # Check it generates the right output
    api_dir = tmp_path / "build" / "html" / "_api"
    top_html = api_dir / "python_copier_template_example.html"
    assert "extra_pkg" in top_html.read_text()
    assert "Extra Package." in top_html.read_text()
    assert "TopCls" in top_html.read_text()
    assert "A top level class." in top_html.read_text()
    assert "__version__" in top_html.read_text()
    assert "setuptools_scm" in top_html.read_text()
    package_html = api_dir / "python_copier_template_example.extra_pkg.html"
    assert "extra_module" in package_html.read_text()
    assert "A module." in package_html.read_text()
    module_html = api_dir / "python_copier_template_example.extra_pkg.extra_module.html"
    assert "Thing" in module_html.read_text()
    assert "A docstring." in module_html.read_text()


def test_template_pyrefly(tmp_path: Path):
    copy_project(tmp_path, type_checker="pyrefly")
    pyproject = (tmp_path / "pyproject.toml").read_text()
    assert "[tool.basedpyright]" in pyproject
    assert "[tool.pyrefly]" in pyproject


def test_template_ty(tmp_path: Path):
    copy_project(tmp_path, type_checker="ty")
    pyproject = (tmp_path / "pyproject.toml").read_text()
    # basedpyright is always present; ty is the secondary checker.
    assert "[tool.basedpyright]" in pyproject
    assert "[tool.ty]" in pyproject


def test_template_no_docs(tmp_path: Path):
    copy_project(tmp_path, docs_type="README")
    # README-only: no docs site config, no docs/ tree, no docs build task
    assert not (tmp_path / "zensical.toml").exists()
    assert not (tmp_path / "docs").exists()
    assert "task docs" not in (tmp_path / "Taskfile.yml").read_text()


def test_template_no_precommit_hygiene_in_ci(tmp_path: Path):
    """pre-commit is replaced by: task-runner lint/fix tasks (ruff, local)
    plus a hygiene workflow (secrets, workflow linting, YAML/EOF, conventional
    commits, REUSE/CFF — CI-only)."""
    copy_project(tmp_path, task_runner="task")
    # nothing pre-commit-shaped ships in the generated project
    assert not (tmp_path / ".pre-commit-config.yaml").exists()
    taskfile = (tmp_path / "Taskfile.yml").read_text()
    assert "pre-commit" not in taskfile
    assert "ruff format --check ." in taskfile
    pyproject = (tmp_path / "pyproject.toml").read_text()
    assert "pre-commit" not in pyproject
    # the hygiene workflow exists, is a reusable workflow, and pins actions
    hygiene = (tmp_path / ".github" / "workflows" / "_hygiene.yml").read_text()
    assert "workflow_call:" in hygiene
    assert "gitleaks/gitleaks-action@" in hygiene
    assert "reviewdog" not in hygiene  # actionlint runs via the digest-pinned docker step
    assert "docker://rhysd/actionlint@sha256:" in hygiene
    # CI calls it and includes it in the required-checks gate
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "uses: ./.github/workflows/_hygiene.yml" in ci
    assert "needs: [hygiene, lint, test" in ci
    # the fix task exists as the pre-commit replacement
    assert "fix:" in taskfile


def test_template_zensical_docs(tmp_path: Path):
    copy_project(tmp_path, docs_type="zensical")
    pyproject_toml = tmp_path / "pyproject.toml"
    assert '"zensical"' in pyproject_toml.read_text()
    assert (tmp_path / "zensical.toml").exists()
    assert (tmp_path / "docs").exists()


def test_template_great_docs(tmp_path: Path):
    copy_project(tmp_path, docs_type="great-docs")
    assert (tmp_path / "great-docs.yml").exists()
    assert (tmp_path / "index.qmd").exists()


def test_template_library_sphinx_version_command(tmp_path: Path):
    """Non-web_api types keep the CLI --version check, named exactly."""
    copy_project(tmp_path, docs_type="README")
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "version-command: python -m python_copier_template_example --version" in ci
    # The guess-based fallback stays only as the reusable workflow's default.
    dist = (tmp_path / ".github" / "workflows" / "_dist.yml").read_text()
    assert "version-command" in dist


def test_template_no_ci(tmp_path: Path):
    copy_project(tmp_path, ci_provider="none")
    assert not (tmp_path / ".github" / "workflows").exists()
    # GitHub-specific files are still generated
    assert (tmp_path / ".github" / "actionlint.yaml").exists()


def test_template_license_check_task(tmp_path: Path):
    """Recommended path ships pip-licenses + a standalone license-check task.

    The task stays out of local `type-check`/`check` (both must run
    offline): CI's lint job calls `lint,type-check,license-check` together
    instead (see ci.yml / .gitlab-ci.yml). Opting out drops the dep and
    the task.
    """
    copy_project(tmp_path, project_type="cli")
    pyproject = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert any(d.startswith("pip-licenses") for d in pyproject["dependency-groups"]["dev"])
    tasks = yaml.safe_load((tmp_path / "Taskfile.yml").read_text())["tasks"]
    assert any("pip-licenses" in str(command) for command in tasks["license-check"]["cmds"])
    assert not any("pip-licenses" in str(command) for command in tasks["type-check"]["cmds"]), (
        "type-check must stay runnable offline"
    )
    assert "license-check" in ci_requested_tasks(tmp_path / ".github" / "workflows" / "ci.yml")

    off_path = tmp_path / "off"
    copy_project(
        off_path,
        project_type="cli",
        use_recommended_security=False,
        security_policy=True,
        scorecard=False,
        license_check=False,
    )
    off_pyproject = tomllib.loads((off_path / "pyproject.toml").read_text())
    assert not any(d.startswith("pip-licenses") for d in off_pyproject["dependency-groups"]["dev"])
    assert "license-check" not in (off_path / "Taskfile.yml").read_text()


def test_template_ci_runs_license_check(tmp_path: Path):
    """CI lint calls the standalone license-check; GitLab matches."""
    copy_project(tmp_path, project_type="cli")
    assert "license-check" in ci_requested_tasks(tmp_path / ".github" / "workflows" / "ci.yml")

    gitlab_path = tmp_path / "gitlab"
    copy_project(
        gitlab_path,
        project_type="cli",
        git_platform="gitlab.com",
        gitlab_group="mygroup",
    )
    gitlab = yaml.safe_load((gitlab_path / ".gitlab-ci.yml").read_text())
    assert any("license-check" in line for line in gitlab["lint"]["script"]), "GitLab's lint job matches"


def test_template_gitleaks_blocks_deidentification_salt(tmp_path: Path):
    """The generated gitleaks config carries the deidentification-salt rule."""
    copy_project(tmp_path, project_type="cli")
    gitleaks = (tmp_path / ".gitleaks.toml").read_text()
    assert "deidentification-salt" in gitleaks
    assert "secret_salt" in gitleaks


def test_template_author_orcid_validator(tmp_path: Path):
    """A malformed ORCID iD is rejected at question time (validator)."""
    from test_recommended_path import BASE

    with pytest.raises(ValueError) as excinfo:
        run_copy(
            src_path=str(TOP),
            dst_path=tmp_path,
            data={
                **BASE,
                "project_type": "library",
                "use_recommended_license": False,
                "fair": True,
                "author_orcid": "not-an-orcid",
            },
            vcs_ref="HEAD",
            defaults=True,
            unsafe=True,
            overwrite=True,
            skip_tasks=True,
        )
    assert "not-an-orcid" in str(excinfo.value), "the refusal names the rejected iD"


def test_template_license_choice(tmp_path: Path):
    copy_project(tmp_path, license="GPL-3.0")
    assert "GNU GENERAL PUBLIC LICENSE" in (tmp_path / "LICENSE").read_text()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["license"] == "GPL-3.0"
    assert pyproject_toml["project"]["license-files"] == ["LICENSE"]


def test_template_license_proprietary(tmp_path: Path):
    copy_project(tmp_path, license="Proprietary")
    license_text = (tmp_path / "LICENSE").read_text()
    assert "All Rights Reserved" in license_text
    assert "UNAUTHORIZED COPYING" in license_text
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    # PEP 639 has no SPDX expression for "no license": omit the field entirely
    assert "license" not in pyproject_toml["project"]


def test_template_fair_metadata(tmp_path: Path):
    copy_project(
        tmp_path,
        fair=True,
        author_orcid="0000-0002-1825-0099",
        data_reusable=True,
        data_ethics=True,
    )
    cff = (tmp_path / "CITATION.cff").read_text()
    assert "cff-version: 1.2.0" in cff
    assert 'title: "python-copier-template-example"' in cff
    assert 'repository-code: "https://github.com/kasi-x/python-copier-template-example"' in cff
    assert 'license: "Apache-2.0"' in cff
    assert 'orcid: "https://orcid.org/0000-0002-1825-0099"' in cff
    reuse_toml = (tmp_path / "REUSE.toml").read_text()
    assert 'SPDX-License-Identifier = "Apache-2.0"' in reuse_toml
    hygiene = (tmp_path / ".github" / "workflows" / "_hygiene.yml").read_text()
    assert "uvx cffconvert==2.0.0 --validate" in hygiene
    assert "fsfe/reuse-action@" in hygiene
    assert (tmp_path / "data" / "DUO.md").exists()
    assert (tmp_path / "data" / "CARE.md").exists()
    assert "Traceability & provenance" in (tmp_path / "data" / "CARE.md").read_text()
    fair_workflow = tmp_path / ".github" / "workflows" / "fair-software.yml"
    assert fair_workflow.exists()
    uses = [
        step["uses"]
        for job in yaml.safe_load(fair_workflow.read_text())["jobs"].values()
        for step in job.get("steps") or []
        if str(step.get("uses", "")).startswith("fair-software/howfairis-github-action")
    ]
    assert uses, "the FAIR workflow must run howfairis"
    assert all(re.fullmatch(r"fair-software/howfairis-github-action@[0-9a-f]{40}", ref) for ref in uses), uses
    assert _renovate_disables(tmp_path / "renovate.json", "fair-software/howfairis-github-action"), (
        "the action's version is owned by copier update, not renovate"
    )


def test_template_fair_off(tmp_path: Path):
    copy_project(tmp_path, fair=False)
    assert not (tmp_path / "CITATION.cff").exists()
    assert not (tmp_path / "REUSE.toml").exists()
    assert not (tmp_path / ".github" / "workflows" / "fair-software.yml").exists()
    assert not _renovate_mentions(tmp_path / "renovate.json", "howfairis"), "no FAIR rule without the FAIR workflow"


@pytest.mark.parametrize("restricted_license", ["Proprietary", "Confidential"])
def test_template_fair_restricted_license(tmp_path: Path, restricted_license: str):
    copy_project(tmp_path, fair=True, license=restricted_license)
    cff = (tmp_path / "CITATION.cff").read_text()
    assert "cff-version: 1.2.0" in cff
    # CFF has no SPDX expression for "all rights reserved": omit the field
    assert "license:" not in cff
    # reuse only applies to open-source licenses
    assert not (tmp_path / "REUSE.toml").exists()
    hygiene = (tmp_path / ".github" / "workflows" / "_hygiene.yml").read_text()
    assert "uvx cffconvert==2.0.0 --validate" in hygiene
    assert "fsfe/reuse-action@" in hygiene


def test_template_license_confidential(tmp_path: Path):
    copy_project(tmp_path, license="Confidential")
    license_text = (tmp_path / "LICENSE").read_text()
    assert "CONFIDENTIAL AND PROPRIETARY INFORMATION" in license_text
    assert "trade secrets" in license_text
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert "license" not in pyproject_toml["project"]


def test_template_license_confidential_recommended_elsewhere(tmp_path: Path):
    # Opting out of just the license/FAIR gate should still leave every
    # other section (docs, quality, integrations, ...) on its recommended
    # default.
    copy_project_recommended(
        tmp_path,
        use_recommended_license=False,
        license="Confidential",
        fair=False,
    )
    license_text = (tmp_path / "LICENSE").read_text()
    assert "CONFIDENTIAL AND PROPRIETARY INFORMATION" in license_text
    assert not (tmp_path / "CITATION.cff").exists()


def test_template_changelog(tmp_path: Path):
    copy_project(tmp_path)
    assert (tmp_path / "CHANGELOG.md").exists()
    assert (tmp_path / "cliff.toml").exists()


def test_template_gitlab(tmp_path: Path):
    copy_project(tmp_path, git_platform="gitlab.com", gitlab_group="mygroup")
    assert (tmp_path / ".gitlab-ci.yml").exists()
    assert not (tmp_path / ".github").exists()
    # SECURITY.md / Scorecard are GitHub-only (private advisories + badge
    # both require github.com), so GitLab projects skip them.
    assert not (tmp_path / "SECURITY.md").exists()
    assert "SECURITY.md" not in (tmp_path / "README.md").read_text()


def test_template_security_policy_opt_out(tmp_path: Path):
    """use_recommended_security=false + security_policy=false drops SECURITY.md."""
    copy_project(tmp_path, use_recommended_security=False, security_policy=False, scorecard=False)
    assert not (tmp_path / "SECURITY.md").exists()
    assert "SECURITY.md" not in (tmp_path / "README.md").read_text()


def test_template_scorecard_opt_in(tmp_path: Path):
    """scorecard=true adds the Scorecard workflow + README badge."""
    copy_project(tmp_path, use_recommended_security=False, scorecard=True, security_policy=True)
    assert (tmp_path / "SECURITY.md").exists()
    assert (tmp_path / ".github" / "workflows" / "scorecard.yml").exists()
    readme = (tmp_path / "README.md").read_text()
    assert "api.scorecard.dev/projects/github.com/kasi-x/python-copier-template-example/badge" in readme


def test_template_readme_badges(tmp_path: Path):
    copy_project(tmp_path)  # example-answers.yml uses package_manager: uv
    readme = (tmp_path / "README.md").read_text()
    # only officially-documented tool badges: no unofficial/inferred ones
    # (e.g. uv, pixi have no official "used by" badge upstream)
    assert "astral-sh/ruff/main/assets/badge/v2.json" in readme
    assert "copier-org/copier/master/img/badge/badge-black.json" in readme
    # pre-commit is no longer shipped: its badge must not come back
    assert "pre--commit" not in readme
    assert "astral-sh/uv" not in readme
    assert "prefix-dev/pixi" not in readme
    assert "Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB" in readme


def test_pr_template_shipped(tmp_path: Path):
    copy_project(tmp_path)
    pr = tmp_path / ".github" / "PULL_REQUEST_TEMPLATE" / "pull_request_template.md"
    assert pr.exists()
    assert "Checks for reviewer" in pr.read_text()


@pytest.mark.heavy
@pytest.mark.network
def test_private_member_access(tmp_path: Path):
    code = """
class MyClass:
    def __init__(self):
        self.foo: int = 1
        self._bar: int = 2

obj = MyClass()
print(obj.foo)
print(obj._bar)
"""

    copy_project(tmp_path)
    run = make_venv(tmp_path)

    # Private member access should be allowed in tests
    test_file = tmp_path / "tests" / "test_private_access.py"
    with test_file.open("w") as stream:
        stream.write(code)
    run("ruff check")

    # Private member access should not be allowed in src
    src_file = tmp_path / "src" / "python_copier_template_example" / "private_access.py"
    with src_file.open("w") as stream:
        stream.write(code)
    with pytest.raises(AssertionError, match=r"private-member-access: Private member accessed: `_bar`"):
        run("ruff check")


@pytest.mark.heavy
@pytest.mark.network
def test_pep8_naming(tmp_path: Path):
    code = """
myVariable = "foo"
"""

    copy_project(tmp_path)
    run = make_venv(tmp_path)

    src_file = tmp_path / "src" / "python_copier_template_example" / "bad_example.py"
    with src_file.open("w") as stream:
        stream.write(code)
    with pytest.raises(AssertionError, match=r"mixed-case-variable-in-global-scope.*"):
        run("ruff check")


def test_basedpyright_works_in_none_typing_mode(tmp_path: Path):
    copy_project(tmp_path, strictness="none")
    pyproject = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    tasks = yaml.safe_load((tmp_path / "Taskfile.yml").read_text())["tasks"]

    # none: pytest + ruff (minimal rules) - no basedpyright, no type-checking env
    assert "basedpyright" not in pyproject["tool"]
    assert "ruff" in pyproject["tool"]
    assert "type-check" not in tasks


def test_basedpyright_works_in_basic_mode(tmp_path: Path):
    copy_project(tmp_path, strictness="basic")
    pyproject = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    tasks = yaml.safe_load((tmp_path / "Taskfile.yml").read_text())["tasks"]

    # basic: ruff but no type checking
    assert "ruff" in pyproject["tool"]
    assert "basedpyright" not in pyproject["tool"]
    assert "type-check" not in tasks


@pytest.mark.heavy
@pytest.mark.network
def test_basedpyright_works_with_external_deps(tmp_path: Path):
    copy_project(tmp_path)
    # Add an external dependency (regex insert -- log_library picks which
    # logging package, if any, already opens the `dependencies = [...]` array)
    pyproject_toml = tmp_path / "pyproject.toml"
    text = pyproject_toml.read_text()
    text, n = re.subn(r"dependencies = \[", 'dependencies = ["numpy", ', text, count=1)
    assert n == 1, "could not find dependencies array in generated pyproject.toml"
    pyproject_toml.write_text(text)
    # And some code that uses it
    src_file = tmp_path / "src" / "python_copier_template_example" / "example.py"
    src_file.write_text("""
import numpy as np

def is_big(arr: np.ndarray) -> bool:
    return arr.size > 0
""")
    # Ensure basedpyright is still happy
    run = make_venv(tmp_path)
    run("uvx --from go-task-bin task type-check")


def test_audit_isolated_from_type_check(tmp_path: Path):
    # pip-audit is network-dependent (OSV/PyPI): on-demand `audit` task,
    # never inside type-check/check so offline CI stays green.
    copy_project(tmp_path)
    tasks = yaml.safe_load((tmp_path / "Taskfile.yml").read_text())["tasks"]
    assert any("pip-audit" in str(command) for command in tasks["audit"]["cmds"])
    assert not any("pip-audit" in str(command) for command in tasks["type-check"]["cmds"]), (
        "type-check must stay runnable offline"
    )


def test_full_strictness_mode(tmp_path: Path):
    copy_project(tmp_path, strictness="full")

    # Check strict mode with Any-reporting is configured
    basedpyright = tomllib.loads((tmp_path / "pyproject.toml").read_text())["tool"]["basedpyright"]
    assert basedpyright["typeCheckingMode"] == "strict"
    assert basedpyright["reportAny"] is True


@pytest.mark.heavy
@pytest.mark.network
def test_works_with_pydocstyle(tmp_path: Path):
    # Use English docstrings (allow_japanese=False) so ruff's D415
    # (punctuation check) applies cleanly.
    copy_project(tmp_path, allow_japanese=False)
    pyproject_toml = tmp_path / "pyproject.toml"
    text = (
        pyproject_toml.read_text()
        .replace('"C4",', '"C4", "D",')  # Enable all pydocstyle
        .replace(
            '"tests/**/*" = [',
            '"tests/**/*" = [\n    "D",',
        )
    )
    # Add __init__.py as a separate key at the end of the per-file-ignores table
    text += '\n"__init__.py" = ["D104"]\n'
    pyproject_toml.write_text(text)

    # Ensure ruff is still happy
    run = make_venv(tmp_path)
    run("ruff check")


@pytest.mark.parametrize(
    "override",
    [
        {},
        {"docker": True},
        {"docker": True, "docker_debug": True},
        {"pypi": True},
        {"docs_type": "sphinx"},
        {"docs_type": "zensical"},
        {"docs_type": "great-docs"},
        {"package_manager": "pixi"},
    ],
)
def test_renovate_actions_match_what_is_shipped(override: dict, tmp_path: Path):
    # Generate a project with the given answers
    answers = {
        "docker": False,
        "docker_debug": False,
        "pypi": False,
        "docs_type": "README",
    }
    answers.update(override)
    copy_project(tmp_path, **answers)
    # Find the GitHub actions ignored by renovate (all github-actions
    # packageRules now that they are split per category, not one block)
    renovate_config_path = tmp_path / "renovate.json"
    renovate_config = json.loads(renovate_config_path.read_text())
    config_github_actions = set()
    for rule in renovate_config["packageRules"]:
        if rule.get("matchManagers") == ["github-actions"]:
            config_github_actions.update(rule.get("matchPackageNames", []))
    used_github_actions = set[str]()
    for workflow_file in (tmp_path / ".github" / "workflows").glob("*.yml"):
        workflow = yaml.safe_load(workflow_file.read_text())
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                action = step.get("uses")
                if action:
                    name = action.split("@")[0]
                    # docker:// steps track the bare image name in renovate
                    name = name.removeprefix("docker://")
                    used_github_actions.add(name)
    # Check they match
    assert used_github_actions == config_github_actions


def test_python_versions_match(tmp_path: Path):
    copy_project(tmp_path)
    # Grab the python versions from ci.yml
    ci_yaml = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(ci_yaml.read_text())
    python_versions = workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"]
    # Check .python-version is the first of these
    python_version_file = tmp_path / ".python-version"
    min_version = python_version_file.read_text().strip()
    assert python_versions[0] == min_version
    # Check pyproject.toml has correct requires-python and classifiers
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["requires-python"] == f">={min_version}"
    for version in python_versions:
        assert f"Programming Language :: Python :: {version}" in pyproject_toml["project"]["classifiers"]
