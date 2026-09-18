"""Machine gate: statically catch template breakage before render tests.

Fast, offline, no uv sync: parses every .jinja source with Jinja2, every
questions/*.yml with YAML, and asserts the resolved questionnaire loads via
copier's own loader. A syntax break (unbalanced if/endif, bad YAML) fails
here in milliseconds instead of surfacing as a cryptic render error in the
slow test_example_* suites.
"""

import re
import sys
from collections import Counter
from pathlib import Path

import jinja2
import pytest
import yaml
from copier._template import load_template_config
from jinja2 import nodes

from render_cache import RenderCache
from render_cache import render_cache as render_cache  # noqa: PLC0414  # the session fixture, made visible here
from test_copier_structure import COPIER_YML
from test_copier_structure import QUESTIONS_DIR
from test_copier_structure import TOP
from test_copier_structure import shared_files
from test_copier_structure import template_files

sys.path.insert(0, str(TOP))  # tests/test_marker_drift.py does the same to reach tools/

from tools.render_inputs import render_input_paths  # noqa: E402


def test_all_jinja_sources_parse():
    """Every .jinja source (template/ + _shared/ + _tasks.jinja) parses."""
    env = jinja2.Environment()
    broken = []
    for f in template_files():
        if not f.is_file() or f.suffix != ".jinja":
            continue
        try:
            env.parse(f.read_text(encoding="utf-8"))
        except jinja2.TemplateSyntaxError as e:
            broken.append(f"{f.relative_to(TOP)}: {e}")
        except (UnicodeDecodeError, OSError):
            continue
    # _tasks.jinja has no .jinja suffix but is a Jinja source
    tasks = TOP / "_tasks.jinja"
    try:
        env.parse(tasks.read_text(encoding="utf-8"))
    except jinja2.TemplateSyntaxError as e:
        broken.append(f"_tasks.jinja: {e}")
    assert not broken, "unparsable Jinja sources:\n" + "\n".join(broken)


def test_all_question_fragments_parse_as_yaml():
    """Every questions/*.yml fragment parses as YAML."""
    broken = []
    for f in sorted(QUESTIONS_DIR.rglob("*.yml")):
        try:
            yaml.safe_load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            broken.append(f"{f.name}: {e}")
    assert not broken, "unparsable question fragments:\n" + "\n".join(broken)


def test_resolved_questionnaire_loads():
    """Copier's own loader resolves the questionnaire (!include chain)."""
    data = load_template_config(COPIER_YML)
    questions = {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}
    # One question from copier.yml itself plus one from each include chain
    # kind: a dropped !include would silently shrink the questionnaire.
    assert {"project_type", "existing_project", "oj_kind", "micropython_port"} <= questions.keys()


def test_shared_partials_are_all_consumed():
    """Every _shared/*.jinja partial is included from somewhere.

    An orphan partial is dead code that silently stops tracking its
    consumer's conditions — either wire it or delete it.
    """
    consumers = []
    for f in template_files():
        if not f.is_file() or f.suffix != ".jinja":
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        consumers.append(text)
    blob = "\n".join(consumers)
    orphaned = [p.name for p in shared_files() if p.name not in blob]
    assert not orphaned, f"orphan _shared/ partials (not included anywhere): {orphaned}"


# The include/import tag form the render-inputs module can attribute: a plain
# double-quoted literal target, optionally followed by static tag grammar
# (`as NAME`, `with/without context`, `ignore missing`, an imported-name
# list) -- words, whitespace and commas only. Kept in sync with
# tools/render_inputs.py's INCLUDE_TAG, which this strengthens in one way the
# regex itself cannot say: any operator or second quote after the literal
# (`{% include "a" ~ b %}`) makes the target an expression that
# INCLUDE_TAG happily prefix-matches while `resolve_include_target` then
# resolves nothing -- a dynamic target wearing a literal's clothes. If the
# graph is ever taught dynamic targets, relax this to match what it can
# really see.
VISIBLE_INCLUDE = re.compile(r'\{%-?\s+(?:include|import)\s+"[^"]+"[\w\s,-]*%}')


def _untrackable_include_lines(text: str) -> list[tuple[int, str]]:
    """`(lineno, line)` for every include/import tag the include graph cannot see.

    The graph (tools/render_inputs.py, shared by the render cache and the
    render twin) follows only tags whose target is a plain double-quoted
    literal; VISIBLE_INCLUDE above is that form, anchored at the tag's close.
    Jinja's own parse finds the tags (so
    one quoted inside a `{# #}` comment, a docstring or a `{% raw %}` block is
    ignored, not flagged), and a found tag counts as seen when a
    VISIBLE_INCLUDE match starts on its line: the target must be a
    double-quoted literal opening on the tag's first line, though the literal
    itself may continue across lines. Tags are compared per line, so a
    literal and a dynamic tag sharing one line is still caught.

    A file that does not parse as Jinja at all (a LaTeX body, a workflow with
    ``${{ }}`` GitHub expressions) cannot be node-scanned, but copier still
    executes it as a template: fall back to a broad textual scan where every
    include/import tag start counts as untrackable until proven otherwise.
    """
    lines = text.splitlines()
    try:
        tree = jinja2.Environment().parse(text)
    except jinja2.TemplateSyntaxError:
        broad = re.compile(r"\{%-?\s*(?:include|import)\b")
        return [(number, line.strip()) for number, line in enumerate(lines, start=1) if broad.search(line)]
    tags_per_line: Counter[int] = Counter()
    for kind in (nodes.Include, nodes.Import, nodes.FromImport):
        for node in tree.find_all(kind):
            tags_per_line[node.lineno] += 1
    seen_per_line: Counter[int] = Counter(
        text.count("\n", 0, match.start()) + 1 for match in VISIBLE_INCLUDE.finditer(text)
    )
    return [
        (lineno, lines[lineno - 1].strip())
        for lineno in sorted(tags_per_line)
        if tags_per_line[lineno] > seen_per_line.get(lineno, 0)
    ]


def test_the_include_scanner_judges_only_double_quoted_literals_visible():
    """The scanner's verdicts on inline fixtures: probes are how this repo
    keeps a detector honest (the PROBE pattern of tests/test_marker_drift.py,
    tests/test_copier_structure.py's injected-bug meta tests)."""
    assert _untrackable_include_lines('{% include "_shared/x.jinja" %}') == []
    assert _untrackable_include_lines('{%- import "_tasks.jinja" as _t with context -%}') == []
    # `{% from %}` pulls the file in just the same, but the graph's regex only
    # knows the `include`/`import` keywords: it is untrackable too, so it
    # stays in the guarded class (write `{% import %}` instead).
    assert _untrackable_include_lines('{% from "_shared/macros.jinja" import python_version %}') != []
    # The graph's regex spans newlines, so a literal opening on the tag's
    # first line is seen however the tag is wrapped.
    assert _untrackable_include_lines('{% import\n    "_shared/macros.jinja" as m %}') == []
    # A tag inside a comment or a raw block is not a tag.
    assert _untrackable_include_lines('{# {% include "ghost.jinja" %} #}') == []
    assert _untrackable_include_lines("{% raw %}{% include raw.jinja %}{% endraw %}") == []
    # A variable target is the blind spot this guards: it renders fine, the
    # graph just cannot attribute it.
    assert _untrackable_include_lines("{% include some_var %}") == [(1, "{% include some_var %}")]
    # A literal that opens but does not close the tag: the graph's regex
    # matches the leading quote and resolves nothing, so it is invisible too.
    assert _untrackable_include_lines('{% include "pre_" ~ name %}') != []
    # A single-quoted literal is not the graph's form either.
    assert _untrackable_include_lines("{% import '_shared/macros.jinja' as m %}") != []
    # A literal and a dynamic tag on one line: the line is flagged.
    assert _untrackable_include_lines('{% include "a.jinja" %} {% include b %}') != []


def test_include_and_import_targets_are_all_literals_the_graph_sees():
    """Every include/import tag in the render inputs is a double-quoted literal.

    The render cache records the files a render consumed via that literal
    include graph, so a dynamic target ({% include some_var %}) would render
    but never appear in an entry's recorded inputs: edits to its target file
    would not invalidate the entry, and the cache would keep serving a stale
    tree as a hit. That is the one render input class the fingerprint cannot
    see, which is why this is guarded rather than supported: zero dynamic
    includes exist today, and adding one must be a loud decision (extend
    tools/render_inputs.py's graph, not around it).
    """
    problems = []
    for path in render_input_paths(TOP):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in _untrackable_include_lines(text):
            problems.append(f"{path.relative_to(TOP)}:{lineno}: {line}")
    assert not problems, (
        "dynamic include/import targets -- the render cache cannot see them, "
        "so edits to their targets would never invalidate a cached render:\n" + "\n".join(problems)
    )


RENDER_MATRIX: list[dict[str, object]] = [
    {"project_type": "library"},
    {"project_type": "cli", "include_ctf": True},
    {"project_type": "web_api"},
    {"project_type": "data_science"},
    {
        "project_type": "online_judge",
        "oj_category": "data_science",
        "oj_kind": "kaggle",
    },
    {
        "project_type": "online_judge",
        "oj_category": "competitive_coding",
        "oj_kind": "atcoder",
    },
    {"project_type": "online_judge", "oj_category": "ctf", "oj_kind": "ctf"},
    {"project_type": "micropython", "micropython_port": "esp32"},
    {
        "project_type": "ros2",
        "pkg_language": "python",
        "ros_distro": "humble",
        "ros2_package_manager": "apt",
    },
]


def _matrix_id(answers: dict[str, object]) -> str:
    return "-".join(f"{k}={v}" for k, v in answers.items())


@pytest.mark.parametrize("answers", RENDER_MATRIX, ids=[_matrix_id(a) for a in RENDER_MATRIX])
def test_render_matrix_renders_and_parses(tmp_path: Path, render_cache: RenderCache, answers: dict[str, object]):
    """Every matrix path renders; pyproject.toml (when generated) parses.

    Catches unbalanced Jinja that only triggers on one branch (e.g. a
    missing endif inside {% if oj_code %}) and TOML-breaking output, in
    seconds (skip_tasks, no uv sync). The render goes through the session
    cache -- the same pure render (skip_tasks, HEAD) a fresh run_copy would
    produce -- so the edit loop pays for each combination once. Deep content
    assertions belong to tests/test_example_*.py; this gate proves
    renderability.
    """
    import tomllib

    from tools.answers import BASE

    render_cache.render(tmp_path, {**BASE, **answers})
    assert not list(tmp_path.rglob("*.jinja")), "unrendered .jinja files left"
    pyproject = tmp_path / "pyproject.toml"
    if pyproject.exists():
        try:
            tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            pytest.fail(f"rendered pyproject.toml does not parse ({_matrix_id(answers)}): {e}")
