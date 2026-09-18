"""The vendored license set is the one source three consumers must agree on.

``tools/licenses/*.txt`` (+ ``_meta.json``) is the vendored
choosealicense.com corpus; ``tools/generate_license_template.py`` turns it
into the template's LICENSE if/elif chain, and the ``license:`` question
offers the same set interactively. Nothing executed the generator
end-to-end (TODO archive §19), so this module pins the three views
together without running it: the chain cannot silently gain or lose a
license, the questionnaire cannot offer one the chain would not render,
and the two reserved (non-vendored) branches keep existing.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import generate_license_template as gen  # noqa: E402
from tools import questionnaire  # noqa: E402

LICENSES_DIR = TOP / "tools" / "licenses"
LICENSE_TEMPLATE = next((TOP / "template").glob("*LICENSE*.jinja"))
# The two hand-written branches the generator itself appends (its docstring:
# "Proprietary" and "Confidential" bodies are not vendored texts).
RESERVED = {"Proprietary", "Confidential"}


def _vendored() -> set[str]:
    """The SPDX ids in the vendored corpus (`_meta.json` is the registry)."""
    meta = json.loads((LICENSES_DIR / "_meta.json").read_text(encoding="utf-8"))
    return {info["spdx"] for info in meta.values()}


def _chain() -> list[str]:
    """The license ids the LICENSE template renders, in chain order."""
    text = LICENSE_TEMPLATE.read_text(encoding="utf-8")
    tags = re.findall(r'{% (if|elif) license_effective == "([^"]+)" -?%}', text)
    assert tags, f"the LICENSE template lost its if/elif chain: {LICENSE_TEMPLATE.name}"
    assert [tag for tag, _ in tags] == ["if"] + ["elif"] * (len(tags) - 1), (
        "the LICENSE chain must be a single `if` followed by `elif`s, exactly as"
        " tools/generate_license_template.py renders it"
    )
    return [spdx for _, spdx in tags]


def _offered() -> set[str]:
    """The values the live questionnaire's `license:` question offers."""
    questions = questionnaire.load_questions()[0]
    return set(next(q for q in questions if q.name == "license").choices)


def test_license_chain_covers_exactly_the_vendored_set():
    chain = _chain()
    assert len(chain) == len(set(chain)), "a license renders twice in the LICENSE chain"
    assert set(chain) - RESERVED == _vendored(), (
        "the LICENSE if/elif chain and tools/licenses/ disagree: the generator"
        " (tools/generate_license_template.py) would regenerate a different chain"
    )
    assert set(chain) >= RESERVED, f"the reserved branches went missing: {sorted(RESERVED - set(chain))}"


def test_license_question_offers_exactly_the_vendored_set():
    assert _offered() == _vendored() | RESERVED, (
        "the license: question offers a value outside tools/licenses/ + the reserved"
        " branches (or hides one): answering it would render a branch the generator"
        " cannot reproduce"
    )


def test_generator_regenerates_the_shipped_template_byte_for_byte():
    """The generator's declared output path + bytes must match the shipped file.

    The output path is a gated copier name
    ("{% if ... %}LICENSE{% endif %}.jinja"), so a stale hard-coded
    "LICENSE.jinja" used to silently write a *stray* file while the real
    template drifted. Importing the module (instead of subprocess) keeps this
    a file-read-only fast test.
    """
    assert gen.render_chain(gen.load_licenses()) == LICENSE_TEMPLATE.read_text(encoding="utf-8"), (
        f"tools/generate_license_template.py no longer reproduces {LICENSE_TEMPLATE.name}"
        " byte for byte; run it and commit the regeneration (or fix the generator)"
    )
