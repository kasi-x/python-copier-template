"""The render cache's invalidation rules, on a scratch template tree.

The cache's promise, per entry: a hit proves every byte the render read is
unchanged. The lookup re-hashes exactly the template files the entry's last
render consumed (its output files' sources, plus their include closure), so
the tests here craft a small template and pin the three interesting
verdicts: a hit for an untouched leaf, a miss when a consumed file changes,
and -- the point of the whole design -- a HIT when a file the leaf does not
render changes. Namespace rules too: a question change or a path-set change
is a namespace change, which conservatively invalidates everything.
"""

from __future__ import annotations

import sys
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

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
---
"""
README_JINJA = 'Hello {{ who }}.\n{% include "_shared/greeting-part.jinja" %}\n'
GREETING_PART = "partials are prose.\n"
BOT_X = "print('bot')\n"


def _scratch_tree(root: Path, *, greeting_part: str = GREETING_PART, bot_x: str = BOT_X) -> Path:
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
