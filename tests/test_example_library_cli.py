"""The default render and the bare project types: the example-answers
library, script, and the repo-name / project_type refusals."""

import re
import tomllib
from pathlib import Path

import pytest

from support import TOP
from support import copy_project
from support import copy_project_recommended
from support import make_venv
from support import run_pipe


@pytest.mark.heavy
@pytest.mark.network
def test_template_defaults(tmp_path: Path):
    copy_project(tmp_path)
    run = make_venv(tmp_path)
    container_doc = tmp_path / "docs" / "how-to" / "run-container.md"
    pyproject_toml = tmp_path / "pyproject.toml"
    assert container_doc.exists()
    # example-answers.yml uses strictness: recommended
    assert 'typeCheckingMode = "recommended"' in pyproject_toml.read_text()
    run("uvx --from go-task-bin task check")
    if not run_pipe("git tag --points-at HEAD"):
        # Only run linkcheck if not on a tag, as the CI might not have pushed
        # the docs for this tag yet, so we will fail. `-b linkcheck` is
        # sphinx-specific; example-answers uses zensical so just build docs.
        run("uvx --from go-task-bin task docs")
    run("uvx --from build pyproject-build")
    run("uvx twine check --strict dist/*")


def test_template_script_type(tmp_path: Path):
    copy_project(tmp_path, project_type="script")
    # Minimal: flat package at repo root (no src/), no notebooks
    pkg = tmp_path / "python_copier_template_example"
    assert (pkg / "__init__.py").exists()
    assert not (tmp_path / "src").exists()
    assert not (tmp_path / "notebooks").exists()
    # No DS extras
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert "optional-dependencies" not in pyproject_toml.get("project", {})
    # Regression: the flat-layout copies of __main__.py/logging_setup.py used
    # to wrap their .jinja suffix *inside* the `{% if %}` filename condition
    # (`...py.jinja{% endif %}` instead of `...py{% endif %}.jinja`), so
    # copier never recognised them as templates -- they were copied verbatim,
    # keeping a literal .jinja suffix and unrendered `{{ }}`/`{% %}` content.
    assert not list(pkg.glob("*.jinja"))
    assert "{% if" not in (pkg / "__main__.py").read_text()
    assert "{% if" not in (pkg / "logging_setup.py").read_text()


def test_template_recommended_settings(tmp_path: Path):
    copy_project_recommended(tmp_path, project_type="data_science")
    # Accepting every "use the recommended ...?" gate still generates a
    # working project, using only the template's built-in defaults.
    assert (tmp_path / "pyproject.toml").exists()
    # use_gpu defaults to true for data_science -> Dockerfile.gpu present
    assert (tmp_path / "Dockerfile.gpu").exists()
    # the recommended license is MIT
    assert "MIT License" in (tmp_path / "LICENSE").read_text()
    pyproject_toml = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject_toml["project"]["license"] == "MIT"


def test_template_github_org_reflected(tmp_path: Path):
    copy_project(tmp_path, github_org="myorg")
    # github_org is used in generated URLs and badges
    readme = (tmp_path / "README.md").read_text()
    assert "myorg" in readme
    assert "DiamondLightSource" not in readme


def test_bad_repo_name(tmp_path: Path):
    with pytest.raises(ValueError) as excinfo:
        copy_project(tmp_path, repo_name="bad:thing")
    assert "bad:thing" in str(excinfo.value), "the refusal names the rejected repo name"


def test_django_is_not_a_project_type(tmp_path: Path):
    # The web_django trap choice is gone: selecting it used to render and then
    # abort from a post-generation task, and it is now rejected before
    # anything is written.
    with pytest.raises(ValueError):
        copy_project(tmp_path, project_type="web_django")


def test_dots_in_package_name(tmp_path: Path):
    copy_project(tmp_path, repo_name="dots.in.name")


def test_gitignore_same():
    # the gated .gitignore template is conditional (data_science / kaggle /
    # ros2 blocks render per project type); the root .gitignore is the
    # union of every conditional branch, so the template repo itself
    # ignores everything any generated project could produce.
    # Compare normalized line sets (jinja tags stripped) in both
    # directions: exact parity catches stale root-only lines (e.g. a
    # removed input//exp/) and missing template lines, which a one-way
    # substring check would hide. the gated .gitignore template shares its
    # CTF / scraping bodies via {% include %} (_shared/gitignore-*.jinja),
    # so those are inlined before normalizing.
    def normalized(path: Path) -> set[str]:
        lines = set()
        text = path.read_text()
        for included in re.findall(r'{%\s*include\s*"([^"]+)"\s*%}', text):
            text += "\n" + (TOP / included).read_text()
        for line in text.splitlines():
            stripped = re.sub(r"{%.*?%}|{#.*?#}", "", line).strip()
            if not stripped or stripped.startswith("#"):
                continue
            lines.add(stripped)
        return lines

    template = normalized(
        TOP
        / "template"
        / "{% if not existing_project or 'gitignore' not in adopt_protect %}.gitignore{% endif %}.jinja"
    )
    root = normalized(TOP / ".gitignore")
    assert template - root == set(), f"missing from root .gitignore: {sorted(template - root)}"
    assert root - template == set(), f"stale in root .gitignore: {sorted(root - template)}"
