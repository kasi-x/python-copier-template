"""Maintenance checks: MicroPython upstream pins and doc/template sync."""

import re
import subprocess
import sys
from pathlib import Path

TOP = Path(__file__).absolute().parent.parent

COPIER_YML = TOP / "copier.yml"
FREEZE_TEMPLATE = (
    TOP
    / "template"
    / ("{% if micropython_pkg %}tools{% endif %}/{% if micropython_pkg %}micropython{% endif %}/freeze.py.jinja")
)
STUBS_TEMPLATE = TOP / "template" / ("{% if micropython_pkg %}requirements-dev.txt{% endif %}.jinja")
MICROPYTHON_DOC = TOP / "docs" / "how-to" / "micropython.md"


def run_checker(offline: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(TOP / "tools" / "check_micropython_upstream.py")]
    if offline:
        cmd.append("--offline")
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def doc_has_concrete_tag(doc: str) -> bool:
    """True if the doc contains a concrete v<major>.<minor>.<patch> tag."""
    return re.search(r"--tag v\d+\.\d+\.\d+", doc) is not None


def micropython_version() -> str:
    """Read micropython_version from copier.yml."""
    src = COPIER_YML.read_text()
    match = re.search(
        r"^micropython_version:\n    type: str\n    default: \"([^\"]+)\"",
        src,
        re.MULTILINE,
    )
    assert match, "micropython_version not found in copier.yml"
    return match.group(1)


def test_upstream_checker_offline_reports_pins():
    """The checker extracts the MicroPython pin without needing the network."""
    result = run_checker(offline=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MicroPython version (copier.yml micropython_version)" in result.stdout
    assert "v1." in result.stdout
    assert "Docker image" in result.stdout
    assert "micropython-<port>-stubs pin" in result.stdout


def test_single_source_of_truth_is_consistent():
    """micropython_version drives freeze.py AND the stub pin together."""
    version = micropython_version()
    assert version.startswith("v"), f"expected a vX.Y.Z tag, got {version}"
    # freeze.py renders DEFAULT_TAG from the copier variable.
    freeze = FREEZE_TEMPLATE.read_text()
    assert 'DEFAULT_TAG = "{{ micropython_version }}"' in freeze
    # requirements-dev.txt pins the stubs to the same version.
    stubs = STUBS_TEMPLATE.read_text()
    assert "~={{ micropython_version[1:] }}" in stubs
    assert "community" in stubs or "NOT official" in stubs


def test_docs_do_not_hardcode_the_micropython_tag():
    """Docs must not pin a concrete tag, or they drift from the template.

    copier.yml owns the pin (micropython_version); the docs explain how to
    override with a placeholder so a future bump does not leave docs behind.
    """
    doc = MICROPYTHON_DOC.read_text()
    # Docs must not contain a `v1.x.y` literal that can go stale.
    assert not doc_has_concrete_tag(doc)
