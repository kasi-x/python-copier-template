"""The translated-docs stager: a translated site carries translated pages only.

architekton/docs_i18n.py assembles build/docs-i18n/<lang>/ from docs-i18n/<lang>/
(the translations, mirroring docs/) plus docs/'s non-Markdown files, and
derives a Zensical config from the root zensical.toml. The contract pinned
here: an untranslated page never reaches the translated site (not as a page,
not in nav), a nav label is the translated page's own heading, the English
config is reused except for the four keys that make it a separate site, and
an empty translation tree is an error rather than an empty site.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from architekton import docs_i18n  # noqa: E402

CONFIG = """\
[project]
site_name = "demo"
edit_uri = "edit/main/docs/"
nav = [
  { "Home" = "index.md" },
  { "Tutorials" = [
      { "Overview" = "tutorials.md" },
      { "Installation" = "tutorials/installation.md" },
  ]},
  { "Reference" = [
      { "Overview" = "reference.md" },
  ]},
]

[project.theme]
name = "material"
language = "en"
features = ["navigation.indexes"]
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _write(tmp_path / "zensical.toml", CONFIG)
    for page in ("index.md", "tutorials.md", "tutorials/installation.md", "reference.md"):
        _write(tmp_path / "docs" / page, f"# {page}\n")
    _write(tmp_path / "docs" / "images" / "logo.svg", "<svg/>")
    _write(tmp_path / "docs-i18n" / "ja" / "index.md", "# ホーム\n")
    _write(tmp_path / "docs-i18n" / "ja" / "tutorials.md", "# チュートリアル\n")
    _write(
        tmp_path / "docs-i18n" / "ja" / "tutorials" / "installation.md",
        "```md\n# fenced, not the title\n```\n\n# インストール\n",
    )
    return tmp_path


def _staged_config(repo: Path) -> dict:
    return tomllib.loads((repo / "build" / "docs-i18n" / "ja" / "zensical.toml").read_text(encoding="utf-8"))


def test_untranslated_pages_stay_out_of_the_site_and_the_nav(repo: Path) -> None:
    staged = docs_i18n.stage(repo, "ja")
    docs = staged.stage / "docs"
    assert sorted(p.relative_to(docs).as_posix() for p in docs.rglob("*.md")) == [
        "index.md",
        "tutorials.md",
        "tutorials/installation.md",
    ], "reference.md is untranslated: an English page must not leak into the ja site"
    assert _staged_config(repo)["project"]["nav"] == [
        {"ホーム": "index.md"},
        {"チュートリアル": [{"チュートリアル": "tutorials.md"}, {"インストール": "tutorials/installation.md"}]},
    ], "nav keeps translated pages only, labelled by their headings; an emptied section is dropped"
    assert (staged.pages, staged.nav_pages) == (3, 3)


def test_assets_are_staged_so_relative_links_resolve(repo: Path) -> None:
    docs_i18n.stage(repo, "ja")
    assert (repo / "build" / "docs-i18n" / "ja" / "docs" / "images" / "logo.svg").read_text() == "<svg/>"


def test_the_english_config_is_reused_except_the_site_identity(repo: Path) -> None:
    docs_i18n.stage(repo, "ja")
    project = _staged_config(repo)["project"]
    assert project["theme"]["language"] == "ja"
    assert (project["docs_dir"], project["site_dir"]) == ("docs", "site")
    assert project["edit_uri"] == "edit/main/docs-i18n/ja/", (
        "edit links must open the translation, not the English page"
    )
    assert project["site_name"] == "demo"
    assert project["theme"]["features"] == ["navigation.indexes"]


def test_restaging_drops_a_page_whose_translation_was_removed(repo: Path) -> None:
    docs_i18n.stage(repo, "ja")
    (repo / "docs-i18n" / "ja" / "tutorials" / "installation.md").unlink()
    docs_i18n.stage(repo, "ja")
    assert not (repo / "build" / "docs-i18n" / "ja" / "docs" / "tutorials" / "installation.md").exists()


def test_a_language_without_pages_is_an_error_not_an_empty_site(repo: Path) -> None:
    with pytest.raises(docs_i18n.NoTranslationsError, match="docs-i18n/de/"):
        docs_i18n.stage(repo, "de")


def test_the_root_nav_targets_exist_so_translations_can_mirror_them() -> None:
    nav = tomllib.loads((TOP / "zensical.toml").read_text(encoding="utf-8"))["project"]["nav"]

    def targets(entries: list[dict]) -> list[str]:
        return [
            leaf
            for entry in entries
            for target in entry.values()
            for leaf in ([target] if isinstance(target, str) else targets(target))
        ]

    missing = [target for target in targets(nav) if not (TOP / "docs" / target).is_file()]
    assert not missing, f"zensical.toml nav points at pages docs/ does not have: {missing}"
