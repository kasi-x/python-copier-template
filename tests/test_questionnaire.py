"""Tests for tools/questionnaire.py: the questionnaire as data.

Parsing is exercised against a synthetic config (so the include order and the
field shapes are pinned exactly) plus a few assertions on the real
questionnaire, which is what the MCP tools and the docs generator consume.
"""

import json
import sys
from pathlib import Path

import pytest

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import questionnaire  # noqa: E402


def write_config(tmp_path: Path) -> Path:
    (tmp_path / "questions").mkdir()
    (tmp_path / "questions" / "a.yml").write_text(
        "gate:\n"
        "    type: bool\n"
        "    default: true\n"
        "    help: |\n"
        "        Use the recommended things?\n"
        "        Recommended: all of them.\n"
    )
    (tmp_path / "questions" / "b.yml").write_text(
        "kind:\n"
        "    type: str\n"
        '    when: "{{ gate }}"\n'
        "    choices: [one, two]\n"
        "    default: one\n"
        "    help: Pick a kind.\n"
    )
    (tmp_path / "copier.yml").write_text(
        "---\n"
        "project_type:\n"
        "    type: str\n"
        "    choices:\n"
        "        Library: library\n"
        "        CLI: cli\n"
        "    default: library\n"
        "---\n"
        "# a gate fragment\n"
        "!include questions/a.yml\n"
        "---\n"
        "internal_thing:\n"
        "    type: bool\n"
        "    when: false\n"
        "    default: \"{{ project_type == 'cli' }}\"\n"
        "---\n"
        "!include questions/b.yml\n"
        "---\n"
        "_subdirectory: template\n"
        "_skip_if_exists:\n"
        "    - CHANGELOG.md\n"
    )
    return tmp_path / "copier.yml"


def test_ask_order_follows_the_includes(tmp_path: Path):
    questions, settings = questionnaire.load_questions(write_config(tmp_path))
    assert [q.name for q in questions] == ["project_type", "gate", "internal_thing", "kind"]
    assert settings == {"_subdirectory": "template", "_skip_if_exists": ["CHANGELOG.md"]}


def test_question_fields_are_reported_as_written(tmp_path: Path):
    questions, _ = questionnaire.load_questions(write_config(tmp_path))
    by_name = {q.name: q for q in questions}

    assert by_name["project_type"].choices == ["library", "cli"]
    assert by_name["project_type"].labels == ["Library", "CLI"]
    assert by_name["gate"].type == "bool"
    assert by_name["gate"].help.startswith("Use the recommended things?")
    assert by_name["gate"].source == "a.yml"
    assert by_name["project_type"].source.startswith("copier.yml")
    # `when: false` is a derived variable, not a question
    assert by_name["internal_thing"].internal is True
    assert by_name["kind"].internal is False
    assert by_name["kind"].when == "{{ gate }}"


def test_block_scalar_choices_are_reported_as_a_template(tmp_path: Path):
    (tmp_path / "questions").mkdir()
    (tmp_path / "questions" / "a.yml").write_text(
        "kind:\n    type: str\n    choices: |\n        {%- if x %}\n        - one\n        {%- else %}\n        - two\n"
    )
    (tmp_path / "copier.yml").write_text("---\n!include questions/a.yml\n")
    questions, _ = questionnaire.load_questions(tmp_path / "copier.yml")
    assert questions[0].choices == []
    assert questions[0].choices_template is not None
    assert "- one" in questions[0].choices_template


def test_nested_include_is_rejected(tmp_path: Path):
    (tmp_path / "questions").mkdir()
    (tmp_path / "questions" / "a.yml").write_text("---\n!include b.yml\n")
    (tmp_path / "copier.yml").write_text("---\n!include questions/a.yml\n")
    with pytest.raises(questionnaire.QuestionnaireError, match="nested !include"):
        questionnaire.load_questions(tmp_path / "copier.yml")


def test_misplaced_include_is_rejected(tmp_path: Path):
    (tmp_path / "questions").mkdir()
    (tmp_path / "questions" / "a.yml").write_text("thing:\n    type: str\n")
    (tmp_path / "copier.yml").write_text("---\nthing:\n    type: str\n!include questions/a.yml\n")
    with pytest.raises(questionnaire.QuestionnaireError, match="only content"):
        questionnaire.load_questions(tmp_path / "copier.yml")


def test_missing_include_is_rejected(tmp_path: Path):
    (tmp_path / "copier.yml").write_text("---\n!include questions/nope.yml\n")
    with pytest.raises(questionnaire.QuestionnaireError, match="not found"):
        questionnaire.load_questions(tmp_path / "copier.yml")


def test_real_questionnaire_reads_in_ask_order():
    questions, settings = questionnaire.load_questions()
    names = [q.name for q in questions]

    assert names[0] == "project_type"
    assert names[1] == "existing_project", "adoption mode is asked right after project_type"
    assert len(names) >= 108
    assert len(names) == len(set(names)), "question names are unique"
    assert all(name.isidentifier() for name in names)
    assert "_subdirectory" in settings and settings["_subdirectory"] == "template"
    assert "CHANGELOG.md" in settings["_skip_if_exists"]
    # both dynamic-choice questions are the ones that narrow themselves
    templated = sorted(q.name for q in questions if q.choices_template is not None)
    assert templated == ["oj_kind", "package_manager"]
    assert any(q.name == "use_recommended_toolchain" and not q.internal for q in questions)
    assert sum(1 for q in questions if q.internal) >= 40, "derived variables stay out of the asked set"


def test_main_prints_names_and_filters_internal(capsys: pytest.CaptureFixture[str]):
    assert questionnaire.main(["--names"]) == 0
    all_names = capsys.readouterr().out.split()
    assert questionnaire.main(["--names", "--asked"]) == 0
    asked = capsys.readouterr().out.split()
    assert len(asked) < len(all_names)
    assert "project_type" in asked

    assert questionnaire.main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["questions"]) == len(all_names)
    assert payload["questions"][0]["name"] == "project_type"
    assert payload["settings"]["_subdirectory"] == "template"


def test_main_reports_a_broken_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    broken = tmp_path / "copier.yml"
    broken.write_text("---\nthing: [unclosed\n")
    assert questionnaire.main(["--config", str(broken), "--names"]) == 2
    assert "cannot read questionnaire" in capsys.readouterr().err
