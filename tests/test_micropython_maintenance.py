"""Maintenance checks: the MicroPython pin and the artifacts it drives.

The questionnaire owns the pin (``micropython_version``, questions/_internal.yml);
the firmware freeze script and the stub requirements only consume it. These
checks read that value back out of the questionnaire's own parser and prove a
real render carries it to both generated artifacts -- a template that hardcoded
either side would fail here -- plus that the offline upstream checker reports
the same pin.
"""

import re
import subprocess
import sys
from pathlib import Path

from copier import run_copy

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import questionnaire  # noqa: E402

from test_recommended_path import BASE  # noqa: E402

MICROPYTHON_DOC = TOP / "docs" / "how-to" / "micropython.md"

# Somewhere else entirely: the render must follow the value, not the default.
OVERRIDE_VERSION = "v9.9.9"


def run_checker(offline: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(TOP / "tools" / "check_upstream.py"), "--only", "MicroPython,micropython"]
    if offline:
        cmd.append("--offline")
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def doc_has_concrete_tag(doc: str) -> bool:
    """True if the doc contains a concrete v<major>.<minor>.<patch> tag."""
    return re.search(r"--tag v\d+\.\d+\.\d+", doc) is not None


def micropython_version() -> str:
    """The tag the questionnaire declares for MicroPython."""
    questions, _ = questionnaire.load_questions()
    default = next(q.default for q in questions if q.name == "micropython_version")
    assert isinstance(default, str) and default.startswith("v"), default
    return default


def render_micropython(tmp_path: Path, version: str) -> Path:
    """Render the MicroPython fast path, pinning ``micropython_version``."""
    tmp_path.mkdir(parents=True)
    run_copy(
        src_path=str(TOP),
        dst_path=tmp_path,
        data={**BASE, "project_type": "micropython", "micropython_port": "esp32", "micropython_version": version},
        vcs_ref="HEAD",
        defaults=True,
        unsafe=True,
        overwrite=True,
        skip_tasks=True,
    )
    return tmp_path


def assert_render_uses(project: Path, version: str) -> None:
    """Both generated consumers of the pin must carry ``version``."""
    freeze = (project / "tools" / "micropython" / "freeze.py").read_text(encoding="utf-8")
    assert f'DEFAULT_TAG = "{version}"' in freeze, "the firmware build must default to the questionnaire's tag"
    stubs = (project / "requirements-dev.txt").read_text(encoding="utf-8")
    assert f"micropython-esp32-stubs~={version.removeprefix('v')}" in stubs, (
        "the stub pin must track the same tag (~= on the version without the v)"
    )


def test_upstream_checker_offline_reports_pins():
    """The checker extracts both MicroPython pins without needing the network."""
    result = run_checker(offline=True)
    assert result.returncode == 0, result.stdout + result.stderr
    version = micropython_version()
    assert version in result.stdout, "the checker must report the questionnaire's tag"
    assert f"~={version.removeprefix('v')}" in result.stdout, "and the stub pin derived from it"


def test_single_source_of_truth_drives_the_render(tmp_path: Path):
    """micropython_version drives freeze.py AND the stub pin in one render.

    The shipped default must reach both artifacts, and an overridden value
    must reach them too: that is what "single source of truth" means -- a
    hardcoded tag on either side breaks the second render.
    """
    assert_render_uses(render_micropython(tmp_path / "default", micropython_version()), micropython_version())
    assert_render_uses(render_micropython(tmp_path / "override", OVERRIDE_VERSION), OVERRIDE_VERSION)


def test_docs_do_not_hardcode_the_micropython_tag():
    """Docs must not pin a concrete tag, or they drift from the template.

    copier.yml owns the pin (micropython_version); the docs explain how to
    override with a placeholder so a future bump does not leave docs behind.
    """
    doc = MICROPYTHON_DOC.read_text(encoding="utf-8")
    # Docs must not contain a `v1.x.y` literal that can go stale.
    assert not doc_has_concrete_tag(doc)
