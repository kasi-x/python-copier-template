"""pyproject-fmt must be able to process a rendered pyproject.toml.

pyproject-fmt is a lossless formatter by contract — it never changes the
meaning of a file. What this template must guarantee is the other direction:
the pyproject.toml it renders is something pyproject-fmt can actually parse
and reformat without erroring out.

The generated project ships a `pyproject-fmt.toml` so that, when a user runs
pyproject-fmt, the template's preferred shape is respected (long `[tool.x]`
table format, full version numbers, authored classifier list kept).
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from copier import run_copy

from test_generated_lint import RENDERED_PATHS  # same renders test_generated_lint lints
from test_recommended_path import BASE

TOP = Path(__file__).absolute().parent.parent


def _pyproject_fmt_bin() -> Path:
    """The pyproject-fmt from this repo's venv (or the running interpreter)."""
    # pytest-xdist workers may run under a different sys.executable, so prefer
    # the venv next to the repo's known interpreter chain: TOP/.venv/bin.
    for base in (TOP / ".venv" / "bin", Path(sys.executable).resolve().parent):
        candidate = base / "pyproject-fmt"
        if candidate.exists():
            return candidate
    which = shutil.which("pyproject-fmt")
    assert which, "pyproject-fmt not found in .venv/bin, next to sys.executable, or on PATH"
    return Path(which)


def _id(answers: dict[str, object]) -> str:
    return "-".join(f"{k}={v}" for k, v in answers.items())


@pytest.mark.parametrize("answers", RENDERED_PATHS, ids=[_id(a) for a in RENDERED_PATHS])
def test_pyproject_fmt_accepts_rendered_pyproject(tmp_path: Path, answers: dict[str, object]):
    """pyproject-fmt runs cleanly on the rendered pyproject.toml.

    Exit 0/1 means it parsed and formatted the file (0 = no change, 1 = it
    would reformat); exit 2 means a configuration error or unparsable input,
    which would be a template bug.
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
    pyproject = tmp_path / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("this render produces no pyproject.toml (ros2 cpp?)")
    assert (tmp_path / "pyproject-fmt.toml").exists(), "generated project must ship pyproject-fmt.toml"
    proc = subprocess.run(
        [str(_pyproject_fmt_bin()), "--check", "pyproject.toml"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode in (0, 1), (
        f"pyproject-fmt could not process the rendered pyproject.toml (answers {answers}):\n{proc.stdout}{proc.stderr}"
    )
