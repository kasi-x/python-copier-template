"""The shipped entry point's dispatch: `python-copier-template new <dir>`.

`tools/cli.py` is the console script this template publishes (pyproject.toml
`[project.scripts]`), and it is a *dispatcher*: the mode `tools/detect.py`
reports picks one of three outcomes, two of which refuse. The tools it calls
have their own tests (test_adopt.py, test_detect.py, test_batch.py); what only
this module can check is the branch that picks between them, and the exit codes
it promises (0 ok / 1 failed / 2 invalid request / 3 refused -- the same
contract as the tools it dispatches to).

The collaborators are patched at this module's boundary (`cli.detect.detect`,
`cli.adopt.adopt`, `cli.batch.render`) so each branch is one in-process call: a
real render, adoption or detector run is that tool's test's subject, not this
dispatcher's. The one path exercised for real is preset loading, whose failure
is this module's own.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_adopt.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools import adopt  # noqa: E402
from tools import batch  # noqa: E402
from tools import cli  # noqa: E402
from tools import detect  # noqa: E402


def _detection(mode: str, **overrides: Any) -> detect.Detection:
    """A Detection with the fields this dispatcher reads."""
    fields: dict[str, Any] = {"path": "/tmp/target", "mode": mode}
    fields.update(overrides)
    return detect.Detection(**fields)


def _adoption(**overrides: Any) -> adopt.Adoption:
    """An Adoption with the fields this dispatcher reads."""
    fields: dict[str, Any] = {
        "target": "/tmp/target",
        "mode": "adopt",
        "ref": "HEAD",
        "ref_reason": "the working tree",
    }
    fields.update(overrides)
    return adopt.Adoption(**fields)


# cli.py imports these modules at module level and reads their attributes as
# `cli.<module>.<name>`, so patching the imported module's attribute here
# (the same object cli.py holds) patches what the dispatcher calls.


def test_new_fresh_renders_and_reports_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """`fresh` mode renders through batch.render and reports the created tree."""
    calls: list[dict[str, Any]] = []

    def fake_render(src: str, dest: Path, data: dict[str, Any], ref: str = "HEAD", **kwargs: Any) -> None:
        calls.append({"src": src, "dest": Path(dest), "data": data, "ref": ref, **kwargs})
        (Path(dest) / "README.md").write_text("# made\n")

    monkeypatch.setattr(
        detect, "detect", lambda *a, **k: _detection("fresh", suggested_answers={"existing_project": False})
    )
    monkeypatch.setattr(adopt, "resolve_ref", lambda requested=None: ("HEAD", "the working tree"))
    monkeypatch.setattr(batch, "render", fake_render)

    assert cli.new(tmp_path, preset=None, ref=None, dry_run=False) == cli.OK
    assert calls and calls[0]["dest"] == tmp_path and calls[0]["ref"] == "HEAD"
    assert calls[0]["defaults"] is False  # no preset: copier asks the questionnaire
    out = capsys.readouterr().out
    assert "mode:    fresh" in out
    assert f"target:  {tmp_path.resolve()}" in out
    assert "created: 1 file(s)" in out


def test_new_fresh_with_preset_keeps_copier_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A preset makes the run non-interactive, so the render keeps copier's defaults."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(detect, "detect", lambda *a, **k: _detection("fresh", suggested_answers={}))
    monkeypatch.setattr(adopt, "resolve_ref", lambda requested=None: ("HEAD", "why"))

    def fake_render(*args: Any, **kwargs: Any) -> None:
        calls.append(kwargs)
        (Path(args[1]) / "README.md").write_text("")

    monkeypatch.setattr(batch, "render", fake_render)

    assert cli.new(tmp_path, preset="library", ref=None, dry_run=False) == cli.OK
    assert calls and calls[0]["defaults"] is True


def test_new_fresh_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """`--dry-run` plans through adopt.render_fresh_source and never renders."""
    source = tmp_path / "plan"
    (source / "pkg").mkdir(parents=True)
    (source / "pkg" / "__init__.py").write_text("")
    (source / "README.md").write_text("")
    monkeypatch.setattr(detect, "detect", lambda *a, **k: _detection("fresh", suggested_answers={}))
    monkeypatch.setattr(adopt, "resolve_ref", lambda requested=None: ("HEAD", "the working tree"))
    monkeypatch.setattr(adopt, "render_fresh_source", lambda data, ref: source)
    monkeypatch.setattr(batch, "render", lambda *a, **k: pytest.fail("a dry run must not render"))

    target = tmp_path / "target"
    assert cli.new(target, preset=None, ref=None, dry_run=True) == cli.OK
    out = capsys.readouterr().out
    assert "dry run -- nothing written" in out
    assert "would create 2 file(s); top level: README.md, pkg" in out
    assert not target.exists()


def test_new_foreign_refuses_with_exit_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """Another template's project is refused, not overwritten."""
    monkeypatch.setattr(detect, "detect", lambda *a, **k: _detection("foreign", foreign_src="https://example.com/x"))
    monkeypatch.setattr(batch, "render", lambda *a, **k: pytest.fail("a foreign project must not render"))

    assert cli.new(tmp_path, preset=None, ref=None, dry_run=False) == cli.REFUSED
    assert "example.com" in capsys.readouterr().err


def test_new_update_refuses_with_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """A project this template already generated is sent to `copier update`."""
    monkeypatch.setattr(detect, "detect", lambda *a, **k: _detection("update"))
    monkeypatch.setattr(batch, "render", lambda *a, **k: pytest.fail("update mode must not render"))

    assert cli.new(tmp_path, preset=None, ref=None, dry_run=False) == cli.INVALID
    assert "copier update" in capsys.readouterr().err


def test_new_adopt_goes_through_the_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """`adopt` mode delegates to tools/adopt.py, never merges, and warns on collisions."""
    calls: list[dict[str, Any]] = []

    def fake_adopt(target: Path, **kwargs: Any) -> adopt.Adoption:
        calls.append({"target": target, **kwargs})
        return _adoption(ok=True)

    monkeypatch.setattr(detect, "detect", lambda *a, **k: _detection("adopt", collisions=["README.md"]))
    monkeypatch.setattr(adopt, "adopt", fake_adopt)
    monkeypatch.setattr(adopt, "render_report", lambda adoption: "adopted 1 file(s)")

    assert cli.new(tmp_path, preset=None, ref=None, dry_run=False) == cli.OK
    assert calls and calls[0]["merge_generated"] is False  # the CLI never merges
    captured = capsys.readouterr()
    assert "adopted 1 file(s)" in captured.out
    assert "warning: 1 existing file(s)" in captured.err  # collisions warn before adopting


def test_new_adopt_reports_a_failed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """An adoption that did not hold returns 1, the same verdict the tool reports."""
    monkeypatch.setattr(detect, "detect", lambda *a, **k: _detection("adopt"))
    monkeypatch.setattr(adopt, "adopt", lambda *a, **k: _adoption(ok=False, error="rollback ran"))
    monkeypatch.setattr(adopt, "render_report", lambda adoption: "rolled back")

    assert cli.new(tmp_path, preset=None, ref=None, dry_run=False) == cli.FAILED
    assert "rolled back" in capsys.readouterr().out


def test_new_adopt_refuses_a_foreign_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """adopt.py's ownership refusal maps to exit 3, not to a generic failure."""

    def refuse(*_args: Any, **_kwargs: Any) -> None:
        message = "owned by another template"
        raise adopt.OwnershipError(message)

    monkeypatch.setattr(detect, "detect", lambda *a, **k: _detection("adopt"))
    monkeypatch.setattr(adopt, "adopt", refuse)

    assert cli.new(tmp_path, preset=None, ref=None, dry_run=False) == cli.REFUSED
    assert "owned by another template" in capsys.readouterr().err


def test_new_unknown_preset_is_an_invalid_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """A preset that does not exist fails before the detector runs."""
    monkeypatch.setattr(detect, "detect", lambda *a, **k: pytest.fail("an unknown preset must not reach detect"))

    assert cli.new(tmp_path, preset="no-such-preset", ref=None, dry_run=False) == cli.INVALID
    err = capsys.readouterr().err
    assert "unknown preset" in err
    assert "library" in err  # the available presets are listed


def test_preset_answers_reads_a_real_preset_and_rejects_a_non_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A preset file must be an answers mapping; the shipped ones are readable."""
    assert cli.preset_answers("library")["project_type"] == "library"
    presets = tmp_path / "presets"
    presets.mkdir()
    (presets / "broken.yml").write_text("- just\n- a\n- list\n")
    monkeypatch.setattr(cli, "PRESETS", presets)

    with pytest.raises(cli.RequestError, match="not an answers mapping"):
        cli.preset_answers("broken")


def test_collision_warning_summarizes_past_the_limit():
    """The warning names up to the limit, then counts the rest."""
    few = cli.collision_warning(["a.txt", "b.txt"])
    assert few == "warning: 2 existing file(s) the template also ships will be left alone: a.txt, b.txt"
    many = cli.collision_warning([f"f{index}.txt" for index in range(cli.COLLISION_LIMIT + 3)])
    assert "warning: 15 existing file(s)" in many
    assert "(+3 more)" in many


def test_main_parses_the_new_subcommand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`main` resolves the subcommand, the directory and the flags."""
    seen: dict[str, Any] = {}

    def fake_new(target: Path, *, preset: str | None, ref: str | None, dry_run: bool) -> int:
        seen.update(target=target, preset=preset, ref=ref, dry_run=dry_run)
        return cli.OK

    monkeypatch.setattr(cli, "new", fake_new)

    assert cli.main(["new", str(tmp_path), "--preset", "library", "--ref", "HEAD", "--dry-run"]) == cli.OK
    assert seen == {"target": tmp_path, "preset": "library", "ref": "HEAD", "dry_run": True}
