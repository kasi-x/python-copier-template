#!/usr/bin/env python3
"""Enumerate the questionnaire's leaf space as §C6 batch requests (W3).

The questionnaire's full cartesian product is far too large to render (every
`use_recommended_*` gate times every detail question times every project
type), so W3 draws its witnesses from a *declared* subspace, enumerated with
Z3 and rendered one JSONL line per leaf by tools/batch.py:

    leaf = project_type
         x (every `use_recommended_*` gate at its default true, or exactly one off)
         x (no include layer, or exactly one include layer on)
         x (oj_category/oj_kind, when project_type is online_judge)

The three restrictions are the declared leaf space (the W4 audit surface) and
are encoded as Z3 constraints:

- ``z3.AtMost(*[z3.Not(gate) for gate in gates], 1)``: accept every
  recommendation, or open exactly one area's detail questions.
- ``z3.AtMost(*includes, 1)``: at most one opt-in layer on top of the base
  layout (the questionnaire's own `combinable` guard applies on top).
- a gate may only be turned off where its own `when` holds, and an include
  layer only turned on where its `when` holds. Otherwise the answer belongs
  to a question copier never asks and the leaf is not a real branch of the
  questionnaire. Those `when` conditions are *projected* onto the leaf space
  below (the derived `has_data_science` / `has_web_api` / `kaggle` /
  `combinable` internals from questions/_internal.yml are inlined there).
  copier.yml stays the source of truth: every question is loaded with
  copier's own loader, a gate/include with no projection is an error, and
  each projected branch a leaf takes is cross-checked against the existing
  encoder (tests/test_copier_structure.py:491 `_when_expr_satisfiable`,
  imported -- never modified; see that file's lines 427-489 for the parser).

Everything else stays at its copier default (tools/batch.py renders with
`defaults=True`): the detail questions an off gate reveals keep their
defaults, so a leaf is one branch of the questionnaire, not a second full
question matrix. `project_type` is its static choices minus web_django,
which aborts generation by design (`_tasks.jinja` exits 1 for it) and so
cannot render. include_mcp/include_sentry are integration detail questions
behind use_recommended_integrations, not layers, and stay at their default
false.

Usage:

    python tools/z3_witnesses.py --json           # leaf space + leaves
    python tools/z3_witnesses.py --jsonl PATH     # the same, as §C6 lines
    python tools/batch.py tests/matrix/witnesses.jsonl --json

Each leaf carries the answers (tests/test_recommended_path.py:25-34 `BASE`,
so the required Project Details stay fixed) and the render invariants of its
declared layout: the artifact set that shape must produce, and no unrendered
`*.jinja` left behind.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any
from typing import cast

import yaml
import z3
from jinja2 import Template

TOP = Path(__file__).resolve().parent.parent
STRUCTURE_TESTS = TOP / "tests" / "test_copier_structure.py"

# The Project Details every leaf pins, so fixtures stay self-consistent
# (validators, URLs): mirrors tests/test_recommended_path.py:25-34.
BASE: dict[str, Any] = {
    "package_name": "smoke_example",
    "description": "An example project",
    "git_platform": "github.com",
    "github_org": "kasi-x",
    "author_name": "kasi-x",
    "author_email": "kashimiya.exe@gmail.com",
    "repo_name": "smoke-example",
    "distribution_name": "smoke-example",
}

# The opt-in layers (questions/_combo.yml:10-48) that make up the include
# dimension of the leaf space. include_mcp / include_sentry are detail
# questions behind use_recommended_integrations, not layers.
INCLUDE_LAYERS: tuple[str, ...] = (
    "include_data_science",
    "include_web_api",
    "include_ctf",
    "include_scraping",
)

GATE_PREFIX = "use_recommended_"

# gates whose `when` the projection below keeps at "always asked".
UNCONDITIONAL_GATES: tuple[str, ...] = (
    "use_recommended_toolchain",
    "use_recommended_polish",
    "use_recommended_docs",
    "use_recommended_quality",
    "use_recommended_license",
    "use_recommended_integrations",
    "use_recommended_security",
)

# gates whose `when` the projection below mirrors explicitly.
PROJECTED_GATES: tuple[str, ...] = (
    "use_recommended_agent",
    "use_recommended_data_science",
    "use_recommended_web_api",
    "use_recommended_scraping",
)

# Question types the questionnaire deliberately cannot render.
EXCLUDED_PROJECT_TYPES: dict[str, str] = {
    "web_django": "generation aborts by design: the _tasks.jinja web_django task exits 1",
}

# Render invariants: artifacts every leaf must produce (the same set the
# recommended path ships, tests/test_recommended_path.py:52-100 MARKERS).
COMMON_FILES: tuple[str, ...] = (
    "README.md",
    "LICENSE",
    ".gitignore",
    ".editorconfig",
    "pyproject.toml",
    "Dockerfile",
    "justfile",
    ".github/workflows/ci.yml",
    "CHANGELOG.md",
)
COMMON_ABSENT: tuple[str, ...] = ("**/*.jinja",)

PROJECT_TYPE_FILES: dict[str, tuple[str, ...]] = {
    "library": ("src/smoke_example/__init__.py",),
    "cli": ("src/smoke_example/__init__.py",),
    "script": ("smoke_example/__init__.py",),
    "online_judge": (),  # supplied by the oj_kind table below
    "ros2": ("package.xml", "smoke_example/__init__.py"),
    "micropython": ("firmware/main.py",),
}

# Competitive-programming judges ship a bare workspace: no package, no
# challenges, no agent guide (tests/test_recommended_path.py MARKERS "oj_atcoder").
OJ_CODE_KINDS: tuple[str, ...] = ("atcoder", "leetcode", "yukicoder", "aoj")
OJ_KIND_FILES: dict[str, tuple[str, ...]] = {
    "kaggle": ("src/utils/__init__.py",),
    "ctf": ("challenges/pwn/example/solve.py", "AGENTS.md"),
    **dict.fromkeys(OJ_CODE_KINDS, ()),
}
OJ_KIND_ABSENT: dict[str, tuple[str, ...]] = {
    "kaggle": ("src/smoke_example", "challenges"),
    "ctf": (),
    **dict.fromkeys(OJ_CODE_KINDS, ("src", "challenges", "AGENTS.md")),
}

# Artifacts the other layers add. include_data_science and include_web_api
# switch on the data_science / web_api layouts and are handled by name in
# _expect (they replace the project type's own package directory).
INCLUDE_FILES: dict[str, tuple[str, ...]] = {
    "include_ctf": ("challenges/pwn/example/solve.py",),
    "include_scraping": ("src/smoke_example/fetcher.py", "tests/test_scraping.py", "CHARTER.md"),
}

# Artifacts a gate being off adds on top of its defaults: the `prompts/`
# directory is rendered only when the agent gate is off for library/cli
# (template/<...>prompts condition).
GATE_FILES: dict[str, tuple[str, ...]] = {
    "use_recommended_agent": ("prompts",),
}


@dataclass(frozen=True)
class Leaf:
    """One declared leaf: its id, the copier answers, and the invariants."""

    id: str
    note: str
    answers: dict[str, Any]
    expect: dict[str, Any]

    def as_request(self) -> dict[str, Any]:
        """The §C6 batch request line for this leaf."""
        return {
            "id": self.id,
            "note": self.note,
            "ref": "HEAD",
            "dest": self.id.replace("/", "_").replace(":", "-"),
            "answers": self.answers,
            "expect": self.expect,
        }


@dataclass(frozen=True)
class Space:
    """The Z3 handles of the declared leaf space."""

    solver: z3.Solver
    pt: z3.ArithRef
    oj_category: z3.ArithRef
    oj_kind: z3.ArithRef
    gates: dict[str, z3.BoolRef]
    includes: dict[str, z3.BoolRef]
    pt_domain: list[str]
    oj_categories: list[str]
    oj_kinds: dict[str, list[str]]

    @property
    def variables(self) -> list[Any]:
        """Every Z3 variable of the leaf space (the blocking-clause scope)."""
        return [self.pt, self.oj_category, self.oj_kind, *self.gates.values(), *self.includes.values()]


def _structure_module() -> ModuleType:
    """Load tests/test_copier_structure.py -- the project's Z3 encoder lives there."""
    spec = importlib.util.spec_from_file_location("_witness_structure", STRUCTURE_TESTS)
    if spec is None or spec.loader is None:
        msg = f"cannot import {STRUCTURE_TESTS}"
        raise SystemExit(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses/pickling resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


def _static_choices(structure: ModuleType, questions: dict[str, dict], name: str) -> list[str]:
    """A question's choice values, mapping form normalized (tests/...:473-489, §C2)."""
    choices = questions[name].get("choices")
    values = (
        [str(value) for value in choices.values()]
        if isinstance(choices, dict)
        else [str(value) for value in structure._static_str_choices(questions[name])]  # noqa: SLF001
    )
    if not values:
        msg = f"question {name!r} has no static choices; the leaf space needs a fixed domain"
        raise SystemExit(msg)
    return values


def _oj_kinds(questions: dict[str, dict], category: str) -> list[str]:
    """oj_kind's choices for one oj_category (its `choices` is a Jinja template)."""
    rendered = Template(str(questions["oj_kind"]["choices"])).render(oj_category=category)
    return [str(value) for value in yaml.safe_load(rendered)]


def _build_space(questions: dict[str, dict], pt_domain: list[str], oj_categories: list[str]) -> Space:
    """Assert the leaf-space restrictions on top of the questionnaire's variables."""
    gates = {name: z3.Bool(name) for name in questions if name.startswith(GATE_PREFIX)}
    includes = {name: z3.Bool(name) for name in INCLUDE_LAYERS}
    for name in (*UNCONDITIONAL_GATES, *PROJECTED_GATES, *INCLUDE_LAYERS):
        if name not in questions:
            msg = f"{name!r} is declared in this tool but gone from the questionnaire; update the leaf space"
            raise SystemExit(msg)
    unprojected = set(gates) - set(UNCONDITIONAL_GATES) - set(PROJECTED_GATES)
    if unprojected:
        msg = f"gate(s) {sorted(unprojected)} have no projection; declare their `when` in this tool"
        raise SystemExit(msg)
    for name in UNCONDITIONAL_GATES:
        when = questions[name].get("when")
        if when is not None and name != "use_recommended_toolchain":
            msg = f"gate {name!r} is no longer unconditional (when={when!r}); project its `when` here"
            raise SystemExit(msg)

    index = {name: position for position, name in enumerate(pt_domain)}
    pt = z3.Int("project_type")
    oj_category = z3.Int("oj_category")
    oj_kind = z3.Int("oj_kind")
    oj_kinds = {category: _oj_kinds(questions, category) for category in oj_categories}

    # Derived internals, inlined from questions/_internal.yml: combinable,
    # has_web_api, has_data_science and kaggle (the four the leaf space reads).
    kaggle_category = oj_categories.index("data_science")
    kaggle = z3.And(
        pt == index["online_judge"],
        oj_category == kaggle_category,
        oj_kind == oj_kinds["data_science"].index("kaggle"),
    )
    combinable = z3.Or(*(pt == index[name] for name in ("library", "cli", "web_api", "data_science")), kaggle)
    has_web_api = z3.Or(pt == index["web_api"], z3.And(includes["include_web_api"], combinable))
    has_data_science = z3.Or(pt == index["data_science"], z3.And(includes["include_data_science"], combinable))

    # when-conditions projected onto the leaf space (fragment named per line).
    asked: dict[str, z3.BoolRef] = dict.fromkeys(
        [*gates, *includes],
        z3.BoolVal(True),  # noqa: FBT003  WHYNOT: z3's own API takes a Python bool.
    )
    asked["use_recommended_agent"] = _bool(z3.Or(pt == index["library"], pt == index["cli"]))  # questions/_common_a.yml
    asked["use_recommended_data_science"] = _bool(has_data_science)  # questions/data_science.yml
    asked["use_recommended_web_api"] = _bool(has_web_api)  # questions/web_api.yml
    asked["use_recommended_scraping"] = includes["include_scraping"]  # questions/_combo.yml
    asked["include_data_science"] = _bool(  # questions/_combo.yml
        z3.Or(pt == index["library"], pt == index["cli"], pt == index["web_api"])
    )
    asked["include_web_api"] = _bool(  # questions/_combo.yml
        z3.Or(pt == index["library"], pt == index["cli"], pt == index["data_science"], kaggle)
    )
    asked["include_ctf"] = _bool(z3.Or(pt == index["library"], pt == index["cli"]))  # questions/_combo.yml
    asked["include_scraping"] = _bool(pt == index["cli"])  # questions/_combo.yml
    # use_recommended_toolchain's when is only false for ros2 + a pixi package
    # manager, and ros2_package_manager stays at its 'apt' default here, so it
    # is always asked (questions/_common_a.yml:16-25).

    solver = z3.Solver()
    solver.add(pt >= 0, pt < len(pt_domain))
    solver.add(oj_category >= 0, oj_category < len(oj_categories))
    solver.add(z3.AtMost(*[z3.Not(gate) for gate in gates.values()], 1))
    solver.add(z3.AtMost(*includes.values(), 1))
    for name, gate in gates.items():
        solver.add(z3.Implies(z3.Not(gate), asked[name]))
    for name, include in includes.items():
        solver.add(z3.Implies(include, asked[name]))
    for category, kinds in oj_kinds.items():
        position = oj_categories.index(category)
        asked_kind = z3.Or(*(oj_kind == i for i in range(len(kinds))))
        solver.add(z3.Implies(z3.And(pt == index["online_judge"], oj_category == position), asked_kind))
    solver.add(z3.Implies(pt != index["online_judge"], z3.And(oj_category == 0, oj_kind == 0)))
    return Space(solver, pt, oj_category, oj_kind, gates, includes, pt_domain, oj_categories, oj_kinds)


def _bool(expr: object) -> z3.BoolRef:
    """One z3 formula as a BoolRef.

    z3's stubs widen `And`/`Or`/probe results to `BoolRef | Probe` and an `Int`
    comparison to `BoolRef | Literal[False]`; every value here is a formula, so
    the cast is the honest narrowing (the leaf is re-checked against the
    questionnaire's own encoder before it is written out).
    """
    return cast("z3.BoolRef", expr)


def _when_domains(structure: ModuleType, questions: dict[str, dict], pt_domain: list[str]) -> dict[str, list[str]]:
    """Str domains for the imported encoder, built like its own test (lines 652-670)."""
    referenced: set[str] = set()
    for question in questions.values():
        when = question.get("when")
        if isinstance(when, str):
            referenced |= structure._jinja_identifiers(when)  # noqa: SLF001
    domains: dict[str, list[str]] = {"project_type": pt_domain}
    for name in sorted(referenced):
        question = questions.get(name)
        if question is None or question.get("type") == "bool":
            continue
        values = structure._static_str_choices(question)  # noqa: SLF001
        if values:
            domains[name] = values
    return domains


def _models(space: Space) -> list[dict[Any, Any]]:
    """Enumerate every satisfying model, blocking each one as it is found."""
    found: list[dict[Any, Any]] = []
    while space.solver.check() == z3.sat:
        model = space.solver.model()
        values = {var: model.eval(var, model_completion=True) for var in space.variables}
        found.append(values)
        space.solver.add(z3.Or(*[var != value for var, value in values.items()]))
    return found


def _unique(items: list[str]) -> list[str]:
    """De-duplicate while keeping the declared order."""
    return list(dict.fromkeys(items))


def _expect(project_type: str, oj_kind: str, include: str | None, gate_off: str | None) -> dict[str, Any]:
    """The render invariants of one leaf's declared layout (derived from its answers).

    The web_api and data_science layers move where the package lives
    (questions/_internal.yml `pkg_dir`), so the project type's own package
    directory only applies when no such layer is on.
    """
    web_api = project_type == "web_api" or include == "include_web_api"
    data_science = project_type == "data_science" or include == "include_data_science"
    files = list(COMMON_FILES)
    absent = list(COMMON_ABSENT)
    if data_science:
        files.append("notebooks/.gitkeep")  # the data-science layout
    if web_api:
        files.append("app/main.py")  # pkg_dir == 'app' (questions/_internal.yml)
    else:
        # data_science/web_api have no package dir of their own: their layer
        # (handled above) is their layout.
        files.extend(PROJECT_TYPE_FILES.get(project_type, ()))
    # The `src/` tree comes from the src layout, the web_api app, the kaggle
    # workspace or the data-science layout -- absent otherwise.
    src_layout = project_type in ("library", "cli") and not web_api
    if not (data_science or oj_kind == "kaggle" or src_layout):
        absent.append("src")
    if project_type == "online_judge":
        files.extend(OJ_KIND_FILES.get(oj_kind, ()))
        absent.extend(OJ_KIND_ABSENT.get(oj_kind, ()))
    if include is not None:
        files.extend(INCLUDE_FILES.get(include, ()))
    if gate_off is not None:
        files.extend(GATE_FILES.get(gate_off, ()))
    return {"files": _unique(files), "absent": _unique(absent)}


def _leaf(
    structure: ModuleType,
    questions: dict[str, dict],
    space: Space,
    values: dict[Any, Any],
    domains: dict[str, list[str]],
) -> Leaf:
    """Map one Z3 model to its §C6 request (id, answers, expected invariants)."""
    project_type = space.pt_domain[values[space.pt].as_long()]
    off = [name for name, gate in space.gates.items() if not z3.is_true(values[gate])]
    on = [name for name, include in space.includes.items() if z3.is_true(values[include])]
    # The projected branch must also be satisfiable for the project's own
    # encoder -- the questionnaire, not this tool, has the last word.
    for name in [*off, *on]:
        when = questions[name].get("when")
        if isinstance(when, str) and not structure._when_expr_satisfiable(when, domains, z3):  # noqa: SLF001
            msg = f"branch {name!r} projected as reachable but its when {when!r} is unsatisfiable"
            raise SystemExit(msg)

    parts = [f"project_type={project_type}", f"gate=off:{off[0]}" if off else "gate=recommended"]
    answers: dict[str, Any] = {**BASE, "project_type": project_type}
    oj_kind = ""
    if project_type == "online_judge":
        category = space.oj_categories[values[space.oj_category].as_long()]
        oj_kind = space.oj_kinds[category][values[space.oj_kind].as_long()]
        answers["oj_category"] = category
        answers["oj_kind"] = oj_kind
        parts.append(f"oj={category}/{oj_kind}")
    if on:
        parts.append(f"include={on[0]}")
        answers[on[0]] = True
    if off:
        answers[off[0]] = False

    note = ["all use_recommended_* gates at their default"]
    if off:
        note.append(f"one gate off: {off[0]} (its detail questions stay at their defaults)")
    if on:
        note.append(f"one include layer on: {on[0]}")
    return Leaf(
        id="/".join(parts),
        note=f"W3 Z3 witness: {'; '.join(note)}",
        answers=answers,
        expect=_expect(project_type, oj_kind, on[0] if on else None, off[0] if off else None),
    )


def build() -> tuple[dict[str, Any], list[Leaf]]:
    """Return the declared leaf space and its enumerated leaves."""
    structure = _structure_module()
    questions, _order = structure._load_questions()  # noqa: SLF001
    pt_domain = [
        value for value in _static_choices(structure, questions, "project_type") if value not in EXCLUDED_PROJECT_TYPES
    ]
    oj_categories = _static_choices(structure, questions, "oj_category")
    space = _build_space(questions, pt_domain, oj_categories)
    domains = _when_domains(structure, questions, pt_domain)
    leaves = [_leaf(structure, questions, space, values, domains) for values in _models(space)]
    leaves.sort(key=lambda leaf: leaf.id)
    ids = [leaf.id for leaf in leaves]
    if len(ids) != len(set(ids)):
        msg = f"leaf ids are not unique: {sorted(name for name in ids if ids.count(name) > 1)}"
        raise SystemExit(msg)

    leaf_space = {
        "project_type": pt_domain,
        "gates": list(space.gates),
        "includes": list(INCLUDE_LAYERS),
        "oj_category": oj_categories,
        "oj_kind": space.oj_kinds,
        "restrictions": [
            "every use_recommended_* gate at its default (true), or exactly one off",
            "no include layer, or exactly one include layer on",
            "a gate may only be off, and an include only on, where its own `when` holds",
            "every other question stays at its copier default",
        ],
        "excluded": EXCLUDED_PROJECT_TYPES,
    }
    return leaf_space, leaves


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enumerate the questionnaire's Z3 witness leaves (W3).")
    parser.add_argument("--json", action="store_true", help="print the leaf space and every leaf")
    parser.add_argument("--jsonl", type=Path, default=None, help="write the leaves as §C6 batch requests")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: enumerate, then print and/or write the §C6 request lines."""
    args = _parse_args(argv)
    leaf_space, leaves = build()
    if args.jsonl is not None:
        args.jsonl.parent.mkdir(parents=True, exist_ok=True)
        lines = "".join(json.dumps(leaf.as_request(), sort_keys=False) + "\n" for leaf in leaves)
        args.jsonl.write_text(lines, encoding="utf-8")
    if args.json or args.jsonl is None:
        payload = {"leaf_space": leaf_space, "leaves": [leaf.as_request() for leaf in leaves]}
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
