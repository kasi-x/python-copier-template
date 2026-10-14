"""`.daimonion.yml` + empty ethics markers: the template's render-side contract.

The template no longer vendors kanon prose: it emits `.daimonion.yml`
(abstract `when` conditions, one per line in vocabulary order, each with a
`# <which answers produced it>` provenance comment, plus the three
commented hints for the non-derivable `jp` / `eu_market` / `ai_assisted`)
and an EMPTY marker pair in AGENTS.md that `daimonion agents-md --write`
fills in. Both `.daimonion.yml` and the composition manifest's `when:`
derive from the single `_shared/daimonion-when.jinja` macro, so the two
must agree.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools.answers import BASE  # noqa: E402

from support import render_answers  # noqa: E402
from test_daimonion_parity import derive_when  # noqa: E402

BEGIN = "<!-- daimonion:ethics:begin"
END = "<!-- daimonion:ethics:end -->"

HINTS = (
    "#  - jp           # operates under Japanese law",
    "#  - eu_market    # ships to the EU market",
    "#  - ai_assisted  # AI coding agents work here",
)

# Three contrasting presets: a bare library (library only), a scraping CLI
# with a commercial distribution (cli + scraping + commercial), and a kaggle
# workspace (kaggle only -- data_science must NOT fire: the derivation uses
# data_science_layout, not ds_stack).
CASES: tuple[tuple[str, dict[str, object]], ...] = (
    ("library", {"project_type": "library"}),
    (
        "cli-scraping-commercial",
        {"project_type": "cli", "include_scraping": True, "distribution": ["commercial"]},
    ),
    (
        "kaggle",
        {"project_type": "online_judge", "oj_category": "data_science", "oj_kind": "kaggle"},
    ),
)


def _render(tmp_path: Path, answers: dict[str, object]) -> Path:
    target = tmp_path / "proj"
    render_answers(target, {**BASE, **answers}, run_tasks=False)
    return target


def _when_lines(path: Path) -> list[str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["agents_md"] == "AGENTS.md"
    assert isinstance(payload.get("when"), list)
    return [str(item) for item in payload["when"]]


@pytest.mark.parametrize("label,overrides", CASES, ids=[label for label, _ in CASES])
def test_daimonion_yml_when_list(tmp_path: Path, label: str, overrides: dict[str, object]) -> None:
    """`.daimonion.yml` carries exactly the derived `when` set, in order."""
    root = _render(tmp_path, overrides)
    config = root / ".daimonion.yml"
    assert config.is_file(), f"{label}: the render must emit .daimonion.yml"
    assert _when_lines(config) == derive_when({**BASE, **overrides}), f"{label}: when list drifted"
    text = config.read_text(encoding="utf-8")
    for hint in HINTS:
        assert hint in text, f"{label}: missing hint {hint!r}"


def test_kaggle_does_not_derive_data_science(tmp_path: Path) -> None:
    """The kaggle workspace derives `kaggle`, not `data_science` (layout, not stack)."""
    root = _render(tmp_path, {"project_type": "online_judge", "oj_category": "data_science", "oj_kind": "kaggle"})
    assert _when_lines(root / ".daimonion.yml") == ["kaggle"]


def test_agents_md_carries_empty_markers_and_no_prose(tmp_path: Path) -> None:
    """AGENTS.md ships the empty marker pair and no vendored section prose."""
    root = _render(tmp_path, {"project_type": "cli", "include_scraping": True})
    guide = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert BEGIN in guide and END in guide, "the empty marker pair must be present"
    assert guide.index(BEGIN) < guide.index(END), "begin must precede end"
    block = guide[guide.index(BEGIN) : guide.index(END)]
    assert "スクレイピングの適法性" not in block, "no vendored section prose may remain"
    assert "ライセンス変動" not in guide, "no vendored section prose may remain"


def test_manifest_when_matches_config(tmp_path: Path) -> None:
    """The composition manifest's `when:` is the same list the config carries."""
    root = _render(tmp_path, {"project_type": "cli", "include_scraping": True, "distribution": ["commercial"]})
    manifest = yaml.safe_load((root / ".architekton-manifest.yml").read_text(encoding="utf-8"))
    config = yaml.safe_load((root / ".daimonion.yml").read_text(encoding="utf-8"))
    assert manifest["when"] == config["when"], "manifest and config when-lists must agree"
