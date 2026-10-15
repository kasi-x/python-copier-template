"""Parity: old REGISTRY gates vs guidance `applies()` over the derived `when` set.

The template stopped vendoring rule prose into AGENTS.md: it now emits
`.daimonion.yml` (abstract `when` conditions) and an empty marker block the
`daimonion` linter fills in. This test proves the cutover changed nothing
about *which* leaf gets *which* section: for every leaf in
tests/matrix/witnesses.jsonl (272), the set of section ids selected by the
old registry gates must equal the set selected by law-map guidance's
`applies()` over the derived `when` set.

Two deliberate self-containments (the sibling slice deletes architekton/ethics.py
and _shared/ethics/REGISTRY.yml, so neither may be imported here):

- the old side's active gates are a FROZEN constant copied from
  _shared/ethics/REGISTRY.yml `status==active` rows (verified 0 mismatches
  over all 272 leaves at derivation time), evaluated by a ~40-line
  restricted evaluator over a `leaf_context` mirror;
- the guidance side is read from law-map's `guidance/sections/MANIFEST.yml`
  (schema 2) plus each section file's YAML front matter at
  $DAIMONION_GUIDANCE_DIR (default: the sibling law-map checkout),
  replicating `Section.applies`: `status == 'active' and
  placement == 'agents_md' and bool({'always', *conditions} & set(when))`,
  where `when` may be a string or a list (any-of). Skipped when the
  checkout is absent.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest
import yaml

TOP = Path(__file__).absolute().parent.parent
WITNESSES = TOP / "tests" / "matrix" / "witnesses.jsonl"
# law-map guidance checkout (schema-2 MANIFEST + YAML front-matter sections).
# Kept under the old DAIMONION_KANON_DIR name as a fallback so existing CI
# env still resolves; prefer DAIMONION_GUIDANCE_DIR going forward.
GUIDANCE_DIR = Path(
    os.environ.get(
        "DAIMONION_GUIDANCE_DIR",
        os.environ.get(
            "DAIMONION_KANON_DIR",
            "/home/user/dev/ConstitutiveTemplates/law-map/guidance/sections",
        ),
    )
)

# Frozen copy of _shared/ethics/REGISTRY.yml `status==active` rows' gates
# (id -> gate string). Verified identical to guidance applies() over the
# derived `when` set for all 272 leaves before the registry was deleted.
FROZEN_GATES: dict[str, str] = {
    "baseline-license-drift": "true",
    "baseline-pki-chain": "project_type in ['micropython', 'cli'] or web_api",
    "baseline-personal-data": "'personal-data' in domain_traits or 'face-recognition' in domain_traits or 'medtech' in domain_traits",
    "baseline-pqc-fips": "project_type in ['library', 'cli'] or web_api",
    "baseline-copyright-ai": "project_type == 'cli' or data_science_layout",
    "domain-llm-appsec": "mcp_effective",
    "domain-ml-bias": "ds_stack",
    "domain-face-recognition": "'face-recognition' in domain_traits",
    "sector-samd-regulatory": "'medtech' in domain_traits",
    "region-eu-cra": "'commercial' in distribution",
    "domain-scraping-law": "scraping_effective",
    "domain-contest-rules": "oj_code",
}

# Deterministic emission order (guidance vocabulary order; `always` never emitted).
WHEN_ORDER: tuple[str, ...] = (
    "library",
    "cli",
    "embedded",
    "personal_data",
    "face_recognition",
    "medtech",
    "scraping",
    "oj_code",
    "mcp",
    "data_science",
    "kaggle",
    "web_api",
    "commercial",
)

OJ_CODE_KINDS = frozenset({"atcoder", "leetcode", "yukicoder", "aoj", "codeforces", "kattis", "other"})

_GATE_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.IfExp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.And,
    ast.Or,
    ast.Not,
    ast.In,
    ast.NotIn,
    ast.Eq,
    ast.NotEq,
)


def _choices(answers: dict, key: str) -> list[str]:
    value = answers.get(key)
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return []


def _combinable(answers: dict) -> bool:
    project_type = str(answers.get("project_type") or "")
    is_kaggle = project_type == "online_judge" and answers.get("oj_kind") == "kaggle"
    return project_type in ("library", "cli", "web_api", "data_science") or is_kaggle


def leaf_context(answers: dict) -> dict:
    """Mirror of architekton/ethics.py `leaf_context` (questions/_internal.yml derived defaults)."""
    project_type = str(answers.get("project_type") or "")
    combinable = _combinable(answers)
    web_api = project_type == "web_api" or (bool(answers.get("include_web_api")) and combinable)
    data_science = project_type == "data_science" or (bool(answers.get("include_data_science")) and combinable)
    kaggle = project_type == "online_judge" and answers.get("oj_kind") == "kaggle"
    return {
        "true": True,
        "false": False,
        "project_type": project_type,
        "oj_kind": str(answers.get("oj_kind") or ""),
        "domain_traits": _choices(answers, "domain_traits"),
        "distribution": _choices(answers, "distribution"),
        "web_api": web_api,
        "data_science_layout": data_science,
        "ds_stack": data_science or kaggle,
        "mcp_effective": bool(answers.get("include_mcp")) and (project_type == "cli" or web_api),
        "scraping_effective": bool(answers.get("include_scraping")) and project_type == "cli",
        "oj_code": project_type == "online_judge" and answers.get("oj_kind") in OJ_CODE_KINDS,
    }


def gate_holds(gate: str, answers: dict) -> bool:
    gate = (gate or "").strip()
    if not gate or gate == "true":
        return True
    tree = ast.parse(gate, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _GATE_NODES):
            detail = f"unsafe gate {gate!r}: {type(node).__name__} not allowed"
            raise TypeError(detail)
    return bool(eval(gate, {"__builtins__": {}}, leaf_context(answers)))  # noqa: S307


def derive_when(answers: dict) -> list[str]:
    """The derived `when` set, in deterministic vocabulary order."""
    ctx = leaf_context(answers)
    project_type = str(answers.get("project_type") or "")
    flags: dict[str, bool] = {
        "library": project_type == "library",
        "cli": project_type == "cli",
        "embedded": project_type == "micropython",
        "personal_data": "personal-data" in ctx["domain_traits"],
        "face_recognition": "face-recognition" in ctx["domain_traits"],
        "medtech": "medtech" in ctx["domain_traits"],
        "scraping": bool(ctx["scraping_effective"]),
        "oj_code": bool(ctx["oj_code"]),
        "mcp": bool(ctx["mcp_effective"]),
        "data_science": bool(ctx["data_science_layout"]),
        "kaggle": project_type == "online_judge" and str(answers.get("oj_kind") or "") == "kaggle",
        "web_api": bool(ctx["web_api"]),
        "commercial": "commercial" in ctx["distribution"],
    }
    return [name for name in WHEN_ORDER if flags[name]]


def _front_matter(text: str) -> dict:
    """Split a guidance section file into its YAML front matter (between --- lines)."""
    if not text.startswith("---\n"):
        return {}
    head, _, _ = text[len("---\n") :].partition("\n---\n")
    return yaml.safe_load(head) or {}


def load_kanon() -> list[dict]:
    """Guidance sections: id, when-tuple, placement, status.

    Kept under the old name so test_daimonion_config keeps importing it.
    Reads law-map's schema-2 MANIFEST.yml for the row order plus each
    section file's YAML front matter for the authoritative status.
    """
    sections_dir = GUIDANCE_DIR if (GUIDANCE_DIR / "MANIFEST.yml").is_file() else GUIDANCE_DIR / "sections"
    if not (sections_dir / "MANIFEST.yml").is_file():
        pytest.skip(f"law-map guidance checkout not found at {GUIDANCE_DIR}")
    manifest = yaml.safe_load((sections_dir / "MANIFEST.yml").read_text(encoding="utf-8"))
    out = []
    for row in manifest["sections"]:
        when = row.get("when", "always")
        when_t = (when,) if isinstance(when, str) else tuple(when)
        front = _front_matter((sections_dir / str(row["file"])).read_text(encoding="utf-8"))
        out.append(
            {
                "id": str(row["id"]),
                "when": when_t,
                "placement": str(front.get("placement", row.get("placement", "agents_md"))),
                "status": str(front.get("status", row.get("status", "draft"))),
            }
        )
    return out


def kanon_applies(section: dict, conditions: list[str]) -> bool:
    wanted = {"always", *conditions}
    return section["status"] == "active" and section["placement"] == "agents_md" and bool(wanted & set(section["when"]))


def _leaves() -> list[dict]:
    return [json.loads(line) for line in WITNESSES.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_parity_old_gates_vs_kanon_applies():
    sections = load_kanon()
    mismatches = []
    for leaf in _leaves():
        answers = dict(leaf["answers"])
        old = sorted(sid for sid, gate in FROZEN_GATES.items() if gate_holds(gate, answers))
        new = sorted(s["id"] for s in sections if kanon_applies(s, derive_when(answers)))
        if old != new:
            mismatches.append(f"{leaf['id']}: old={old} new={new}")
    assert mismatches == [], "parity drift on:\n  " + "\n  ".join(mismatches)


def test_parity_covers_all_272_leaves():
    assert len(_leaves()) == 272, f"expected 272 leaves, got {len(_leaves())}"


def test_derive_when_vocabulary_order():
    answers = {
        "project_type": "cli",
        "include_web_api": False,
        "include_scraping": True,
        "distribution": ["commercial"],
    }
    when = derive_when(answers)
    assert when == sorted(when, key=WHEN_ORDER.index), f"not in vocabulary order: {when}"
    assert "always" not in when
