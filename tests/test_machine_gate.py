"""Machine gate: statically catch template breakage before render tests.

Fast, offline, no uv sync: parses every .jinja source with Jinja2, every
questions/*.yml with YAML, and asserts the resolved questionnaire loads via
copier's own loader. A syntax break (unbalanced if/endif, bad YAML) fails
here in milliseconds instead of surfacing as a cryptic render error in the
slow test_example.py suite.
"""

from pathlib import Path

import jinja2
import pytest
import yaml
from copier._template import load_template_config

from test_copier_structure import COPIER_YML
from test_copier_structure import QUESTIONS_DIR
from test_copier_structure import TOP
from test_copier_structure import shared_files
from test_copier_structure import template_files


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
    assert "project_type" in questions
    assert len(questions) > 30, f"suspiciously few questions: {len(questions)}"


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
def test_render_matrix_renders_and_parses(tmp_path: Path, answers: dict[str, object]):
    """Every matrix path renders; pyproject.toml (when generated) parses.

    Catches unbalanced Jinja that only triggers on one branch (e.g. a
    missing endif inside {% if oj_code %}) and TOML-breaking output, in
    seconds (skip_tasks, no uv sync). Deep content assertions belong to
    test_example.py; this gate proves renderability.
    """
    import tomllib

    from copier import run_copy

    from test_recommended_path import BASE

    run_copy(
        src_path=str(TOP),
        dst_path=tmp_path,
        data={**BASE, **answers},
        vcs_ref="HEAD",
        defaults=True,
        unsafe=True,
        overwrite=True,
        skip_tasks=True,
    )
    assert not list(tmp_path.rglob("*.jinja")), "unrendered .jinja files left"
    pyproject = tmp_path / "pyproject.toml"
    if pyproject.exists():
        try:
            tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            pytest.fail(f"rendered pyproject.toml does not parse ({_matrix_id(answers)}): {e}")
