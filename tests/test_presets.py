"""`presets/*.yml` are usable answers files: each renders end to end.

`tools/cli.py`'s `--preset` path reads one of these files and makes the run
non-interactive (`--defaults`), so the shared Project Details plus the
preset's few keys is exactly the answer set a user supplies. These tests
render that set for real -- `copy_project_recommended` with the preset's
answers merged on top, which is what `cli.new` assembles -- because the
failure a preset can have (a renamed question, an invalid choice, a `when`
that silently drops the family it picks) only shows up at render time, not
in the load-path tests test_cli.py already runs. The parametrization reads
`cli.available_presets()` so a new preset is covered the moment it exists.

Sentinels are per-family: the file that proves the family landed (the
ROS 2 `package.xml`, the web `app/` tree, the src/ package for the Python
project types), or -- for the online-judge presets, which deliberately ship
a bare workspace with no package tree -- the judge's own marker inside the
generated README.
"""

import sys
from pathlib import Path

import pytest

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_cli.py does the same to reach tools/
    sys.path.insert(0, str(TOP))

from tools import cli  # noqa: E402

from support import copy_project_recommended  # noqa: E402

# The file that would be absent if the preset's family keys were dropped or
# rejected -- `README.md` alone cannot tell a preset render from the default
# one, because the default render ships it too.
SENTINEL_PATH: dict[str, str] = {
    "library": "src/recommended_example/__init__.py",
    "cli": "src/recommended_example/__main__.py",
    "web-api": "app/main.py",
    "data-science": "src/recommended_example/__init__.py",
    "micropython": "firmware/main.py",
    "ros2": "package.xml",
}

# The judge workspaces are bare on purpose (the judge's own CLI creates its
# directories), so the judge identity lives in the generated README's
# site-specific wording -- the same pins tests/test_example_oj.py uses.
SENTINEL_README: dict[str, str] = {
    "online-judge-atcoder": "atcoder.jp",
    "online-judge-codeforces": "codeforces.com",
    "online-judge-kattis": "open.kattis.com",
}

PRESETS = cli.available_presets()


@pytest.mark.parametrize("preset", PRESETS)
def test_preset_renders(tmp_path: Path, preset: str):
    """`--preset {preset}` produces a project: the render succeeds and the
    family's sentinel is there."""
    copy_project_recommended(tmp_path, run_tasks=False, **cli.preset_answers(preset))
    readme = tmp_path / "README.md"
    assert readme.is_file()
    if preset in SENTINEL_PATH:
        assert (tmp_path / SENTINEL_PATH[preset]).exists(), (
            f"preset {preset!r} rendered but its family sentinel {SENTINEL_PATH[preset]} is missing -- "
            "the preset's answers no longer reach the files they used to"
        )
    elif preset in SENTINEL_README:
        assert SENTINEL_README[preset] in readme.read_text(encoding="utf-8"), (
            f"preset {preset!r} rendered but its judge marker {SENTINEL_README[preset]!r} is not in README.md -- "
            "the preset's oj_kind answer no longer reaches the generated guide"
        )
    else:
        pytest.fail(f"preset {preset!r} has no sentinel -- add it to SENTINEL_PATH or SENTINEL_README")


def test_every_preset_has_a_sentinel():
    """A preset without a sentinel would fail in the parametrized test only
    after a render; this pins the maps to the preset list up front."""
    assert set(SENTINEL_PATH) | set(SENTINEL_README) == set(PRESETS)
