"""Tests for tools/detect.py: which mode fits a target, and what it has.

The detection runs against synthetic trees (deterministic, offline) plus a
few assertions on the real template/ tree, so the "what would the template
write over" mapping cannot silently drift from the template's own
`existing_project` / `adopt_protect` conditions.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from copier import run_copy

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import detect  # noqa: E402


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def make_legacy_project(root: Path) -> Path:
    """A small, realistic pre-existing project (adopt target)."""
    (root / "src" / "legacy").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "docs").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "legacy"\ndescription = "The legacy service"\n'
        'requires-python = ">=3.9"\nauthors = [{ name = "Ada", email = "ada@example.com" }]\n\n'
        "[tool.ruff]\nline-length = 100\n"
    )
    (root / "src" / "legacy" / "__init__.py").write_text("")
    (root / "tests" / "test_legacy.py").write_text("")
    (root / "docs" / "index.md").write_text("# docs\n")
    (root / "README.md").write_text("# legacy\n")
    (root / "LICENSE").write_text("Apache License\n")
    (root / "CHANGELOG.md").write_text("# Changelog\n")
    (root / ".gitignore").write_text("*.pyc\n")
    (root / ".python-version").write_text("3.9\n")
    (root / "justfile").write_text("lint:\n")
    (root / ".github" / "workflows" / "ci.yml").write_text("# MY OWN CI\n")
    return root


def test_empty_directory_is_fresh(tmp_path: Path):
    detection = detect.detect(tmp_path)
    assert detection.mode == "fresh"
    assert detection.suggested_answers == {"existing_project": False}
    assert detection.kept == [] and detection.collisions == []


def test_missing_directory_is_fresh(tmp_path: Path):
    detection = detect.detect(tmp_path / "not-created-yet")
    assert detection.mode == "fresh"
    assert detection.suggested_answers == {"existing_project": False}


def test_git_only_directory_is_fresh(tmp_path: Path):
    git(tmp_path, "init", "-q")
    assert detect.detect(tmp_path).mode == "fresh"


def test_existing_project_is_adopt(tmp_path: Path):
    make_legacy_project(tmp_path)
    detection = detect.detect(tmp_path)

    assert detection.mode == "adopt"
    # Every protectable thing this project has is offered as protected.
    assert detection.suggested_answers["existing_project"] is True
    assert detection.suggested_answers["adopt_protect"] == [
        "readme",
        "license",
        "pyproject",
        "gitignore",
        "python_version",
        "scaffold",
        "docs",
    ]
    # The adopter's own files are kept ...
    for kept in ("README.md", "LICENSE", "pyproject.toml", ".gitignore", ".python-version", "CHANGELOG.md"):
        assert kept in detection.kept, f"{kept} should be kept"
    assert "justfile" in detection.kept, "task-runner files are never written in adopt mode"
    # ... and infrastructure the template always ships is a collision.
    assert ".github/workflows/ci.yml" in detection.collisions
    assert ".gitleaks.toml" not in detection.collisions, "absent files are additions, not collisions"
    assert ".gitleaks.toml" in detection.added


def test_facts_and_derived_answers(tmp_path: Path):
    make_legacy_project(tmp_path)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "remote", "add", "origin", "git@github.com:acme/legacy.git")
    detection = detect.detect(tmp_path)

    fact_keys = {fact.key for fact in detection.facts}
    assert {"vcs", "packaging", "python", "layout", "tests", "task runner", "ci", "quality", "docs"} <= fact_keys
    answers = detection.suggested_answers
    assert answers["package_name"] == "legacy"
    assert answers["description"] == "The legacy service"
    assert answers["git_platform"] == "github.com"
    assert answers["github_org"] == "acme"
    assert answers["repo_name"] == "legacy"
    assert answers["author_name"] == "Ada"
    assert answers["author_email"] == "ada@example.com"


def test_answers_are_not_guessed_for_shape_questions(tmp_path: Path):
    """SPEC-adoption §12: no project_type / include_* inference from code."""
    make_legacy_project(tmp_path)
    answers = detect.detect(tmp_path).suggested_answers
    assert not {"project_type", "include_mcp", "include_data_science", "docs_type", "strictness"} & set(answers)


def test_generated_project_is_update(tmp_path: Path):
    (tmp_path / ".copier-answers.yml").write_text(
        "_commit: 5.4.0-1-gabcdef\n_src_path: https://github.com/kasi-x/python-copier-template.git\n"
        "project_type: library\n"
    )
    assert detect.detect(tmp_path).mode == "update"


def test_local_clone_of_this_template_is_update(tmp_path: Path):
    """A clone records a local path in _src_path; ask the clone where it came from."""
    clone = tmp_path / "a-clone-with-an-unrelated-name"
    clone.mkdir()
    git(clone, "init", "-q")
    git(clone, "remote", "add", "origin", str(TOP))
    target = tmp_path / "project"
    target.mkdir()
    (target / ".copier-answers.yml").write_text(f"_src_path: {clone}\n_commit: abc\n")
    assert detect.detect(target).mode == "update"


def test_other_template_is_foreign(tmp_path: Path):
    (tmp_path / ".copier-answers.yml").write_text("_src_path: https://github.com/other/template.git\n")
    assert detect.detect(tmp_path).mode == "foreign"


def test_answers_file_refused_for_update(tmp_path: Path):
    (tmp_path / ".copier-answers.yml").write_text("_src_path: https://github.com/kasi-x/python-copier-template.git\n")
    out = tmp_path / "answers.yml"
    assert detect.main([str(tmp_path), "--answers", str(out)]) == 2
    assert not out.exists()


def test_answers_file_written_for_adopt(tmp_path: Path):
    make_legacy_project(tmp_path)
    out = tmp_path / "answers.yml"
    assert detect.main([str(tmp_path), "--answers", str(out), "--json"]) == 0
    text = out.read_text()
    assert "existing_project: true" in text
    assert "adopt_protect:" in text
    assert "package_name: legacy" in text
    assert "\nproject_type" not in text, "shape questions must not be invented"


def test_synthetic_template_conditions_are_parsed(tmp_path: Path):
    template = tmp_path / "template"

    def place(relative: str) -> None:
        path = template / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")

    place("{% if not existing_project %}README.md{% endif %}.jinja")
    place("{% if not existing_project or 'gitignore' not in adopt_protect %}.gitignore{% endif %}.jinja")
    place("{% if not existing_project %}docs{% endif %}/{% if docs %}index.md{% endif %}")
    place(".gitleaks.toml")
    place("{{ package_name }}/__init__.py")
    outputs = {output.path: output for output in detect.template_outputs(template)}

    assert set(outputs) == {"README.md", ".gitignore", "docs/index.md", ".gitleaks.toml"}
    assert outputs["README.md"].token == "readme"
    assert outputs[".gitignore"].token == "gitignore"
    assert outputs[".gitleaks.toml"].token is None

    all_protected = dict.fromkeys(detect.PROTECT_TOKENS, True)
    assert detect.render_state(outputs["README.md"], all_protected) == "omit"
    assert detect.render_state(outputs[".gitignore"], all_protected) == "omit"
    assert detect.render_state(outputs[".gitleaks.toml"], all_protected) == "overwrite"
    # Deselecting a token re-enables that file.
    assert detect.render_state(outputs["README.md"], {**all_protected, "readme": False}) == "overwrite"
    assert detect.render_state(outputs[".gitignore"], {**all_protected, "gitignore": False}) == "overwrite"


def test_real_template_protects_its_own_files():
    """The mapping holds for whichever protection condition the tree has now."""
    outputs = {output.path: output for output in detect.template_outputs(detect.TEMPLATE_DIR)}
    all_protected = dict.fromkeys(detect.PROTECT_TOKENS, True)

    assert "README.md" in outputs, "template must be able to render README.md"
    assert "pyproject.toml" in outputs
    assert ".gitleaks.toml" in outputs
    for path in ("README.md", "pyproject.toml", ".gitleaks.toml"):
        assert outputs[path].token in detect.PROTECT_TOKENS or path == ".gitleaks.toml"
    assert detect.render_state(outputs["README.md"], all_protected) == "omit"
    assert detect.render_state(outputs["pyproject.toml"], all_protected) == "omit"
    assert detect.render_state(outputs[".gitleaks.toml"], all_protected) == "overwrite"
    assert "CHANGELOG.md" in detect.skip_if_exists(detect.TEMPLATE_DIR)
    # Several branches can render the same path; it is reported once.
    paths = [output.path for output in detect.template_outputs(detect.TEMPLATE_DIR)]
    assert len(paths) == len(set(paths))


def test_copier_template_directory_is_flagged(tmp_path: Path):
    (tmp_path / "copier.yml").write_text("project_type:\n    type: str\n")
    (tmp_path / "template").mkdir()
    detection = detect.detect(tmp_path)
    assert detection.mode == "adopt"
    assert any("copier template" in note for note in detection.notes)


def test_answers_omit_questions_the_template_does_not_ask(tmp_path: Path):
    """A derived value the questionnaire does not declare must not be emitted."""
    template = tmp_path / "template"
    template.mkdir()
    (template / "README.md").write_text("x")
    (tmp_path / "questions").mkdir()
    (tmp_path / "questions" / "adoption.yml").write_text("existing_project:\n    type: bool\n")
    (tmp_path / "copier.yml").write_text("project_type:\n    type: str\n")

    target = make_legacy_project(tmp_path / "project")
    detection = detect.detect(target, template)

    assert detection.suggested_answers == {"existing_project": True}, "only declared questions may be answered"
    assert detect.template_questions(template) == {"existing_project", "project_type"}


def test_real_template_declares_the_answered_questions():
    asked = detect.template_questions(detect.TEMPLATE_DIR)
    assert {"existing_project", "project_type", "package_name", "git_platform", "github_org"} <= asked


def test_foreign_template_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """A project another template manages is a refusal, not an adoption."""
    (tmp_path / ".copier-answers.yml").write_text("_src_path: https://github.com/other/template.git\n_commit: v9.9.9\n")
    out = tmp_path / "answers.yml"
    assert detect.main([str(tmp_path), "--answers", str(out)]) == 3
    assert not out.exists(), "a refused target must not get an answers file"
    report = capsys.readouterr().out
    assert "STOP" in report
    assert "https://github.com/other/template.git" in report
    assert "--takeover" in report

    # --json still reports (an agent needs foreign_src), and still refuses.
    capsys.readouterr()
    assert detect.main([str(tmp_path), "--json"]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "foreign"
    assert payload["foreign_src"] == "https://github.com/other/template.git"


def test_takeover_adopts_over_a_foreign_template(tmp_path: Path):
    (tmp_path / ".copier-answers.yml").write_text("_src_path: https://github.com/other/template.git\n")
    (tmp_path / "README.md").write_text("# mine\n")

    detection = detect.detect(tmp_path, takeover=True)
    assert detection.mode == "adopt"
    assert detection.took_over is True
    assert any("taking over" in note for note in detection.notes)
    assert detection.suggested_answers["existing_project"] is True
    assert "README.md" in detection.kept

    out = tmp_path / "answers.yml"
    assert detect.main([str(tmp_path), "--takeover", "--answers", str(out)]) == 0
    assert "existing_project: true" in out.read_text()


def test_collisions_are_the_skip_list(tmp_path: Path):
    """The collisions are exactly what the adopter must --skip to keep them."""
    make_legacy_project(tmp_path)
    detection = detect.detect(tmp_path)
    assert detection.collisions == [".github/workflows/ci.yml"]
    assert detection.skip == detection.collisions
    assert ".gitleaks.toml" not in detection.skip, "absent files are additions"


def test_report_prints_a_runnable_skip_recipe(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    make_legacy_project(tmp_path)
    (tmp_path / "renovate.json").write_text("{}")
    assert detect.main([str(tmp_path)]) == 0
    report = capsys.readouterr().out
    assert "--skip .github/workflows/ci.yml" in report
    assert "--skip renovate.json" in report
    assert "--data-file answers.yml" in report

    assert detect.main([str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["skip"] == [".github/workflows/ci.yml", "renovate.json"]


def test_skip_recipe_keeps_existing_files_and_adds_the_rest(tmp_path: Path):
    """The recipe the report prints, run for real.

    `--skip <path>` is copier's "do not write this over an existing file", so
    the adopter's files survive while everything else is still added. This is
    the contract `skip` exists for; the collisions are its input.
    """
    project = make_legacy_project(tmp_path)
    (project / "renovate.json").write_text("{}\n")
    detection = detect.detect(project)
    assert detection.skip == [".github/workflows/ci.yml", "renovate.json"]

    run_copy(
        src_path=str(TOP),
        dst_path=project,
        data=detection.suggested_answers,
        vcs_ref="HEAD",
        unsafe=True,
        defaults=True,
        quiet=True,
        skip_if_exists=detection.skip,
    )

    assert (project / ".github/workflows" / "ci.yml").read_text() == "# MY OWN CI\n"
    assert (project / "renovate.json").read_text() == "{}\n"
    assert (project / "README.md").read_text() == "# legacy\n", "protected by existing_project"
    assert (project / "pyproject.toml").read_text().startswith("[project]"), "protected by existing_project"
    # the infrastructure the adopter did not have is still added
    assert (project / ".gitleaks.toml").exists()
    assert (project / ".github" / "workflows" / "_hygiene.yml").exists()
    assert (project / ".copier-answers.yml").exists()


def test_report_and_json_render(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    make_legacy_project(tmp_path)
    assert detect.main([str(tmp_path), "--json"]) == 0
    payload = capsys.readouterr().out
    assert '"mode": "adopt"' in payload
    assert '"collisions"' in payload

    assert detect.main([str(tmp_path)]) == 0
    report = capsys.readouterr().out
    assert "COLLISIONS" in report
    assert ".github/workflows/ci.yml" in report
