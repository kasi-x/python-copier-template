"""The render twin's verdicts, on crafted states (the integration run is `slow`).

The twin's promise: a leaf outside the candidate set has an identical render
context, and none of the changed template bytes are reachable from its
rendered file set. These tests pin the candidacy rules on crafted states --
no rendering -- plus the manifest normalization the exact verdict relies on.
The whole-pipeline proof on the real template runs as a `slow` integration
test, and every deliberately-broken case here is also demonstrated against
the real template in the commit that introduced this module.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import render_delta as rd  # noqa: E402


def _state(  # noqa: PLR0913  WHYNOT: a fixture factory over the State's own fields.
    context_hashes: dict[str, str],
    file_hashes: dict[str, str],
    *,
    path_set: tuple[str, ...] = ("pyproject.toml",),
    leaves: tuple[str, ...] = ("l1", "l2"),
    include_graph: dict[str, set[str]] | None = None,
    manifests: dict[str, dict[str, str]] | None = None,
) -> rd.State:
    return rd.State(
        context_hashes=context_hashes,
        file_hashes=file_hashes,
        path_set=path_set,
        leaves=frozenset(leaves),
        include_graph=include_graph or {},
        manifests=manifests or {},
    )


def test_identical_states_have_no_candidates():
    """A no-op change must propose zero re-renders: that is the whole point."""
    state = _state({"l1": "c1", "l2": "c2"}, {"_tasks.jinja": "t1"})
    candidates, _report = rd.compute_candidates(state, state)
    assert not candidates, "an identical state cannot affect any leaf"


def test_a_context_change_candidates_exactly_the_leaves_that_changed():
    """Value flow: one leaf's internals moved, the other did not."""
    old = _state({"l1": "c1", "l2": "c2"}, {"_tasks.jinja": "t1"})
    new = _state({"l1": "c1-CHANGED", "l2": "c2"}, {"_tasks.jinja": "t1"})
    candidates, report = rd.compute_candidates(old, new)
    assert candidates == {"l1"}, "only the leaf whose context moved is a candidate"
    assert "the render context changed" in report["reasons"]["l1"][0]


def test_a_changed_template_file_candidates_the_leaves_that_render_it():
    """Content flow: the changed bytes only reach leaves whose render includes them."""
    partial = "_shared/pyproject-deps.toml.jinja"
    parent = "{% if (not existing_project or 'pyproject' not in adopt_protect) and not ros2_cpp %}pyproject.toml{% endif %}.jinja"
    changed = {partial: "v1"}
    old = _state(
        {"l1": "c", "l2": "c"},
        changed,
        include_graph={parent: {partial}},
        manifests={"l1": {"pyproject.toml": "h"}, "l2": {"README.md": "h"}},
    )
    new = _state(
        {"l1": "c", "l2": "c"},
        {**changed, partial: "v2"},
        include_graph=graph if (graph := {parent: {partial}}) else {},
        manifests={"l1": {"pyproject.toml": "h"}, "l2": {"README.md": "h"}},
    )
    candidates, _report = rd.compute_candidates(old, new)
    assert candidates == {"l1"}, "l2 never renders the changed partial, so it is unaffected"


def test_the_include_closure_spreads_the_candidates():
    """A leaf rendering a file that *includes* the changed partial is a candidate too.

    The manifest keys are destination names and the reach is template-side, so
    the comparison runs over the stripped output names (`_output_name`).
    """
    partial = "_shared/pyproject-deps.toml.jinja"
    parent = "{% if (not existing_project or 'pyproject' not in adopt_protect) and not ros2_cpp %}pyproject.toml{% endif %}.jinja"
    graph = {parent: {partial}}
    old = _state(
        {"l1": "c", "l2": "c"},
        {partial: "v1"},
        include_graph=graph,
        manifests={"l1": {"pyproject.toml": "h"}, "l2": {"other.txt": "h"}},
    )
    new = _state(
        {"l1": "c", "l2": "c"},
        {partial: "v2"},
        include_graph=graph,
        manifests=dict(old.manifests),
    )
    candidates, _report = rd.compute_candidates(old, new)
    assert candidates == {"l1"}, "l1 renders pyproject.toml, which includes the changed partial"
    assert "l2" not in candidates, "l2's render never pulls the changed bytes in"


def test_a_leaf_without_a_manifest_is_conservatively_a_candidate():
    """No recorded render means no evidence: the first run of a state renders everything."""
    old = _state({"l1": "c", "l2": "c"}, {"f.txt": "v1"}, manifests={"l1": {"f.txt": "h"}})
    new = _state({"l1": "c", "l2": "c"}, {"f.txt": "v2"}, manifests={"l1": {"f.txt": "h2"}})
    candidates, _report = rd.compute_candidates(old, new)
    assert candidates == {"l1", "l2"}, "l2 has no manifest: the change could reach it unseen"


def test_a_path_set_change_candidates_everything():
    """Added or removed template paths are visible to every leaf, so nothing is excluded."""
    old = _state({"l1": "c", "l2": "c"}, {"f.txt": "v"}, path_set=("a",))
    new = _state({"l1": "c", "l2": "c"}, {"f.txt": "v"}, path_set=("a", "b"))
    candidates, _report = rd.compute_candidates(old, new)
    assert candidates == {"l1", "l2"}, "the file set is shared by every leaf"


def test_the_answers_file_stamps_do_not_count_as_content(tmp_path: Path):
    """`_commit`/`_src_path` vary with dirty-template renders; they are not content."""
    import shutil

    stamped_dir = tmp_path / "stamped"
    stamped_dir.mkdir()
    (stamped_dir / ".copier-answers.yml").write_text(
        yaml.dump({"_commit": "aaa", "_src_path": "/x", "project_type": "cli"}), encoding="utf-8"
    )
    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    (clean_dir / ".copier-answers.yml").write_text(yaml.dump({"project_type": "cli"}), encoding="utf-8")
    assert rd._manifest(stamped_dir) == rd._manifest(clean_dir), (  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  WHYNOT: the normalization under test is the checker's own helper.
        "the per-render stamps must normalize away, or every dirty render looks changed"
    )
    shutil.rmtree(clean_dir)


@pytest.mark.slow
def test_verify_delta_proves_an_untouched_tree():
    """The integration run: an unmodified tree has no candidates and proves everything.

    Everything here is real -- the baseline checkout, the copier passes over
    all 225 leaves, the verdict. Nothing renders on the leaf side (there are
    no candidates), which is why this is the affordable whole-pipeline check.
    """
    code, payload = rd.verify(base_ref="HEAD", jobs=4, audit=0)
    assert code == 0, f"an untouched tree must prove clean: {payload['failures']}"
    assert payload["leaves"] == payload["proven"], "every leaf must be accounted for"
    assert payload["candidates"] == 0, "an untouched tree has no semantic diff, so no candidates"
