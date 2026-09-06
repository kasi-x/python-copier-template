"""Static checks for the secret-scanning setup.

pre-commit used to run gitleaks locally; scanning now happens in CI via the
hygiene workflow (`gitleaks/gitleaks-action`), which reads `.gitleaks.toml`.
These tests guard the wiring that the old behavioral tests exercised:
the config exists in both the repo and the template output, the gitleaks
action is present and SHA-pinned, and the SealedSecrets allowlist + the
de-identification salt rule survive config refactors (the behavioral
versions of those checks are in CI now).
"""

from pathlib import Path

import pytest
import yaml

TOP = Path(__file__).resolve().parent.parent
GITLEAKS_TOML = TOP / ".gitleaks.toml"
HYGIENE = TOP / ".github" / "workflows" / "_hygiene.yml"


def test_gitleaks_config_exists_in_template_output():
    """Every generated project keeps the root `.gitleaks.toml` (symlinked
    into the template) that the hygiene workflow's gitleaks step reads."""
    template_link = TOP / "template" / ".gitleaks.toml"
    assert template_link.is_symlink(), (
        "template/.gitleaks.toml must stay a symlink to the root config so "
        "generated projects ship the same secret-scanning rules"
    )
    assert template_link.resolve() == GITLEAKS_TOML.resolve()


def test_hygiene_workflow_runs_gitleaks_sha_pinned():
    workflow = HYGIENE.read_text()
    assert "gitleaks/gitleaks-action@" in workflow
    # Pin the exact digest-style SHA the repo's workflow-security policy
    # requires (40 hex chars, version comment follows).
    import re

    match = re.search(r"gitleaks/gitleaks-action@([0-9a-f]{40})", workflow)
    assert match, "gitleaks action must be pinned to a 40-char SHA"
    assert "# v" in workflow.split("gitleaks/gitleaks-action@")[1][:80]


def test_sealed_secrets_allowlist_stays_yaml_scoped():
    """The generic-api-key allowlist for long Ag… tokens must stay limited to
    YAML files — broadening it to all files would silence real leaks (the
    scenario the old behavioral gitleaks tests covered)."""
    config = GITLEAKS_TOML.read_text()
    assert "[[rules.allowlists]]" in config
    assert "Ag[A-Za-z0-9+/]{500,}" in config
    paths_line = next(line for line in config.splitlines() if line.startswith("paths = "))
    assert "ya?ml" in paths_line, f"allowlist must stay YAML-scoped: {paths_line}"


@pytest.mark.parametrize(
    "rule_id,fragment",
    [
        ("deidentification-salt", "deidentification_salt"),
        ("deidentification-salt", "pseudonym_salt"),
        ("deidentification-salt", "secret_salt"),
    ],
)
def test_deidentification_salt_rule_survives(rule_id: str, fragment: str):
    """The privacy rule guarding data/DEIDENTIFICATION.md must keep matching
    every salt naming variant."""
    config = GITLEAKS_TOML.read_text()
    assert f'id = "{rule_id}"' in config
    assert fragment in config


def test_hygiene_workflow_steps_are_gated():
    """The optional hygiene steps self-gate via hashFiles so a generated
    project only runs what it ships."""
    workflow = yaml.safe_load(HYGIENE.read_text())
    steps = workflow["jobs"]["hygiene"]["steps"]
    by_name = {step.get("name"): step for step in steps if "name" in step}
    reuse = by_name["REUSE compliance"]
    cff = by_name["Validate CITATION.cff"]
    notebooks = by_name["Jupyter notebooks are stripped of outputs"]
    assert reuse["if"] == "hashFiles('REUSE.toml') != ''"
    assert cff["if"] == "hashFiles('CITATION.cff') != ''"
    assert notebooks["if"] == "hashFiles('**/*.ipynb') != ''"
