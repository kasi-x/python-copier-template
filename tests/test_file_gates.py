"""questions/99-files.yml: the table of which generated files exist for which answers.

copier evaluates the table itself (copier.yml's `_exclude`); these tests keep
the table and template/ telling the same story, and keep `file_gates.py`'s
reading of it identical to the YAML copier parses.
"""

import re
import subprocess
import sys
from pathlib import Path

import yaml

TOP = Path(__file__).absolute().parent.parent
if str(TOP) not in sys.path:  # tests/test_cli.py does the same to reach architekton/
    sys.path.insert(0, str(TOP))

from architekton import file_gates  # noqa: E402
from architekton import questionnaire  # noqa: E402


def test_every_row_names_a_path_the_template_produces():
    """A row left behind by a removed or renamed file is an error, not a no-op."""
    stale = file_gates.stale_rows()
    assert not stale, "rows with no template/ source: " + ", ".join(f"line {g.line}: {g.path}" for g in stale)


def test_the_parser_reads_every_row_copier_reads():
    """file_gates.load sees exactly the rows of the YAML block copier renders.

    The block is made plain YAML the way a render would: block tags drop out,
    `{{ pkg_dir }}` becomes a path, every condition a boolean.
    """
    table = str(questionnaire.questions_by_name()["file_gates"].default)
    plain = re.sub(r"(?m)^\s*\{%.*%\}\s*$", "", table).replace("{{ pkg_dir }}", "PKG")
    rows = yaml.safe_load(re.sub(r"\{\{.*?\}\}", "true", plain))
    assert {key.replace("PKG", "{{ pkg_dir }}") for key in rows} == {gate.path for gate in file_gates.load()}


def test_template_names_carry_conditions_only_where_the_name_is_computed():
    """Plain names keep template/ readable: a `{% if %}` stays in a name only around a computed
    name (`{{ pkg_dir }}`, the lock-file switch) or in the src/ sub-trees several project types share.
    """
    offenders = []
    for path in (TOP / "template").rglob("*"):
        relative = path.relative_to(TOP / "template")
        for segment in relative.parts:
            if "{%" not in segment or "{{" in segment or "{% elif" in segment:
                continue
            if relative.parts[0].endswith("src{% endif %}"):
                continue
            offenders.append(relative.as_posix())
    assert not offenders, "move these conditions into questions/99-files.yml: " + ", ".join(sorted(set(offenders)))


def test_a_path_inherits_its_directory_rows():
    """A file under a gated directory is gated by the directory's row too."""
    gates = file_gates.load()
    conditions = file_gates.conditions_for(".github/workflows/_docs.yml", gates)
    assert conditions == ["is_github", "ci_github_actions", "docs"]


def test_rows_inside_a_block_carry_the_block_condition():
    """`{% if pkg_scaffold %}` around the package rows is part of each row's condition."""
    gate = next(g for g in file_gates.load() if g.path == "{{ pkg_dir }}/agent.py")
    assert gate.full_condition == "(pkg_scaffold) and (agent_scaffold)"


def test_no_template_file_is_gitignored():
    """copier drops gitignored files when it renders a dirty checkout (it re-adds the
    working tree into a fresh index), so a template file matching .gitignore
    silently vanishes from every local render with uncommitted changes.
    """
    tracked = subprocess.run(["git", "ls-files", "template"], cwd=TOP, capture_output=True, text=True, check=True)
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=TOP,
        input=tracked.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert not ignored.stdout, f"template files matched by .gitignore (add a `!` exception):\n{ignored.stdout}"
