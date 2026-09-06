# Vision & Positioning

This page states, in one place, what this template is trying to become, how it
differs from the other templates in this space, and what it deliberately
does *not* try to be. It exists because a template that wants to be adopted
widely has to answer "why this one, not the other five?" in under a minute —
everything else in these docs answers "how do I use it", this page answers
"why does it exist".

## The one-line pitch

**One copier template that covers every shape of Python project a working
developer actually meets — library, service, data pipeline, competitive
programming, robotics, firmware — verified to the same standard a compiler
holds itself to, not just documented to that standard.**

Most opinionated templates pick one project shape (usually "installable
library") and do it well. This one treats "which shape of project" as a
first-class, combinable axis (`project_type` + layers, see
[Structure](structure.md)), and treats its own question logic as something
to *prove* correct rather than merely test by example:

- Every `when:` condition in the ~940-line (now fragmented, see
  [Authoring Template Sources](template-dev.md)) questionnaire is checked for
  satisfiability with an SMT solver (Z3) — a dead branch or a typo'd variable
  name is a test failure, not a support ticket six months later.
- Drift is tracked across five independent failure sources (template-source
  quality, rendered-output correctness, upstream toolchain aging, the
  DiamondLightSource fork relationship, and tooling accidents) crossed with
  four detection timings (local `lint`/`fix` runs, PR CI, scheduled runs, and the Z3 proof
  above) — see the MECE table this project keeps internally for the full
  matrix. A project can look correct on the day it's generated and silently
  rot when Ruff, basedpyright, or a pinned dependency releases something new
  months later with zero code changes; this template runs its own CI weekly
  against no-op changes specifically to catch that.
- Generated CI is SHA-pinned, zizmor-audited, and Scorecard-tracked from the
  first commit, not bolted on after an incident.

## Where this fits among the alternatives

No template is strictly better than the others — they're optimizing for
different things. As of 2026-09:

| | Project-type coverage | Update mechanism | Correctness approach | Backing |
|---|---|---|---|---|
| **This template** | library / cli / web_api / data_science / online_judge (5 kinds) / script / ros2 / micropython, combinable via layers | `copier update` | Z3 satisfiability proof + scheduled drift detection across 5 sources | Solo maintainer, pre-1.0 |
| [copier-uv](https://github.com/pawamoy/copier-uv) | Library, deliberately narrow | `copier update` | Example-based tests, mature and widely used | Solo maintainer (pawamoy), well-established |
| [scientific-python/cookie](https://github.com/scientific-python/cookie) | Scientific libraries specifically | `copier update` | Example-based tests | Scientific Python community (NumFOCUS-adjacent), institutional |
| [cookiecutter-hypermodern-python](https://github.com/cjolowicz/cookiecutter-hypermodern-python) | Library | None (cookiecutter, one-shot) | Example-based tests | Unmaintained since 2024-05 |
| `uv init` (Astral) | Library/app skeleton only | None | N/A — not opinionated about CI/docs/quality | Astral, official uv baseline |

Read this table as: if you want a minimal, battle-tested, uv-only library
template maintained by someone with a long track record, **copier-uv is a
completely reasonable and arguably lower-risk choice today** — this template
is newer and has not yet earned that track record externally. What this
template is betting on instead is breadth (one template for the *whole*
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

- **Full-stack web apps.** `project_type: web_django` aborts generation on
  purpose and points to `cookiecutter-django` and upstream FastAPI/Litestar
  docs instead. `web_api` stays deliberately API-only.
- **Auth, admin UIs, task queues baked into `web_api`.** Documented as
  "add later"; the recommended-settings gate for `web_api` is three switches
  (Prometheus, rate limiting, CORS), not a catalogue.
- **A GUI or web wizard for the questionnaire.** `copier copy` on the
  command line is the interface.
- **Being the template for languages other than Python** (the `ros2` C++
  option and MicroPython firmware are the two acknowledged exceptions,
  because they're how Python developers reach robotics/embedded work, not a
  general multi-language ambition).

If your use case falls in one of these gaps, this template will actively
tell you so at generation time rather than generate something half-working.

## Current status and how to help

This is a young, pre-1.0, solo-maintained project (recently forked from and
still diverging fast past
[DiamondLightSource/python-copier-template](https://github.com/DiamondLightSource/python-copier-template),
to which it owes its original structure and CI backbone). It does not yet
have the external track record the comparison table's other rows have
earned over years. Becoming "the standard" is a claim to be earned through
real generated projects surviving real `copier update` runs over years, not
a badge to self-assign — the roadmap toward that is tracked in this
repository's `TODO.md`.

The most useful contribution right now is not a new `project_type` — see
[Contributing](../how-to/contribute.md) — it's a bug report from an actual
generated project, or a link to a real repo demonstrating a behavior you
want changed (per [CONTRIBUTING](https://github.com/kasi-x/python-copier-template/blob/main/.github/CONTRIBUTING.md),
this template treats "show me the repo where this matters" as the way
changes get evaluated).
