"""Static guard for the generation commands documented in the repo's docs.

Copier checks out the **latest git tag** when `copier copy` is given a URL
without `--vcs-ref`. Until the v1.0 fork detach (TODO item 11) the newest tag
here is the inherited pre-fork `5.4.0` — DiamondLightSource template content —
so every URL-based `copier copy` command we document MUST pin `--vcs-ref`.
Missing the flag silently generates projects from the old upstream template
(this produced the real "docs_type rejects zensical" and "asks
component_owner" bug reports; see BUG.md and COPIER_UPSTREAM.md item 9).
"""

import re
from pathlib import Path

import pytest

TOP = Path(__file__).resolve().parent.parent

DOC_FILES = [
    TOP / "README.md",
    *(TOP / "docs" / "tutorials").glob("*.md"),
]

TEMPLATE_URL = "kasi-x/python-copier-template.git"

FENCED_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


@pytest.mark.parametrize("doc", DOC_FILES, ids=lambda p: p.name)
def test_documented_copy_commands_pin_a_vcs_ref(doc: Path):
    """Every fenced block that runs `copier copy` against the template URL
    must pass `--vcs-ref=<something>` (main, HEAD, or a deliberate tag)."""
    text = doc.read_text(encoding="utf-8")
    for block in FENCED_BLOCK.findall(text):
        if "copier copy" not in block or TEMPLATE_URL not in block:
            continue
        assert re.search(r"--vcs-ref=\S+", block), (
            f"{doc.relative_to(TOP)}: a documented `copier copy` command is "
            "missing `--vcs-ref=`. Without it copier checks out the latest "
            "git tag, which here still points at the inherited pre-fork "
            "5.4.0 (old upstream template) — see BUG.md and TODO item 11."
        )


def test_documented_blocks_reference_the_current_template_commands():
    """Sanity for the guard itself: the main README flow must still be
    scanned (if the URL or command spelling drifts, the parametrized check
    above would silently pass over zero blocks)."""
    readme = (TOP / "README.md").read_text(encoding="utf-8")
    assert any("copier copy" in block and TEMPLATE_URL in block for block in FENCED_BLOCK.findall(readme)), (
        "README no longer contains a fenced `copier copy` block with the template URL"
    )
