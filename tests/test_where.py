"""`architekton/where.py`: every file a question touches, from the question graph and the payload's Jinja.

The report is how a newcomer finds the files to edit, so each group is
pinned against a file that must be in it: if a refactor moves the payload
or renames a fragment, these fail instead of the report going quietly empty.
"""

import sys
from pathlib import Path

import pytest

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_cli.py does the same to reach architekton/
    sys.path.insert(0, str(TOP))

from architekton import cli  # noqa: E402
from architekton import question_graph  # noqa: E402
from architekton import where  # noqa: E402


def test_a_question_reports_its_fragment_feeds_and_payload():
    """task_runner: defined in the toolchain area, fed into runner_* internals, gating the runner files."""
    hits = where.touchpoints("task_runner")
    assert hits.kind == question_graph.QUESTION
    assert hits.defined.startswith("questions/06-toolchain.yml:")
    assert "task_runner_effective" in hits.feeds
    assert any(row.startswith("template/justfile.gate") and row.endswith("  justfile") for row in hits.file_gated)
    assert "partials/tasks-model.jinja" in hits.partials
    assert "tests/test_task_runners.py" in hits.tests


def test_a_derived_value_follows_its_own_feeds():
    """A gate read through an internal still counts: docs feeds render_docs, which gates docs/."""
    hits = where.touchpoints("docs")
    assert hits.kind == question_graph.INTERNAL
    assert "render_docs" in hits.feeds
    assert any(row.endswith("  docs") for row in hits.file_gated)
    assert any("docs/.gate" in row for row in hits.file_gated)


def test_presets_are_found_by_key():
    """include_sentry is pinned by the bare preset."""
    assert "presets/bare.yml" in where.touchpoints("include_sentry").presets


def test_a_unique_fragment_resolves_to_the_full_name():
    """`sentry` is enough: one setting contains it."""
    assert where.touchpoints("sentry").name == "include_sentry"


def test_an_ambiguous_fragment_lists_the_candidates():
    """`task_runner` alone is exact; `runner` matches several and says which."""
    with pytest.raises(where.WhereError, match="task_runner_effective"):
        where.resolve("runner", question_graph.build_graph())


def test_an_unknown_name_suggests_close_matches():
    """A typo gets the nearest names, not an empty report."""
    with pytest.raises(where.WhereError, match="Did you mean: task_runner"):
        where.resolve("taskrunner", question_graph.build_graph())


def test_prose_is_not_a_read():
    """Only Jinja code counts: a sentence mentioning `docs` does not make a file a docs file."""
    assert where.jinja_reads("see the docs for details") == set()
    assert "docs" in where.jinja_reads("{% if docs %}x{% endif %}")
    assert "secrets" not in where.jinja_reads("${{ secrets.TOKEN }}")


def test_cli_where_prints_the_report(capsys: pytest.CaptureFixture[str]):
    """`architekton-py where NAME` is the same report as the module."""
    assert cli.main(["where", "task_runner"]) == 0
    out = capsys.readouterr().out
    assert "questions/06-toolchain.yml" in out
    assert "Then run:" in out


def test_cli_where_rejects_an_unknown_name(capsys: pytest.CaptureFixture[str]):
    """An unknown name exits 2 with the reason on stderr."""
    assert cli.main(["where", "no_such_setting_anywhere"]) == 2
    assert "no question or derived value" in capsys.readouterr().err
