"""Guards for `architekton/hygiene.py` -- the checks `task hygiene` and CI share.

The four checks used to live inline in `.github/workflows/_hygiene.yml`, where
only CI could run them; the module exists so a local run and the workflow run
make the same call. These tests press its observable contract, not its
internals: each case builds a throwaway git work tree, runs
`python architekton/hygiene.py` inside it, and asserts on the exit status --
0 when clean, 1 plus the offending paths when not -- which is exactly what the
workflow step reads.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from architekton.hygiene import conflict_markers
from architekton.hygiene import invalid_yaml
from architekton.hygiene import oversized
from architekton.hygiene import worktree_files

TOP = Path(__file__).resolve().parent.parent
SCRIPT = TOP / "architekton" / "hygiene.py"
MEGABYTE = 1024 * 1024


def _repo(tmp_path: Path) -> Path:
    """An empty git work tree: the checks read git's own file list."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    return repo


def _write(repo: Path, name: str, content: str | bytes) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)


def _sparse(repo: Path, name: str, size: int) -> None:
    """A `size`-byte file that allocates nothing on disk (what `du` cannot see)."""
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(size)


def _hygiene(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_repo_passes(tmp_path: Path) -> None:
    """A tidy tree exits 0 -- the only status `task check` and CI tolerate."""
    repo = _repo(tmp_path)
    _write(repo, "README.md", "# hello\n")
    _write(repo, "notes.txt", "text\n")
    result = _hygiene(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "clean" in result.stdout


def test_missing_trailing_newline_fails(tmp_path: Path) -> None:
    """A text file without its final newline is reported by name."""
    repo = _repo(tmp_path)
    _write(repo, "README.md", "# hello")  # no trailing newline
    result = _hygiene(repo)
    assert result.returncode == 1, result.stdout
    assert "missing trailing newline" in result.stdout
    assert "README.md" in result.stdout


def test_jinja_partial_without_newline_passes(tmp_path: Path) -> None:
    """`.jinja` partials end without a newline on purpose (the render adds one)."""
    repo = _repo(tmp_path)
    _write(repo, "payload.txt.jinja", "{% include '_shared/x.jinja' %}")
    assert _hygiene(repo).returncode == 0


def test_binary_file_without_newline_passes(tmp_path: Path) -> None:
    """A NUL byte in the first 8 KiB marks the file binary: no newline expected."""
    repo = _repo(tmp_path)
    _write(repo, "assets/blob.bin", b"\x00\x01\x02")
    assert _hygiene(repo).returncode == 0


def test_lockfile_without_newline_passes(tmp_path: Path) -> None:
    """`uv.lock` is machine-written: its trailing newline is not ours to control."""
    repo = _repo(tmp_path)
    _write(repo, "uv.lock", "version = 1")
    assert _hygiene(repo).returncode == 0


def test_pyproject_without_newline_passes(tmp_path: Path) -> None:
    """`pyproject.toml` was exempt from the original check and stays exempt."""
    repo = _repo(tmp_path)
    _write(repo, "pyproject.toml", "[project]")
    assert _hygiene(repo).returncode == 0


def test_invalid_yaml_fails(tmp_path: Path) -> None:
    """An unparsable `.yml` is reported with the parser's message."""
    repo = _repo(tmp_path)
    _write(repo, "broken.yml", "key: [1, 2\n")
    result = _hygiene(repo)
    assert result.returncode == 1, result.stdout
    assert "invalid YAML" in result.stdout
    assert "broken.yml" in result.stdout


def test_copier_yml_include_tags_pass(tmp_path: Path) -> None:
    """`copier.yml` carries custom `!include` tags the safe loader rejects."""
    repo = _repo(tmp_path)
    _write(repo, "copier.yml", "_extends:\n  - !include questions/base.yml\n")
    assert _hygiene(repo).returncode == 0


def test_include_tag_outside_copier_yml_fails(tmp_path: Path) -> None:
    """The `copier.yml` exemption is the file name, not the tag: elsewhere it fails."""
    repo = _repo(tmp_path)
    _write(repo, "config.yml", "_extends:\n  - !include questions/base.yml\n")
    result = _hygiene(repo)
    assert result.returncode == 1, result.stdout
    assert "config.yml" in result.stdout


def test_unrendered_jinja_yaml_passes(tmp_path: Path) -> None:
    """A YAML source still carrying `{% ... %}` is a template, not a document."""
    repo = _repo(tmp_path)
    _write(repo, "workflow.yml", "{% if ros2_pkg %}\nkey: [1, 2\n{% endif %}\n")
    assert _hygiene(repo).returncode == 0


def test_yaml_in_skipped_directory_passes(tmp_path: Path) -> None:
    """`build/` (like `site/`, `.venv`, `node_modules`) is checkout output, not source."""
    repo = _repo(tmp_path)
    _write(repo, "build/broken.yml", "key: [1, 2\n")
    assert _hygiene(repo).returncode == 0


def test_merge_conflict_marker_fails(tmp_path: Path) -> None:
    """A `<<<<<<< ` line is reported as `path:line`."""
    repo = _repo(tmp_path)
    _write(repo, "src/app.py", "a = 1\n<<<<<<< HEAD\nb = 2\n")
    result = _hygiene(repo)
    assert result.returncode == 1, result.stdout
    assert "merge-conflict markers" in result.stdout
    assert "src/app.py:2" in result.stdout


def test_oversized_file_fails(tmp_path: Path) -> None:
    """A file over 10 MiB is refused, even when it is sparse (nothing allocated on disk)."""
    repo = _repo(tmp_path)
    _sparse(repo, "assets/blob.bin", 11 * MEGABYTE)
    result = _hygiene(repo)
    assert result.returncode == 1, result.stdout
    assert "assets/blob.bin" in result.stdout


def test_oversized_lockfile_passes(tmp_path: Path) -> None:
    """Lockfiles are huge by nature: exempt from the size check too."""
    repo = _repo(tmp_path)
    _sparse(repo, "uv.lock", 11 * MEGABYTE)
    assert _hygiene(repo).returncode == 0


def test_gitignored_files_are_not_scanned(tmp_path: Path) -> None:
    """Git's exclude rules decide the candidate set: a rendered `.cache/` is not source."""
    repo = _repo(tmp_path)
    _write(repo, ".gitignore", "cache/\n")
    _write(repo, "cache/scratch.md", "<<<<<<< HEAD\n")
    _write(repo, "cache/scratch.yml", "key: [1, 2\n")
    result = _hygiene(repo)
    assert result.returncode == 0, result.stdout


def test_every_failing_check_is_reported(tmp_path: Path) -> None:
    """The run does not stop at the first failure: one exit lists all four."""
    repo = _repo(tmp_path)
    _write(repo, "src/app.py", "a = 1")  # missing newline
    _write(repo, "conflict.md", "<<<<<<< HEAD\n")  # marker
    _write(repo, "broken.yml", "key: [1, 2\n")  # invalid YAML
    _sparse(repo, "assets/blob.bin", 11 * MEGABYTE)  # oversized
    result = _hygiene(repo)
    assert result.returncode == 1, result.stdout
    for label in ("merge-conflict markers", "files over 10MB", "missing trailing newline", "invalid YAML"):
        assert label in result.stdout, result.stdout


def test_walk_fallback_outside_git(tmp_path: Path) -> None:
    """A released tarball has no `.git`: the walk still sees every file."""
    _write(tmp_path, "README.md", "# hi\n")
    _write(tmp_path, ".git/trap.yml", "key: [1, 2\n")
    names = [p.as_posix() for p in worktree_files(tmp_path)]
    assert "README.md" in names
    assert ".git/trap.yml" not in names


def test_read_failure_is_skipped(tmp_path: Path) -> None:
    """A file that cannot be opened (dangling symlink, race) is no finding."""
    (tmp_path / "gone.txt").symlink_to("no-such-target")
    assert conflict_markers([tmp_path / "gone.txt"]) == []


def test_stat_failure_is_skipped(tmp_path: Path) -> None:
    """`oversized` tolerates a path that disappears between listing and stat."""
    (tmp_path / "gone.bin").symlink_to("no-such-target")
    assert oversized([tmp_path / "gone.bin"]) == []


def test_yaml_read_failure_is_reported(tmp_path: Path) -> None:
    """An unreadable `.yml` surfaces as a finding, not a traceback."""
    bad = tmp_path / "locked.yml"
    bad.write_text("key: 1\n", encoding="utf-8")
    bad.chmod(0o000)
    try:
        found = invalid_yaml([bad])
    finally:
        bad.chmod(0o644)
    assert found and "locked.yml" in found[0]
