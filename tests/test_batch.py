"""Tests for tools/batch.py: the JSONL batch runner's verdicts.

The runner exists so a batch of copier requests can be judged without a
human reading any output, so what matters here is that a *wrong* request
line is rejected loudly (unknown key, duplicate id, overlapping dest, bad
expectation shape), that a *failing* expectation really fails, and that
`--jobs N` changes only the schedule. The end-to-end and `--jobs` tests
render real projects from the real template; every other test is offline.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import batch  # noqa: E402

BASE_ANSWERS = {
    "package_name": "batch_example",
    "description": "An example project",
    "git_platform": "github.com",
    "github_org": "kasi-x",
    "author_name": "kasi-x",
    "author_email": "kashimiya.exe@gmail.com",
    "repo_name": "batch-example",
    "distribution_name": "batch-example",
}


def write_lines(tmp_path: Path, *requests: dict) -> list[Path]:
    path = tmp_path / "requests.jsonl"
    path.write_text("\n".join(json.dumps(request) for request in requests) + "\n")
    return [path]


def request(**overrides: object) -> dict:
    return {"id": "case", "answers": {"project_type": "script"}, **overrides}


def test_rejects_unknown_keys(tmp_path: Path):
    with pytest.raises(batch.SpecError) as excinfo:
        batch.load_requests(write_lines(tmp_path, {**request(), "not_a_key": {}}))
    assert "not_a_key" in str(excinfo.value), "the refusal names the offending key"


def test_rejects_duplicate_ids(tmp_path: Path):
    with pytest.raises(batch.SpecError) as excinfo:
        batch.load_requests(write_lines(tmp_path, request(), request()))
    assert request()["id"] in str(excinfo.value), "the refusal names the duplicated id"


def test_requires_an_id(tmp_path: Path):
    with pytest.raises(batch.SpecError):
        batch.load_requests(write_lines(tmp_path, {"answers": {}}))


def test_rejects_a_dest_outside_the_work_dir(tmp_path: Path):
    with pytest.raises(batch.SpecError) as excinfo:
        batch.load_requests(write_lines(tmp_path, request(dest="../escape")))
    assert "../escape" in str(excinfo.value), "the refusal names the offending dest"


def test_rejects_invalid_json(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{not json}\n")
    with pytest.raises(batch.SpecError) as excinfo:
        batch.load_requests([path])
    assert path.name in str(excinfo.value), "the refusal names the file it could not read"


def test_rejects_an_unknown_expectation_key(tmp_path: Path):
    """A misspelled key must fail the run, not silently check nothing."""
    with pytest.raises(batch.SpecError) as excinfo:
        batch.load_requests(write_lines(tmp_path, request(expect={"expects": []})))
    assert "expects" in str(excinfo.value), "the refusal names the misspelled key"


def test_rejects_a_toml_expectation_without_equals(tmp_path: Path):
    with pytest.raises(batch.SpecError) as excinfo:
        batch.load_requests(
            write_lines(tmp_path, request(expect={"toml": [{"path": "pyproject.toml", "key": "project.name"}]}))
        )
    assert "equals" in str(excinfo.value), "the refusal names the missing key"


def test_shipped_smoke_batch_parses():
    """The sample batch is part of the contract: a typo in it fails here."""
    requests = batch.load_requests([TOP / "batches" / "smoke.jsonl"])
    assert any(r.update is not None for r in requests), "the sample must exercise the update phase"
    assert any(r.expect for r in requests), "and judge what a render produced"


def test_checks_judge_a_tree(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "pkg.py").write_text("VALUE = 1\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nrequires-python = ">=3.11"\n')

    assert all(c.ok for c in batch.check_files(tmp_path, ["src/pkg.py", "src/**/*.py"]))
    assert not batch.check_files(tmp_path, ["src/missing.py"])[0].ok
    assert batch.check_absent(tmp_path, ["Dockerfile"])[0].ok
    assert not batch.check_absent(tmp_path, ["src"])[0].ok
    assert batch.check_matches(tmp_path, [{"path": "src/pkg.py", "regex": "^VALUE"}], want=True)[0].ok
    assert not batch.check_matches(tmp_path, [{"path": "src/pkg.py", "regex": "^NOPE"}], want=True)[0].ok
    assert batch.check_matches(tmp_path, [{"path": "src/pkg.py", "regex": "^NOPE"}], want=False)[0].ok
    assert not batch.check_matches(tmp_path, [{"path": "src/pkg.py", "regex": "^VALUE"}], want=False)[0].ok
    judged = batch.check_toml(
        tmp_path, [{"path": "pyproject.toml", "key": "project.requires-python", "equals": ">=3.11"}]
    )
    assert judged[0].ok
    wrong = batch.check_toml(tmp_path, [{"path": "pyproject.toml", "key": "project.name", "equals": "other"}])
    assert not wrong[0].ok and "actual 'demo'" in wrong[0].detail
    missing = batch.check_toml(tmp_path, [{"path": "pyproject.toml", "key": "project.nope", "equals": 1}])
    assert not missing[0].ok


def test_commands_report_exit_and_output(tmp_path: Path):
    passing = batch.check_commands(tmp_path, [{"run": "echo hello"}], "case")
    assert all(c.ok for c in passing)
    failing = batch.check_commands(tmp_path, [{"run": "exit 3"}], "case")
    assert not failing[0].ok and "exit 3" in failing[0].detail
    matched = batch.check_commands(tmp_path, [{"run": "echo hello", "stdout_regex": "^hello$"}], "case")
    assert all(c.ok for c in matched)
    unmatched = batch.check_commands(tmp_path, [{"run": "echo hello", "stdout_regex": "^bye$"}], "case")
    assert not all(c.ok for c in unmatched), "a stdout regex that does not match must fail the run"


def test_update_precondition_needs_a_clean_tree(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "tracked.txt").write_text("clean\n")
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"],
        check=True,
    )
    parsed = batch.load_requests(write_lines(tmp_path, request(update={"ref": "HEAD"}, src=str(repo))))[0]
    assert batch.update_precondition(parsed).ok

    (repo / "tracked.txt").write_text("dirty\n")
    dirty = batch.update_precondition(parsed)
    assert not dirty.ok
    assert "tracked.txt" in dirty.detail, "the failing check must name what is uncommitted"


def test_prepare_command_follows_the_rendered_project(tmp_path: Path):
    assert batch.prepare_command(tmp_path) is None
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    assert batch.prepare_command(tmp_path) == ["uv", "sync"]
    (tmp_path / "poetry.lock").write_text("")
    assert batch.prepare_command(tmp_path) == ["poetry", "install"]
    (tmp_path / "pixi.toml").write_text("[project]\n")
    assert batch.prepare_command(tmp_path) == ["pixi", "install"]


def test_prepare_environment_reports_success_and_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The check carries the install command's exit code and output."""
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    stub = stub_bin / "uv"
    stub.write_text("#!/bin/sh\necho installing\nexit 0\n")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_bin}:{os.environ['PATH']}")
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n")

    ok = batch.prepare_environment(project, "case")
    assert ok.ok

    stub.write_text("#!/bin/sh\necho boom >&2\nexit 3\n")
    failed = batch.prepare_environment(project, "case")
    assert not failed.ok
    assert "exit 3" in failed.detail and "boom" in failed.detail


def test_open_shell_runs_in_the_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--shell hands the terminal to $SHELL inside the rendered project."""
    marker = tmp_path / "shell-was-here"
    shell = tmp_path / "fake-shell"
    shell.write_text(f"#!/bin/sh\npwd > {marker}\n")
    shell.chmod(0o755)
    monkeypatch.setenv("SHELL", str(shell))
    project = tmp_path / "project"
    project.mkdir()

    batch.open_shell(project)

    assert marker.read_text().strip() == str(project)


def test_run_request_end_to_end(tmp_path: Path):
    """One real render through the real template, judged by the runner."""
    parsed = batch.load_requests(
        write_lines(
            tmp_path,
            {
                "id": "script-e2e",
                "answers": {**BASE_ANSWERS, "project_type": "script"},
                "expect": {
                    "files": ["batch_example/__init__.py", "pyproject.toml"],
                    "absent": ["src"],
                    "unmatches": [{"path": "README.md", "regex": "\\{\\{"}],
                    "toml": [{"path": "pyproject.toml", "key": "project.name", "equals": "batch-example"}],
                },
                "commands": [
                    {"run": "python3 -c \"import pathlib; print(len(list(pathlib.Path('.').rglob('*.py'))))\""}
                ],
            },
        )
    )[0]
    result = batch.run_request(parsed, tmp_path / "work", TOP)
    failed = [c for c in result.checks if not c.ok]
    assert result.error is None
    assert not failed, failed
    assert result.ok


def _script_answers() -> dict[str, Any]:
    return {**BASE_ANSWERS, "project_type": "script"}


def _verdicts(payload: dict[str, Any]) -> list[tuple[object, ...]]:
    """Everything in a --json report that must not depend on --jobs.

    `seconds`, `dest` and `work` are deliberately left out: they are the
    scheduling difference, not the verdict.
    """
    return [
        (
            line["id"],
            line["index"],
            line["ok"],
            line["error"],
            [(check["name"], check["ok"]) for check in line["checks"]],
        )
        for line in payload["lines"]
    ]


def _run_json(argv: list[str]) -> tuple[int, dict[str, Any]]:
    """Run `main` with `--json` and return its exit code and parsed report.

    `sys.stdout` is redirected around the call rather than read from pytest's
    capture: the runner reassigns fd 1 for the duration of the renders (see
    `report_stream_only`), which is exactly what keeps copier's chatter out of
    the JSON, and pytest's own capture is not a stable place to read it from.
    """
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = batch.main(argv)
    return code, json.loads(out.getvalue())


def test_jobs_change_only_the_schedule(tmp_path: Path):
    """--jobs N reorders nothing and swallows nothing.

    The first line sleeps, so under --jobs 3 the later lines render while it
    sleeps; the report must still follow the JSONL. The second line fails an
    expectation, so the run must still exit nonzero, with the same verdicts as
    `--jobs 1`.
    """
    path = write_lines(
        tmp_path,
        {"id": "slow", "answers": _script_answers(), "commands": [{"run": "sleep 0.8"}]},
        {"id": "broken", "answers": _script_answers(), "expect": {"files": ["not-rendered.txt"]}},
        {"id": "quick", "answers": _script_answers()},
    )[0]

    serial_code, serial = _run_json([str(path), "--json", "--work", str(tmp_path / "serial")])
    started = time.monotonic()
    parallel_code, parallel = _run_json([str(path), "--json", "--work", str(tmp_path / "parallel"), "--jobs", "3"])
    wall = time.monotonic() - started

    assert serial_code == parallel_code == 1, "one line fails its expectation, so both runs exit 1"
    assert parallel["ok"] is False, "a failing request fails the run under --jobs too"
    assert [line["id"] for line in parallel["lines"]] == ["slow", "broken", "quick"], (
        "results follow the JSONL, not the completion order"
    )
    # `seconds` is what each line took inside its own worker. Pitting two
    # lines against each other ("the sleeper finished last") reads scheduler
    # noise as signal: on a busy machine a quick line's render can stretch by
    # more than the sleeper's 0.8 s and invert the comparison. Overlap is
    # asserted against the clock instead -- the wall must beat the sum of the
    # lines' own durations, which only happens when the workers really run
    # side by side.
    assert parallel["lines"][0]["seconds"] >= 0.8, "the slow line really slept inside its worker"
    assert wall < sum(line["seconds"] for line in parallel["lines"]), (
        "three lines under --jobs 3 overlap: the wall beats the sum of the lines' own durations"
    )
    assert _verdicts(parallel) == _verdicts(serial)


def test_rejects_overlapping_dests(tmp_path: Path):
    """Two lines may not share a work dir: rendering one would wipe the other."""
    with pytest.raises(batch.SpecError) as excinfo:
        batch.load_requests(write_lines(tmp_path, request(id="outer"), request(id="inner", dest="outer/nested")))
    assert "overlaps" in str(excinfo.value), "the refusal says why"
    with pytest.raises(batch.SpecError) as excinfo:
        batch.load_requests(write_lines(tmp_path, request(), request(id="twin", dest="case")))
    assert "overlaps" in str(excinfo.value), "a duplicated dest is refused too"


def test_rejects_jobs_below_one(tmp_path: Path):
    path = write_lines(tmp_path, request())[0]
    with pytest.raises(SystemExit) as excinfo:
        batch.main([str(path), "--jobs", "0"])
    assert excinfo.value.code == 2, "argparse refuses --jobs 0 before anything renders"
