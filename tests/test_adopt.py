"""Tests for tools/adopt.py: adoption that can be undone.

The point of the driver is the guarantee, not the render: every test here
either checks the plan (ref judgement, dry run) or checks that a failed run
leaves the project exactly as it was.
"""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import adopt  # noqa: E402


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def make_project(root: Path) -> Path:
    """A minimal pre-existing project that collides with the template."""
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text("# MY OWN CI\n")
    (root / "README.md").write_text("# mine\n")
    (root / "pyproject.toml").write_text('[project]\nname = "legacy"\nversion = "0"\n')
    (root / "renovate.json").write_text('{"custom": true}\n')
    return root


def tree(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def test_resolve_ref_uses_a_tag_only_when_it_carries_the_questionnaire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The stale-tag trap, decided rather than assumed."""
    template = tmp_path / "template-repo"
    (template / "questions").mkdir(parents=True)
    (template / "copier.yml").write_text("---\n!include questions/a.yml\n")
    (template / "questions" / "a.yml").write_text("alpha:\n    type: str\n")
    git(template, "init", "-q", "-b", "main")
    git(template, "add", "-A")
    git(template, "commit", "-qm", "one question")
    git(template, "tag", "v1")
    monkeypatch.setattr(adopt, "TOP", template)

    ref, reason = adopt.resolve_ref()
    assert ref == "v1", "a tag with this questionnaire is the right default"
    assert "carries this questionnaire" in reason

    # the template grows a question the tag does not have -> the tag is stale
    (template / "questions" / "b.yml").write_text("beta:\n    type: str\n")
    (template / "copier.yml").write_text("---\n!include questions/a.yml\n---\n!include questions/b.yml\n")
    git(template, "add", "-A")
    git(template, "commit", "-qm", "second question")

    ref, reason = adopt.resolve_ref()
    assert ref == "main"
    assert "does not carry this questionnaire" in reason and "beta" in reason
    assert adopt.resolve_ref("HEAD") == ("HEAD", "requested explicitly")


def test_dry_run_writes_nothing(tmp_path: Path):
    project = make_project(tmp_path)
    before = tree(project)

    result = adopt.adopt(project, ref="HEAD", dry_run=True)

    assert result.ok and not result.applied
    assert result.mode == "adopt"
    assert result.skip == [".github/workflows/ci.yml", "renovate.json"]
    assert any("dry run" in note for note in result.notes)
    assert tree(project) == before


def test_adoption_keeps_existing_files_and_adds_the_rest(tmp_path: Path):
    project = make_project(tmp_path)

    result = adopt.adopt(project, ref="HEAD")

    assert result.ok and result.applied
    assert result.error is None
    assert (project / ".github" / "workflows" / "ci.yml").read_text() == "# MY OWN CI\n"
    assert (project / "renovate.json").read_text() == '{"custom": true}\n'
    assert (project / "README.md").read_text() == "# mine\n"
    assert (project / "pyproject.toml").read_text().startswith("[project]")
    assert (project / ".gitleaks.toml").exists()
    assert (project / ".github" / "workflows" / "_hygiene.yml").exists()
    assert sorted(result.unchanged) == [".github/workflows/ci.yml", "README.md", "pyproject.toml", "renovate.json"]
    assert result.created and not result.removed and not result.restored


def test_a_collision_that_was_not_skipped_rolls_the_project_back(tmp_path: Path):
    """The guarantee: a failed run leaves the project exactly as it was.

    `skip=[]` stands for any collision the plan did not cover (a protection
    token deselected, an answer-dependent path): copier stops on the first
    one, and everything it wrote before that stop is undone.
    """
    project = make_project(tmp_path)
    before = tree(project)

    result = adopt.adopt(project, ref="HEAD", skip=[])

    assert not result.ok and not result.applied
    assert result.error is not None and "InteractiveSessionError" in result.error
    assert result.removed, "files created before the stop are removed"
    assert tree(project) == before, "every file is back to its old bytes"
    directories = {str(path.relative_to(project)) for path in project.rglob("*") if path.is_dir()}
    assert directories == {".github", ".github/workflows"}, "not even an empty directory is left behind"
    assert any("rolled back" in note for note in result.notes)


def test_adoption_merges_the_template_dependencies(tmp_path: Path):
    """Dependencies are the one part of the adopter's config that is merged."""
    project = make_project(tmp_path)
    (project / "pyproject.toml").write_text(
        '[project]\nname = "legacy"\nversion = "0"\n# my pin\ndependencies = ["structlog>=9"]\n'
    )

    result = adopt.adopt(project, ref="HEAD")

    assert result.ok and result.deps is not None
    assert result.deps["added"]["dev"], "the dev toolchain is merged"
    assert result.deps["kept"]["runtime"] == ["structlog"], "the dependency they already declare is left alone"
    text = (project / "pyproject.toml").read_text()
    assert "# my pin" in text, "the adopter's file is edited, not replaced"
    assert '"structlog>=9"' in text, "their constraint survives"
    assert '"structlog' in text
    assert "[dependency-groups]" in text
    assert any("structlog" in line for line in result.deps["differing"]), "their pin wins, and is reported"


def test_runtime_dependencies_of_a_layer_are_merged(tmp_path: Path):
    """Adopting with a layer (web_api here) brings that layer's runtime deps."""
    project = make_project(tmp_path)
    (project / "pyproject.toml").write_text('[project]\nname = "legacy"\nversion = "0"\ndependencies = []\n')

    result = adopt.adopt(project, ref="HEAD", answers={"project_type": "web_api"})

    assert result.ok and result.deps is not None
    added = result.deps["added"]["runtime"]
    assert any(spec.startswith("fastapi") for spec in added), added
    assert any(spec.startswith("sqlalchemy") for spec in added), added
    assert (project / "app" / "main.py").is_file(), "the layer itself is rendered"
    assert "fastapi" in (project / "pyproject.toml").read_text()


def test_adoption_merges_gitignore_makefile_and_ci(tmp_path: Path):
    """The files an adopter usually already has are merged, not skipped."""
    project = make_project(tmp_path)
    (project / ".gitignore").write_text("*.pyc\n# mine\ncustom/\n")
    (project / "Makefile").write_text("mine:\n\techo mine\n")
    workflows = project / ".github" / "workflows"
    (workflows / "ci.yml").write_text("# MY OWN CI\n")

    result = adopt.adopt(
        project,
        ref="HEAD",
        answers={"use_recommended_toolchain": False, "package_manager": "uv", "task_runner": "make"},
    )

    assert result.ok
    merged = {entry["path"]: entry for entry in result.files_merged}
    assert any(path.endswith(".gitignore") for path in merged)
    assert set(merged).intersection({str(project / ".gitignore"), str(project / "Makefile")})

    assert (project / ".gitignore").read_text().startswith("*.pyc\n# mine\ncustom/\n")
    assert ".pytest_cache/" in (project / ".gitignore").read_text()
    assert (project / "Makefile").read_text().startswith("mine:\n\techo mine\n")
    assert "check:" in (project / "Makefile").read_text()
    assert (workflows / "ci.yml").read_text() == "# MY OWN CI\n", "their workflow is never rewritten"
    caller = workflows / "copier-ci.yml"
    assert caller.is_file() and "Copier CI" in caller.read_text()
    assert "name: my-ci" not in caller.read_text()


def test_adoption_merges_tool_config_but_not_project_paths(tmp_path: Path):
    project = make_project(tmp_path)
    (project / "pyproject.toml").write_text(
        '[project]\nname = "legacy"\nversion = "0"\n\n[tool.ruff]\nline-length = 100\n'
    )

    result = adopt.adopt(project, ref="HEAD")

    assert result.ok and result.tool_config is not None
    text = (project / "pyproject.toml").read_text()
    assert "line-length = 100" in text, "their setting survives"
    assert "[tool.ruff.lint]" in text and 'select = ["ALL"]' in text
    assert "src/" not in text.split("[dependency-groups]")[0].split("[tool.ruff.lint]")[1][:200]
    assert any("tool.ruff.line-length" in line for line in result.tool_config["kept"])
    assert result.tool_config["needs_your_value"], "path-shaped values are reported, not copied"


def test_confirmation_yes_applies_the_merges(tmp_path: Path):
    project = make_project(tmp_path)
    (project / ".gitignore").write_text("*.pyc\n")

    result = adopt.adopt(project, ref="HEAD", ask=lambda _question: "yes")

    assert result.ok and not result.cancelled
    assert "__pycache__" in (project / ".gitignore").read_text()


def test_confirmation_no_keeps_the_render_and_skips_the_merges(tmp_path: Path):
    project = make_project(tmp_path)
    (project / ".gitignore").write_text("*.pyc\n")

    result = adopt.adopt(project, ref="HEAD", ask=lambda _question: "no")

    assert result.ok and not result.cancelled
    assert (project / ".gitignore").read_text() == "*.pyc\n", "their file is untouched"
    assert (project / ".gitleaks.toml").exists(), "the render still happened"
    assert any("merges skipped" in note for note in result.notes)


def test_confirmation_cancel_rolls_the_render_back(tmp_path: Path):
    project = make_project(tmp_path)
    before = tree(project)

    result = adopt.adopt(project, ref="HEAD", ask=lambda _question: "cancel")

    assert result.cancelled and not result.ok and result.error is None
    assert tree(project) == before, "nothing of the adoption is left behind"
    assert any("cancelled" in note for note in result.notes)


def test_confirmation_can_approve_a_project_specific_value(tmp_path: Path):
    """The values the merge refuses to copy blind are exactly what to ask about."""
    project = make_project(tmp_path)
    (project / "src" / "legacy").mkdir(parents=True)
    (project / "src" / "legacy" / "__init__.py").write_text("")
    (project / "pyproject.toml").write_text('[project]\nname = "legacy"\nversion = "0"\ndependencies = []\n')

    asked: list[str] = []

    def answer(question: str) -> str:
        asked.append(question)
        return "yes"

    result = adopt.adopt(project, ref="HEAD", ask=answer)

    assert result.ok
    assert any("tool.basedpyright.include" in question for question in asked), asked[:3]
    text = (project / "pyproject.toml").read_text()
    assert "src/legacy" in text, "the approved value is the adapted one, for their layout"
    assert "src/my_package" not in text


def test_confirmation_all_approves_every_remaining_value(tmp_path: Path):
    """One "all" answers the rest of the project-specific questions."""
    project = make_project(tmp_path)
    (project / "src" / "legacy").mkdir(parents=True)
    (project / "src" / "legacy" / "__init__.py").write_text("")
    (project / "pyproject.toml").write_text('[project]\nname = "legacy"\nversion = "0"\ndependencies = []\n')

    asked: list[str] = []

    def answer(question: str) -> str:
        asked.append(question)
        return "all" if question.startswith("add ") else "yes"

    result = adopt.adopt(project, ref="HEAD", ask=answer)

    assert result.ok
    value_questions = [question for question in asked if question.startswith("add ")]
    assert len(value_questions) == 1, "everything after the first 'all' is approved without asking"
    text = (project / "pyproject.toml").read_text()
    assert "src/legacy" in text
    assert "testpaths" in text, "later values were approved too"


def test_confirmation_can_approve_appending_to_the_taskfile(tmp_path: Path):
    """The task list is offered and, once approved, appended."""
    project = make_project(tmp_path)
    (project / "Taskfile.yml").write_text("version: '3'\n\ntasks:\n  mine:\n    cmds:\n      - echo mine\n")

    asked: list[str] = []

    def answer(question: str) -> str:
        asked.append(question)
        return "yes"

    result = adopt.adopt(
        project,
        ref="HEAD",
        ask=answer,
        answers={"use_recommended_toolchain": False, "package_manager": "uv", "task_runner": "task"},
    )

    assert result.ok
    assert any("append these tasks to your Taskfile.yml" in question for question in asked)
    document = yaml.safe_load((project / "Taskfile.yml").read_text())
    assert "mine" in document["tasks"], "their task survives"
    assert "lint" in document["tasks"], "the approved tasks were appended"


def test_taskfile_is_left_alone_without_approval(tmp_path: Path):
    project = make_project(tmp_path)
    (project / "Taskfile.yml").write_text("version: '3'\n\ntasks:\n  mine:\n    cmds:\n      - echo mine\n")
    before = (project / "Taskfile.yml").read_text()

    result = adopt.adopt(project, ref="HEAD", ask=lambda _question: "no")

    assert result.ok
    assert (project / "Taskfile.yml").read_text() == before


def test_adoption_does_not_merge_when_asked_not_to(tmp_path: Path):
    project = make_project(tmp_path)
    before = (project / "pyproject.toml").read_text()

    result = adopt.adopt(project, ref="HEAD", merge_generated=False)

    assert result.ok and result.deps is None
    assert (project / "pyproject.toml").read_text() == before


def test_dry_run_reports_the_dependency_plan_without_writing(tmp_path: Path):
    project = make_project(tmp_path)
    before = (project / "pyproject.toml").read_text()

    result = adopt.adopt(project, ref="HEAD", dry_run=True)

    assert result.ok and result.deps is not None
    assert "structlog" in result.deps["added"]["runtime"]
    assert (project / "pyproject.toml").read_text() == before


def test_merge_verification_detects_a_rewritten_requirement(tmp_path: Path):
    """The guard behind the rollback: a merge may only add."""
    project = make_project(tmp_path)
    target = project / "pyproject.toml"
    target.write_text('[project]\nname = "legacy"\nversion = "0"\ndependencies = ["httpx>=0.20"]\n')
    before = target.read_bytes()

    assert adopt.merge_problem(target, before) is None, "unchanged file is fine"

    target.write_text('[project]\nname = "legacy"\nversion = "0"\ndependencies = ["httpx>=0.20", "structlog"]\n')
    assert adopt.merge_problem(target, before) is None, "appending is not a violation"

    target.write_text('[project]\nname = "legacy"\nversion = "0"\ndependencies = ["httpx>=0.99"]\n')
    problem = adopt.merge_problem(target, before)
    assert problem is not None and "httpx" in problem

    target.write_text("this is not toml\n")
    assert "does not parse" in (adopt.merge_problem(target, before) or "")


def test_refuses_a_project_this_template_already_generated(tmp_path: Path):
    (tmp_path / ".copier-answers.yml").write_text("_src_path: https://github.com/kasi-x/python-copier-template.git\n")
    with pytest.raises(adopt.AdoptError, match="already generated"):
        adopt.adopt(tmp_path, ref="HEAD")


def test_refuses_a_foreign_template_until_takeover(tmp_path: Path):
    make_project(tmp_path)
    (tmp_path / ".copier-answers.yml").write_text("_src_path: https://github.com/other/template.git\n")
    with pytest.raises(adopt.OwnershipError, match="another copier template"):
        adopt.adopt(tmp_path, ref="HEAD")

    result = adopt.adopt(tmp_path, ref="HEAD", takeover=True, dry_run=True)
    assert result.ok and result.mode == "adopt"


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    project = make_project(tmp_path)
    assert adopt.main([str(project), "--ref", "HEAD", "--dry-run", "--no-merge"]) == 0
    assert "dry run" in capsys.readouterr().out

    # an uncovered collision: exit 1, and the project is back to its old self
    before = tree(project)
    assert adopt.main([str(project), "--ref", "HEAD", "--no-merge", "--skip", "nothing-actually-collides"]) == 1
    assert "FAILED" in capsys.readouterr().out
    assert tree(project) == before

    other = tmp_path / "other"
    other.mkdir()
    (other / ".copier-answers.yml").write_text("_src_path: https://github.com/other/template.git\n")
    assert adopt.main([str(other), "--ref", "HEAD"]) == 3
    assert "another copier template" in capsys.readouterr().err


def test_main_rejects_a_missing_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    assert adopt.main([str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err
