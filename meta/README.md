# meta/ — the catalog the template is generated from

`catalog.yml` is the root: the facts the template needs, written once, each
next to its update policy. `architekton/gen_macros.py` renders
`partials/macros.jinja` from it (`task regen` runs this), and every template
that needs a version or a dependency list consumes the generated file — so a
bump is one line in TOML, never a Jinja hunt.

## Update policy

Each value carries `update`:

| Value | Meaning |
| --- | --- |
| `"bot"` | fair game for an automated bump (dep floors, Python floor — guarded by `check_upstream.py` against upstream EOL) |
| `"pinned"` | must not move without a human — e.g. ROS distro Python versions, ABI-locked by REP-2000 |

A bot proposing a bump touches `update = "bot"` rows only. Anything pinned
appears in the diff by definition, so a rogue update cannot hide.

## The questionnaire tree (`meta/questionnaire/`)

Questions are generated too:

    tree.yml              — which questions/*.yml are generated ([areas]),
                             and the variant → area plug table ([plugs_in]):
                             "choosing this template adds these questions,
                             filed in this area"
    areas/<NN>-*.yml       — area source; plain YAML plus two markers:
                               !fragment shared/log_library   splice a
                                 fragment verbatim (shared questions live
                                 once — log_library is the first)
                               !catalog ros_distro            emit a
                                 question from catalog rows
    fragments/<path>.yml   — a reusable question block (the partial question)
gen_questions.py expands the markers line-wise and writes questions/.

Adding a template variant: one catalog row (e.g. [python.ros.<name>] with
label/eol/version/default) + one [plugs_in] row if it adds questions. The
distro choices, the rendered python_version()/classifiers() branches and
check_upstream's EOL check all follow without a second edit.

## Direction

This file is the first slice of "one root meta-definition": type-specific
constraints (ROS's ament layout, MicroPython's firmware tree, OJ's bare
workspace) move here next, and per-type template fragments render from it —
replacing the deep `{% if %}` ladders inside shared files with flat,
type-owned files where the constraint lives with the type (first cut:
partials/types/{standard,ros2}/tasks-model.jinja). Cross-type choices
(task runner, docs builder, `log_library`) stay shared questions — in
fragments/ when more than one area needs them; what is *unique* to a type
becomes catalog data.
