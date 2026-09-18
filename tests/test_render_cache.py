"""The render cache's invalidation rules, on a scratch template tree.

The cache's promise, per entry: a hit proves every byte the render read is
unchanged. The lookup re-hashes exactly the template files the entry's last
render consumed (its output files' sources, plus their include closure), so
the tests here craft a small template and pin the three interesting
verdicts: a hit for an untouched leaf, a miss when a consumed file changes,
and -- the point of the whole design -- a HIT when a file the leaf does not
render changes. Namespace rules too: a question change, a path-set change,
or a render-toolchain (copier/jinja2) version change is a namespace change,
which conservatively invalidates everything. The module also guards the
placement constraint the render helpers live under: they must never move
into conftest.py, because the template renders that file (via a symlink)
into generated projects that have neither copier nor fcntl to import.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

import render_cache  # noqa: E402
from render_cache import RenderCache  # noqa: E402

# A minimal template: one always-rendered file, one conditionally-rendered
# file, one partial included by the always file. `who` steers the greeting.
COPIER_YML = """---
_subdirectory: template
who:
    type: str
    default: world
bot:
    type: bool
    default: false
pkg_dir:
    type: str
    default: pkg
---
"""
README_JINJA = 'Hello {{ who }}.\n{% include "_shared/greeting-part.jinja" %}\n'
GREETING_PART = "partials are prose.\n"
BOT_X = "print('bot')\n"


BOT_PART = "bot body v1.\n"


def _scratch_tree(
    root: Path, *, greeting_part: str = GREETING_PART, bot_x: str = BOT_X, bot_part: str = BOT_PART
) -> Path:
    (root / "questions").mkdir(parents=True, exist_ok=True)
    # questions/*.yml is only hashed (the namespace reads the bytes); the
    # questionnaire itself is copier.yml's inline questions here.
    (root / "copier.yml").write_text(COPIER_YML, encoding="utf-8")
    template = root / "template"
    template.mkdir(parents=True, exist_ok=True)
    (template / "README.md.jinja").write_text(README_JINJA, encoding="utf-8")
    # the partial lives at the repo-root level, like the real _shared/
    (root / "_shared").mkdir(parents=True, exist_ok=True)
    (root / "_shared" / "greeting-part.jinja").write_text(greeting_part, encoding="utf-8")
    (template / "{% if bot %}bot.py{% endif %}.jinja").write_text(bot_x, encoding="utf-8")
    # A `{{ pkg_dir }}`-interpolated path whose body is a _shared partial:
    # the shape the real pkg tree uses for the bot platforms, and the case
    # the recorded-inputs suffix rule exists for.
    (root / "_shared" / "bot-part.jinja").write_text(bot_part, encoding="utf-8")
    pkg = template / "{% if bot %}{{ pkg_dir }}{% endif %}"
    pkg.mkdir(exist_ok=True)
    (pkg / "bot.py.jinja").write_text('{% include "_shared/bot-part.jinja" %}\n', encoding="utf-8")
    return root


ANSWERS_NO_BOT: dict[str, object] = {"who": "a", "bot": False}
ANSWERS_BOT: dict[str, object] = {"who": "a", "bot": True}


def test_hit_for_identical_answers_and_identical_template(tmp_path: Path):
    """The second render of the same (answers, template) is a cache hit."""
    tree = _scratch_tree(tmp_path / "tree")
    cache = RenderCache(root=tmp_path / "cache", template_root=tree)
    one = cache.render(tmp_path / "one", dict(ANSWERS_NO_BOT))
    assert (one / "README.md").read_text().startswith("Hello a.")
    before = cache.renders
    two = cache.render(tmp_path / "two", dict(ANSWERS_NO_BOT))
    assert cache.renders == before, "the second identical render must be a hit"
    assert (two / "README.md").read_text() == (one / "README.md").read_text()


def test_an_edit_to_a_consumed_file_misses_and_changes_the_output(tmp_path: Path):
    """A consumed partial's edit invalidates, and the new bytes are served."""
    tree = _scratch_tree(tmp_path / "tree")
    cache = RenderCache(root=tmp_path / "cache", template_root=tree)
    one = cache.render(tmp_path / "one", dict(ANSWERS_NO_BOT))
    (tree / "_shared" / "greeting-part.jinja").write_text("partials are EDITED.\n", encoding="utf-8")
    two = cache.render(tmp_path / "two", dict(ANSWERS_NO_BOT))
    assert "EDITED" in (two / "README.md").read_text(), "the edited partial must reach the new render"
    assert "EDITED" not in (one / "README.md").read_text(), "the old render must be untouched"


def test_an_edit_to_a_file_the_leaf_does_not_render_is_a_hit(tmp_path: Path):
    """THE leaf-scoping win: a bot-file edit cannot touch a no-bot render."""
    tree = _scratch_tree(tmp_path / "tree")
    cache = RenderCache(root=tmp_path / "cache", template_root=tree)
    one = cache.render(tmp_path / "one", dict(ANSWERS_NO_BOT))
    (tree / "template" / "{% if bot %}bot.py{% endif %}.jinja").write_text("print('EDITED')\n", encoding="utf-8")
    two = cache.render(tmp_path / "two", dict(ANSWERS_NO_BOT))
    assert cache.reuses >= 1, "a file the leaf does not render must not invalidate it"
    assert (two / "README.md").read_text() == (one / "README.md").read_text()


def test_the_same_edit_misses_for_a_leaf_that_renders_the_file(tmp_path: Path):
    """The bot render consumes the bot file, so the same edit misses there."""
    tree = _scratch_tree(tmp_path / "tree")
    cache = RenderCache(root=tmp_path / "cache", template_root=tree)
    cache.render(tmp_path / "bot-render", dict(ANSWERS_BOT))
    (tree / "template" / "{% if bot %}bot.py{% endif %}.jinja").write_text("print('EDITED')\n", encoding="utf-8")
    two = cache.render(tmp_path / "bot-render-2", dict(ANSWERS_BOT))
    assert "EDITED" in (two / "bot.py").read_text(), "the bot leaf must see the new bytes"


def test_a_question_change_is_a_namespace_change(tmp_path: Path):
    """A questionnaire edit conservatively invalidates every entry."""
    tree = _scratch_tree(tmp_path / "tree")
    cache = RenderCache(root=tmp_path / "cache", template_root=tree)
    cache.render(tmp_path / "before", dict(ANSWERS_NO_BOT))
    (tree / "copier.yml").write_text(COPIER_YML + "# a comment changes the state\n", encoding="utf-8")
    reconnected = RenderCache(root=tmp_path / "cache", template_root=tree)
    reconnected.render(tmp_path / "after", dict(ANSWERS_NO_BOT))
    assert reconnected.renders == 1, "a question-state change must miss"


def test_a_path_set_change_is_a_namespace_change(tmp_path: Path):
    """A new template file could render for any leaf: everything re-renders."""
    tree = _scratch_tree(tmp_path / "tree")
    cache = RenderCache(root=tmp_path / "cache", template_root=tree)
    cache.render(tmp_path / "before", dict(ANSWERS_NO_BOT))
    (tree / "template" / "new-file.txt.jinja").write_text("new\n", encoding="utf-8")
    reconnected = RenderCache(root=tmp_path / "cache", template_root=tree)
    after = reconnected.render(tmp_path / "after", dict(ANSWERS_NO_BOT))
    assert reconnected.renders >= 1, "a path-set change must not serve the old render"
    assert (after / "new-file.txt").exists(), "the new file must reach the render"


def test_a_pkg_dir_body_partial_is_recorded_and_invalidates(tmp_path: Path):
    """A `{{ pkg_dir }}`-owned body's _shared partial is a recorded input.

    The pkg tree's sources interpolate the package directory into their
    template paths, so matching them to rendered outputs needs the suffix
    rule: an exact-name match drops every pkg-tree body from the recorded
    inputs, and an edit to the _shared partial it includes (the real
    _shared/bot-*.py.jinja shape) then keeps serving a stale bot render.
    Found while landing the gmail platform slice (TODO archive §4).
    """
    tree = _scratch_tree(tmp_path / "tree")
    cache = RenderCache(root=tmp_path / "cache", template_root=tree)
    cache.render(tmp_path / "one", dict(ANSWERS_BOT))
    inputs = json.loads(next(cache.namespace.glob("*.inputs.json")).read_text(encoding="utf-8"))
    assert "_shared/bot-part.jinja" in inputs, "the pkg tree's _shared partial must be recorded as a consumed input"

    (tree / "_shared" / "bot-part.jinja").write_text("bot body EDITED.\n", encoding="utf-8")
    reconnected = RenderCache(root=tmp_path / "cache", template_root=tree)
    reconnected.render(tmp_path / "two", dict(ANSWERS_BOT))
    assert reconnected.renders == 1, "an edit to the pkg body's partial must miss"
    assert "bot body EDITED." in (tmp_path / "two" / "pkg" / "bot.py").read_text(encoding="utf-8")


def test_stale_entries_are_pruned_on_open(tmp_path: Path):
    """An entry whose consumed bytes moved on is deleted, not left to rot."""
    tree = _scratch_tree(tmp_path / "tree")
    cache = RenderCache(root=tmp_path / "cache", template_root=tree)
    cache.render(tmp_path / "one", dict(ANSWERS_NO_BOT))
    (tree / "_shared" / "greeting-part.jinja").write_text("partials are EDITED.\n", encoding="utf-8")
    reconnected = RenderCache(root=tmp_path / "cache", template_root=tree)
    # opening the cache is what prunes: the stale entry's tree and manifest
    # are gone, because its recorded inputs no longer describe the template
    namespace = reconnected.namespace
    assert not (namespace / "one.done").exists(), "the stale entry must be pruned on open"
    assert not (namespace / "one.inputs.json").exists(), "the stale entry's manifest must be pruned with it"


def test_a_render_toolchain_change_is_a_namespace_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A copier/jinja2 bump must not keep serving renders the old version made.

    The template bytes are untouched, so only the toolchain versions in the
    namespace state can break the hit -- monkeypatched here at the version
    source the namespace digest reads (render_cache._dist_version).
    """
    tree = _scratch_tree(tmp_path / "tree")
    cache = RenderCache(root=tmp_path / "cache", template_root=tree)
    cache.render(tmp_path / "before", dict(ANSWERS_NO_BOT))
    monkeypatch.setattr(render_cache, "_dist_version", lambda distribution: f"0.0-bumped-{distribution}")
    reconnected = RenderCache(root=tmp_path / "cache", template_root=tree)
    reconnected.render(tmp_path / "after", dict(ANSWERS_NO_BOT))
    assert reconnected.renders == 1, "a render-toolchain version change must miss"
    assert reconnected.namespace != cache.namespace, "the bumped toolchain must live in a new namespace"


def test_the_same_render_toolchain_still_hits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The version fingerprint reads the environment once per namespace: with
    the (monkeypatched) environment unchanged, the entry still hits."""
    tree = _scratch_tree(tmp_path / "tree")
    versions = dict.fromkeys(render_cache.RENDER_TOOLCHAIN, "9.9.9-test")
    monkeypatch.setattr(render_cache, "_dist_version", versions.__getitem__)
    cache = RenderCache(root=tmp_path / "cache", template_root=tree)
    cache.render(tmp_path / "one", dict(ANSWERS_NO_BOT))
    reconnected = RenderCache(root=tmp_path / "cache", template_root=tree)
    reconnected.render(tmp_path / "two", dict(ANSWERS_NO_BOT))
    assert reconnected.renders == 0, "the same toolchain versions must serve the entry"


def test_the_render_records_its_resolved_answers(tmp_path: Path):
    """The post-questionnaire answers ride the entry, for support.py's task replay.

    copier's `_tasks` render against the questionnaire pass's resolved answer
    set, not the raw input answers, so the render persists what its pass
    produced: the payload rebuilds into an AnswersMap serving the same
    `combined` answers, minus the live context singletons copier re-adds.
    """
    tree = _scratch_tree(tmp_path / "tree")
    cache = RenderCache(root=tmp_path / "cache", template_root=tree)
    cache.render(tmp_path / "one", dict(ANSWERS_NO_BOT))
    stored = cache.stored_answers(dict(ANSWERS_NO_BOT))
    assert stored is not None, "a filled entry must record its questionnaire pass"
    assert stored["combined"]["who"] == "a" and stored["combined"]["bot"] is False
    assert "now" not in stored["combined"], "DEFAULT_DATA singletons stay out of the payload"
    rebuilt = render_cache.answers_map_from_payload(stored)
    assert rebuilt.combined["who"] == "a" and rebuilt.combined["bot"] is False
    assert callable(rebuilt.combined["now"]), "copier re-supplies the live context singletons"
    assert rebuilt.hidden == set(), "the scratch questionnaire hides nothing"
    assert cache.stored_answers({"who": "unrendered"}) is None, "another answer set has no record"


def test_render_helpers_stay_out_of_conftest():
    """The render helpers' placement constraint, stated mechanically.

    tests/render_cache.py and tests/support.py import copier and fcntl, so
    they must never move into tests/conftest.py: the template renders that
    file into every generated project -- the template-side conftest.py is a
    symlink to the repo's own -- and a generated project has neither copier
    nor fcntl to import. The symlink is what makes the constraint bite, so
    its existence is asserted here too.
    """
    conftest = TOP / "tests" / "conftest.py"
    rendered = sorted((TOP / "template").glob("*tests*/conftest.py"))
    assert rendered, "the template must still ship a (symlinked) tests/conftest.py"
    for link in rendered:
        assert link.is_symlink() and link.resolve() == conftest.resolve(), (
            f"{link} must stay a symlink to the repo's conftest.py -- that is what "
            "renders this file into generated projects"
        )
    imported: set[str] = set()
    for node in ast.walk(ast.parse(conftest.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    render_only = {"copier", "fcntl", "render_cache", "support"}
    assert not imported & render_only, (
        f"tests/conftest.py imports {sorted(imported & render_only)}: it renders into generated "
        "projects that have neither copier nor fcntl nor this suite's helpers (see the "
        "render_cache.py/support.py docstrings)"
    )
