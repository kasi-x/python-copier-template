"""Lint the rendered output of the questionnaire's recommended (fast) paths.

test_recommended_path.py proves those paths *render*; this module proves the
rendered tree is clean under the generated project's own ruff config. We run
`run_copy(..., skip_tasks=True)` so no uv sync is needed -- ruff (from this
repo's venv) is pointed at the generated project, whose pyproject.toml holds
the `[tool.ruff]` that the generated project's own CI would use. A failure
here means the template's .jinja sources emit code the generated ruff config
rejects, which the heavy task-check tests in test_example.py would only catch
after a full uv sync.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from copier import run_copy

from test_recommended_path import BASE
from test_recommended_path import FAST_PATHS

TOP = Path(__file__).absolute().parent.parent


def _id(answers: dict[str, object]) -> str:
    return "-".join(f"{k}={v}" for k, v in answers.items())


# Extra recommended-path cases beyond FAST_PATHS: the project families whose
# generated Python is ruff-checked. (FAST_PATHS deliberately skips these
# because test_example.py's copy_project_recommended already renders them;
# this module needs them here to lint the output.)
EXTRA_PATHS: list[dict[str, object]] = [
    {"project_type": "data_science"},
    {"project_type": "micropython", "micropython_port": "esp32"},
    {
        "project_type": "ros2",
        "pkg_language": "python",
        "ros_distro": "humble",
        "ros2_package_manager": "apt",
    },
]

RENDERED_PATHS = FAST_PATHS + EXTRA_PATHS


def _ruff_bin() -> Path:
    """The ruff to lint rendered output with: the one in this repo's venv.

    The generated project has no venv of its own (we skip uv sync), so reuse
    the interpreter running this test suite. pytest-xdist workers may run
    under a different sys.executable, so prefer TOP/.venv/bin first.
    """
    for base in (TOP / ".venv" / "bin", Path(sys.executable).resolve().parent):
        candidate = base / "ruff"
        if candidate.exists():
            return candidate
    which = shutil.which("ruff")
    assert which, "ruff not found in .venv/bin, next to sys.executable, or on PATH"
    return Path(which)


@pytest.mark.parametrize("answers", RENDERED_PATHS, ids=[_id(a) for a in RENDERED_PATHS])
def test_generated_project_is_ruff_clean(tmp_path: Path, answers: dict[str, object]):
    run_copy(
        src_path=str(TOP),
        dst_path=tmp_path,
        data={**BASE, **answers},
        vcs_ref="HEAD",
        defaults=True,
        unsafe=True,
        overwrite=True,
        skip_tasks=True,  # REUSE-copy tasks need a checkout; ruff is what we test
    )
    ruff = _ruff_bin()
    proc = subprocess.run(
        [str(ruff), "check", "--no-cache", "."],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"generated project is not clean under its own [tool.ruff]:\n{proc.stdout}{proc.stderr}"
    )


# Text file extensions whose content copier renders from .jinja sources.
# Binary-ish or machine-owned files (images, lockfiles, .copier-answers.yml)
# are excluded: the end-of-file convention applies to authored text.
_TEXT_SUFFIXES = {
    ".cff",
    ".css",
    ".csv",
    ".env",
    ".gitignore",
    ".ini",
    ".jinja",
    ".json",
    ".lua",
    ".md",
    ".py",
    ".rst",
    ".sql",
    ".toml",
    ".txt",
    ".tex",
    ".yaml",
    ".yml",
}
_TEXT_EXCLUDES = {
    ".copier-answers.yml",
    ".git/",
    ".pixi/",
    ".venv/",
    "uv.lock",
    "poetry.lock",
    "pixi.lock",
}


def _iter_text_files(root: Path):
    """Yield generated text files that should follow the end-of-file rule."""
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if not path.is_file():
            continue
        if any(rel == ex or rel.startswith(ex) for ex in _TEXT_EXCLUDES):
            continue
        if path.suffix in _TEXT_SUFFIXES or path.name in _TEXT_SUFFIXES:
            yield path


@pytest.mark.parametrize("answers", RENDERED_PATHS, ids=[_id(a) for a in RENDERED_PATHS])
def test_generated_files_end_with_single_newline(tmp_path: Path, answers: dict[str, object]):
    """Rendered text files must end with exactly one newline.

    Jinja sources that end with `{% include %}` / `{% if %}` tags silently
    add a trailing blank line (the tag's own newline), which the generated
    project's own end-of-file-fixer would then rewrite on first commit. This
    is a recurring class of bug, so every rendered path is checked: each text
    file must end in exactly one ``\\n`` (no trailing blank line, no missing
    final newline).
    """
    run_copy(
        src_path=str(TOP),
        dst_path=tmp_path,
        data={**BASE, **answers},
        vcs_ref="HEAD",
        defaults=True,
        unsafe=True,
        overwrite=True,
        skip_tasks=True,
    )
    offenders: list[str] = []
    for path in _iter_text_files(tmp_path):
        data = path.read_bytes()
        if not data:
            continue  # empty file: nothing to end with a newline
        if not data.endswith(b"\n"):
            offenders.append(f"{path.relative_to(tmp_path)}: missing final newline")
        elif data.endswith(b"\n\n"):
            offenders.append(f"{path.relative_to(tmp_path)}: trailing blank line(s)")
    assert not offenders, "generated text files must end with exactly one newline:\n" + "\n".join(offenders)
