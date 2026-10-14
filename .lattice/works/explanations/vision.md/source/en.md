# Vision & Positioning

This page states, in one place, what this template is trying to become, how it
differs from the other templates in this space, and what it deliberately
does <lt-m v="*"/>not<lt-m v="*"/> try to be. It exists because a template that wants to be adopted
widely has to answer "why this one, not the other five?" in under a minute —
everything else in these docs answers "how do I use it", this page answers
"why does it exist".

## The one-line pitch

**One copier template that covers every shape of Python project a working
developer actually meets — library, service, data pipeline, competitive
programming, robotics, firmware — with its question logic machine-checked and
every answer path's render tested, not just documented.**

It is one adoption entry point into the wider politeuma rule distribution,
not its end: the canonical picture is the
<lt-m v="["/>politeuma architecture diagram<lt-m v="](https://github.com/politeuma/.github/blob/main/profile/diagram.md)"/>,
where law-map is the rulebook, its guidance tree holds the prose, and daimonion
delivers the matching rules into any repository's `AGENTS.md`. This template
is the way in for <lt-m v="*"/>new Python projects<lt-m v="*"/>; any existing repository, in any
language, adopts the same rules through daimonion directly.

Most opinionated templates pick one project shape (usually "installable
library") and do it well. This one treats "which shape of project" as a
first-class, combinable axis (`project_type` + layers, see
<lt-m v="["/>Structure<lt-m v="](structure.md)"/>), and checks its own question logic mechanically
rather than only by example:

- Every `when:` condition in the ~940-line (now fragmented, see
  <lt-m v="["/>Authoring Template Sources<lt-m v="](template-dev.md)"/>) questionnaire is checked for
  satisfiability with an SMT solver (Z3), and the solver enumerates every
  answer leaf — a dead branch or a typo'd variable name is a test failure,
  not a support ticket six months later. That is a statement about the input
  space only: what each leaf renders is covered by output invariants over all
  leaves and by executing a sample of them, and
  <lt-m v="["/>Verification<lt-m v="](verification.md)"/> states what each layer cannot prove.
- Drift is tracked across five independent failure sources (template-source
  quality, rendered-output correctness, upstream toolchain aging, the
  DiamondLightSource fork relationship, and tooling accidents) crossed with
  four detection timings (local `lint`/`fix` runs, PR CI, scheduled runs, and the Z3 check
  above) — see the MECE table this project keeps internally for the full
  matrix. A project can look correct on the day it's generated and silently
  rot when Ruff, basedpyright, or a pinned dependency releases something new
  months later with zero code changes; this template runs its own CI weekly
  against no-op changes specifically to catch that.
- Generated CI is SHA-pinned, zizmor-audited, and Scorecard-tracked from the
  first commit, not bolted on after an incident.

## Name origin

The project is now architekton-py — Greek <lt-m v="*"/>architekton<lt-m v="*"/>, the master-builder:
the template is the master-builder's plan, which says what must hold rather
than what to build. That is exactly this template's posture: it never tells
you <lt-m v="*"/>what<lt-m v="*"/> to build (the questionnaire is yours to answer); it only refuses,
aborts, and warns when a render path would be unsound.

<lt-m v="*"/>Architekton<lt-m v="*"/> — the master builder who works from a plan.

## Where this fits among the alternatives

No template is strictly better than the others — they're optimizing for
different things. As of 2026-09:

| | Project-type coverage | Update mechanism | Correctness approach | Backing |
|---|---|---|---|---|
| <lt-m v="**"/>This template<lt-m v="**"/> | library / cli / web_api / data_science / online_judge (5 kinds) / script / ros2 / micropython, combinable via layers | `copier update` | Z3 satisfiability of question logic, render invariants over every leaf, sampled execution, scheduled drift detection across 5 sources | Solo maintainer, 7.0.0 upcoming |
| <lt-m v="["/>copier-uv<lt-m v="](https://github.com/pawamoy/copier-uv)"/> | Library, deliberately narrow | `copier update` | Example-based tests, mature and widely used | Solo maintainer (pawamoy), well-established |
| <lt-m v="["/>scientific-python/cookie<lt-m v="](https://github.com/scientific-python/cookie)"/> | Scientific libraries specifically | `copier update` | Example-based tests | Scientific Python community (NumFOCUS-adjacent), institutional |
| <lt-m v="["/>cookiecutter-hypermodern-python<lt-m v="](https://github.com/cjolowicz/cookiecutter-hypermodern-python)"/> | Library | None (cookiecutter, one-shot) | Example-based tests | Unmaintained since 2024-05 |
| `uv init` (Astral) | Library/app skeleton only | None | N/A — not opinionated about CI/docs/quality | Astral, official uv baseline |

Read this table as: if you want a minimal, battle-tested, uv-only library
template maintained by someone with a long track record, **copier-uv is a
completely reasonable and arguably lower-risk choice today** — this template
is newer and has not yet earned that track record externally. What this
template is betting on instead is breadth (one template for the <lt-m v="*"/>whole<lt-m v="*"/>
range of project shapes a career touches, not just libraries) plus
correctness engineering that scales with that breadth. If you only ever
write installable libraries, that bet doesn't pay for you.

`cookiecutter-hypermodern-python`'s userbase is effectively orphaned (no
push since 2024-05) — if that template shaped how you think a Python
project should look, the opinions here descend from the same lineage
(ruff/mypy-family strictness, full CI, docs-as-code) updated for the
uv/copier/2026 toolchain.

## What this is deliberately not

Saying no explicitly is part of the pitch — a template that tries to be
everyone's best option for everything becomes no one's best option for
anything. Concretely, out of scope:

- <lt-m v="**"/>Full-stack web apps.<lt-m v="**"/> Django is not a `project_type` at all (the choice
  never renders; it only pointed at `cookiecutter-django`). The how-to names
  FastAPI / Litestar / Flask and upstream `cookiecutter-django` as the
  alternatives. `web_api` stays deliberately API-only.
- <lt-m v="**"/>Auth, admin UIs, task queues baked into `web_api`.<lt-m v="**"/> Documented as
  "add later"; the recommended-settings gate for `web_api` is three switches
  (Prometheus, rate limiting, CORS), not a catalogue.
- <lt-m v="**"/>A GUI or web wizard for the questionnaire.<lt-m v="**"/> `copier copy` on the
  command line is the interface.
- <lt-m v="**"/>Being the template for languages other than Python<lt-m v="**"/> (the `ros2` C++
  option and MicroPython firmware are the two acknowledged exceptions,
  because they're how Python developers reach robotics/embedded work, not a
  general multi-language ambition).

If your use case falls in one of these gaps, this template will actively
tell you so at generation time rather than generate something half-working.

## The recommended path and its guarantees

The questionnaire's recommended answers (uv + just + zensical, `recommended`
strictness) are the only combination CI executes end to end — `uv sync`,
the generated pytest, basedpyright, and the docs build on every witness
sample leaf (the `full` tier in <lt-m v="["/>Support Levels<lt-m v="](../reference/support.md)"/>).
Every other option the questionnaire keeps (poetry / pixi, the other six
task runners, Sphinx / great-docs, ty, ros2, the non-AtCoder judges) still
renders and is ruff-checked, but is community-supported: it ships because
someone uses it, and it stays because someone runs it — CI does not execute
it. Reporting a break there with a reproducing render is the contribution
that keeps it.

This is a young, solo-maintained project (recently forked from and
still diverging fast past
<lt-m v="["/>DiamondLightSource/python-copier-template<lt-m v="](https://github.com/DiamondLightSource/python-copier-template)"/>,
to which it owes its original structure and CI backbone). It does not yet
have the external track record the comparison table's other rows have
earned over years. Becoming "the standard" is a claim to be earned through
real generated projects surviving real `copier update` runs over years, not
a badge to self-assign — the roadmap toward that is tracked in the
repository's issues and the maintainers' internal notes.

The most useful contribution right now is not a new `project_type` — see
<lt-m v="["/>Contributing<lt-m v="](../how-to/contribute.md)"/> — it's a bug report from an actual
generated project, or a link to a real repo demonstrating a behavior you
want changed (per <lt-m v="["/>CONTRIBUTING<lt-m v="](https://github.com/politeuma/architekton-py/blob/main/.github/CONTRIBUTING.md)"/>,
this template treats "show me the repo where this matters" as the way
changes get evaluated).
