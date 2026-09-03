"""Structural maintenance checks for copier.yml and the questionnaire docs.

test_micropython_maintenance.py guards the MicroPython pins the same way:
static, offline assertions over the template source that catch drift early.
This module guards the questionnaire's shape:

- the `use_recommended_*` gates appear in the canonical order and are
  well-formed bool questions;
- docs/reference/questionnaire.md's gate table stays in sync with copier.yml;
- every variable referenced in a question's `when`/`default`/`choices` or in a
  `template/` conditional exists (a removed question leaves a dangling
  reference — the ascii_banner removal regressed exactly this way);
- every `when: false` internal variable is actually used somewhere (no dead
  hidden variables).
"""

import re
from contextlib import suppress
from pathlib import Path

import yaml

TOP = Path(__file__).absolute().parent.parent
COPIER_YML = TOP / "copier.yml"
QUESTIONNAIRE_DOC = TOP / "docs" / "reference" / "questionnaire.md"
TEMPLATE_DIR = TOP / "template"

# The canonical gate order — matches the order asked in copier.yml (project
# type first, then each area, then Project Details).
CANONICAL_GATES = [
    "use_recommended_agent",
    "use_recommended_toolchain",
    "use_recommended_data_science",
    "use_recommended_polish",
    "use_recommended_docs",
    "use_recommended_quality",
    "use_recommended_license",
    "use_recommended_integrations",
    "use_recommended_web_api",
    "use_recommended_security",
]

# Copier/Jinja built-ins and the custom extension globals (extensions.py) that
# may appear in `{{ }}` expressions without being copier.yml keys.
ALLOWED_NON_KEYS = {
    "_copier_answers",
    "_copier_conf",
    "_commit",
    "_folder_name",
    "_src_path",
    "_dst_path",
    "_copier_templates_dir",
    "_copier_subdirectory",
    "git_user_name",
    "git_user_email",
    "github_username",
    "current_year",
    "now",
    "today",
    # Jinja / copier built-in filters and tests used in the questionnaire.
    "regex_search",
    "replace",
    "lower",
    "upper",
    "length",
    "to_nice_yaml",
    "tojson",
    "map",
    "join",
    "trim_start_matches",
    "date",
    "striptags",
    "split",
    "truncate",
}

_QUESTION_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:\s*$")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _load_questions() -> tuple[dict[str, dict], list[str]]:
    """Return ({key: raw-question-dict}, ordered-keys) from copier.yml.

    Copier.yml is parsed as YAML for structure, but the ordering (which
    matters: gates before their detail questions) is read from the raw text.
    """
    data = yaml.safe_load(COPIER_YML.read_text(encoding="utf-8"))
    questions = {k: v for k, v in data.items() if isinstance(v, dict)}
    order: list[str] = []
    for line in COPIER_YML.read_text(encoding="utf-8").splitlines():
        m = _QUESTION_KEY.match(line)
        if m and line[0] != " ":
            key = m.group(0)[:-1]
            if key in questions:
                order.append(key)
    return questions, order


def _jinja_identifiers(text: str) -> set[str]:
    """All identifiers inside {{ }} / {% %} blocks in ``text``.

    Only full Jinja tags are scanned (a stray ``{``/``}`` in a template body
    is never treated as a tag boundary). Within each tag, string literals
    (e.g. ``== 'ros2'``) and Jinja keywords are not identifiers; GitHub
    Actions expressions (``${{ secrets.X }}``) are not Jinja and are skipped.
    """
    found: set[str] = set()
    # GitHub Actions expressions (${{ secrets.X }}) are not Jinja; blank them
    # out first so they are never scanned.
    text = re.sub(r"\$\{\{[^}]*\}\}", " ", text)
    # {% raw %}...{% endraw %} blocks are emitted verbatim for another tool
    # (git-cliff's cliff.toml.jinja), not rendered by copier.
    text = re.sub(r"\{%-?\s*raw\s*-?%\}.*?\{%-?\s*endraw\s*-?%\}", " ", text, flags=re.DOTALL)
    for tag in re.findall(r"\{\{.*?\}\}|\{%.*?%\}", text, re.DOTALL):
        # Drop quoted strings inside this tag only — tag-internal quotes like
        # == "BSL-1.0" must not span across to quotes in the body text.
        stripped = re.sub(r"'[^']*'|\"[^\"]*\"", " ", tag)
        for m in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", stripped):
            # Attribute access: in `x.attr`, `attr` is not a variable.
            if m.start() > 0 and stripped[m.start() - 1] == ".":
                continue
            # Keyword argument: in `filter(keyword=value)`, `keyword` is not a
            # variable (`==` comparisons are unaffected — two '=' signs).
            rest = stripped[m.end() :]
            if rest.startswith("=") and not rest.startswith("=="):
                continue
            found.add(m.group(0))
    return found


_JINJA_IF_WORDS = {
    "if",
    "elif",
    "else",
    "endif",
    "for",
    "endfor",
    "set",
    "endset",
    "import",
    "from",
    "as",
    "with",
    "context",
    "in",
    "not",
    "and",
    "or",
    "is",
    "defined",  # {% if x is defined %}
    "true",
    "false",
    "none",
    "None",
    "_",  # {% set _ = ... %} loop-accumulator idiom
}


def _is_known(name: str, keys: set[str]) -> bool:
    return name in keys or name in ALLOWED_NON_KEYS or name in _JINJA_IF_WORDS


def _template_files() -> list[Path]:
    """Every file in template/ plus the root _tasks.jinja it imports."""
    files = list(TEMPLATE_DIR.rglob("*"))
    files.append(TOP / "_tasks.jinja")
    return files


def _template_local_vars(files: list[Path]) -> set[str]:
    """Names bound by {% set %}, {% import ... as %} and {% for %} in templates.

    These are template-local definitions, not copier.yml keys.
    """
    local: set[str] = set()
    for f in files:
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        local |= set(re.findall(r"\{%-?\s*set\s+([A-Za-z_][A-Za-z0-9_]*)", text))
        local |= set(re.findall(r"\{%-?\s*import\s+[\"'][^\"']+[\"']\s+as\s+([A-Za-z_][A-Za-z0-9_]*)", text))
        # A loop may bind several names: {% for a, b in ... %}.
        local |= set(
            re.findall(r"\{%-?\s*for\s+([A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)\s+in\b", text)
        )
    return local


def test_can_parse_copier_yml_and_gates_are_well_formed():
    questions, order = _load_questions()
    # Every gate exists, is a bool defaulting to true, and has help text.
    for gate in CANONICAL_GATES:
        assert gate in questions, f"{gate} missing from copier.yml"
        assert questions[gate].get("type") == "bool", f"{gate} should be a bool"
        assert questions[gate].get("default") is True, f"{gate} should default to true"
        assert questions[gate].get("help"), f"{gate} should explain its recommendation"
    # The gates appear in the canonical order (project-type questions come
    # first, so filter to just the gates when comparing order).
    gate_order = [k for k in order if k in CANONICAL_GATES]
    assert gate_order == CANONICAL_GATES, f"gate order drifted: {gate_order}"


def test_questionnaire_gate_table_matches_copier_yml():
    """The gate table in the questionnaire reference stays in sync."""
    doc = QUESTIONNAIRE_DOC.read_text(encoding="utf-8")
    # Table rows look like "| `use_recommended_*` | ... |".
    doc_gates = re.findall(r"\| `(use_recommended_[a-z_]+)` \|", doc)
    assert doc_gates == CANONICAL_GATES, f"questionnaire.md gate table drifted: {doc_gates}"


def test_when_and_default_reference_defined_variables():
    questions, _ = _load_questions()
    keys = set(questions)
    for key, q in questions.items():
        for field in ("when", "default", "validator"):
            value = q.get(field)
            if isinstance(value, str):
                for ident in _jinja_identifiers(value):
                    assert _is_known(ident, keys), f"question {key!r} {field} references undefined {ident!r}"
        choices = q.get("choices")
        if isinstance(choices, str):
            for ident in _jinja_identifiers(choices):
                assert _is_known(ident, keys), f"question {key!r} choices references undefined {ident!r}"


def test_template_conditionals_reference_defined_variables():
    """Every {% if %}/{{ }} variable in template/ paths and bodies is defined.

    Template filenames carry copier's conditional syntax
    ({% if var %}segment{% endif %}), so the tree is walked including the
    bracketed directory names. This is what catches a removed question that
    template files still gate on.
    """
    questions, _ = _load_questions()
    keys = set(questions) | ALLOWED_NON_KEYS
    files = _template_files()
    known = keys | _template_local_vars(files)
    references: dict[str, list[str]] = {}
    for f in files:
        if f.is_dir():
            continue
        # Path conditionals: the {%%} segments in relative path parts. Copier
        # interprets these for every file, .jinja or not.
        rel = f.relative_to(TOP)
        refs = _jinja_identifiers(str(rel)) | _jinja_identifiers(f.name)
        # Body conditionals / expressions: only `.jinja` files are rendered by
        # copier. A non-.jinja file (e.g. sphinx's custom-module-template.rst,
        # processed later by sphinx-autoapi) keeps its Jinja verbatim, so its
        # variables are not copier.yml keys by design.
        if f.name.endswith(".jinja"):
            with suppress(UnicodeDecodeError, OSError):
                refs |= _jinja_identifiers(f.read_text(encoding="utf-8"))
        for ident in sorted(refs):
            references.setdefault(ident, []).append(str(rel))
    for ident, where in sorted(references.items()):
        if not _is_known(ident, known):
            assert False, f"template references undefined variable {ident!r} in {where[:3]}"


def test_no_dead_internal_variables():
    """Hidden (`when: false`) variables must be referenced somewhere."""
    questions, _ = _load_questions()
    internal = {k for k, q in questions.items() if isinstance(q.get("when"), bool) and q["when"] is False}
    assert internal, "no internal variables found — is the when: false convention still used?"
    # Collect every identifier referenced anywhere in copier.yml, in template/
    # file *names* (the {% if %} path conditionals) and in file bodies.
    referenced: set[str] = set()
    referenced |= _jinja_identifiers(COPIER_YML.read_text(encoding="utf-8"))
    for f in TEMPLATE_DIR.rglob("*"):
        if f.is_file():
            rel = f.relative_to(TOP)
            referenced |= _jinja_identifiers(str(rel)) | _jinja_identifiers(f.name)
            with suppress(UnicodeDecodeError, OSError):
                referenced |= _jinja_identifiers(f.read_text(encoding="utf-8"))
    for var in sorted(internal):
        assert var in referenced, (
            f"internal variable {var!r} is never referenced — remove it or its last consumer regressed"
        )
