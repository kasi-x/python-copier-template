# Governance

This document states how decisions are made in this repository. It is
short on purpose: the project currently has one maintainer, and pretending
otherwise would be less honest than saying so plainly.

## Current model: BDFL

The project is maintained as a **BDFL-style project** with a single
maintainer: [kasi-x](https://github.com/kasi-x) (also the sole entry in
[.github/CODEOWNERS](.github/CODEOWNERS)). The maintainer:

- decides the roadmap and the scope boundaries (see the "What this is
  deliberately not" section of
  [docs/explanations/vision.md](docs/explanations/vision.md) and the
  [design principles](docs/explanations/design-principles.md));
- merges or rejects pull requests;
- is, for now, the bus factor. This is a known risk and the reason the
  next section exists.

## Adding maintainers

A second maintainer will be added when someone has:

1. a track record here — several merged, non-trivial PRs, or substantial
   reviewed feedback on the questionnaire/design surfaces;
2. demonstrated agreement with the design principles
   ([docs/explanations/design-principles.md](docs/explanations/design-principles.md))
   — in particular the reluctance to add a new `project_type` or option
   without a "what existing layer does this sit on?" answer;
3. time to review, not only to build.

The invitation is made by the current maintainer, publicly in an issue.

## Layer ownership

The questionnaire's layers are listed in [.github/CODEOWNERS](.github/CODEOWNERS)
by path (question fragment, template files, preset, per-layer tests). Each
layer may have a distinct owner once contributors exist.

**Ownerless-layer rule**: a layer whose row lists no owner besides the
maintainer is *supported* but not *staffed*. When the maintainer stops
reviewing a layer's area, that layer's leaves drop to the `experimental`
tier in [docs/reference/support.md](docs/reference/support.md) — they keep
rendering, but the support matrix says so honestly rather than implying a
reviewer exists. Regaining `supported` requires a named owner who reviews
that layer's PRs.

**Promotion path** (triager → layer owner → core maintainer):

1. *Triager*: anyone may triage issues and review PRs informally; sustained,
   accurate triage is the visible track record.
2. *Layer owner*: a contributor with several merged non-trivial PRs inside
   one layer is added to that layer's CODEOWNERS row by the maintainer.
   Layer owners review changes in their area; merges still go through the
   maintainer.
3. *Core maintainer*: a layer owner who additionally meets the "Adding
   maintainers" criteria above and reviews outside their layer.

## Scope and support commitments

A proposal for a new project type, layer, or supported toolchain path must
state:

1. who needs it and what existing path does not cover;
2. who will own ongoing updates and failures;
3. the support tier it is expected to meet, and the verification needed for
   that tier.

If there is no owner, the option must remain experimental or the proposal
must be declined. Do not treat a passing render, a larger witness matrix, or
the presence of generated files as proof that a path is fully supported.
Keep support claims aligned with the evidence in
[the support matrix](docs/reference/support.md). Prefer strengthening
existing paths over expanding the questionnaire; remove or narrow paths when
their maintenance cost is no longer justified.

## Release discipline

`architekton-py new`, `architekton-py adopt`, and `architekton-py update` are the public
interface and follow the compatibility policy documented in the installation
tutorial. A release must validate the revision users will actually resolve
from the template source, not only an untagged working tree. Required CI must
be green; any job blocked by external credentials must be classified and
resolved or explicitly accepted before release, never silently counted as a
pass.

Before release, review the support matrix and update-rehearsal result against
the candidate revision. Generated-project claims must not exceed what those
checks executed. When coverage or rehearsal is incomplete, document the gap
and keep the affected path at its existing support tier rather than implying
confidence the evidence does not provide.

## How contributions are reviewed

- **Big changes start as an issue first** (also stated in
  [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md)). "Big" means: a new
  question, project type, layer, or anything that changes generated files
  for existing answers.
- Every change that adds behavior must add a test that fails without it.
  The repo's own QA suite (ruff, basedpyright, zizmor/actionlint, the
  render-matrix tests) is the minimum bar; CI must be green.
- Changes to the questionnaire must keep the structural tests green:
  fragment union, forward-only references, and the Z3 satisfiability sweep
  (`tests/test_copier_structure.py`).
- Template defaults and pins must respect the freshness policy
  ([docs/explanations/template-dev.md](docs/explanations/template-dev.md))
  and, where a value is hardcoded, the upstream-check tooling
  (`architekton/check_upstream.py`).

## Ethics, regional, and operational rules

The ethics sections live in the [`daimonion`](https://github.com/politeuma/daimonion)
linter's kanon corpus ([`politeuma/kanon`](https://github.com/politeuma/kanon)),
not in this repository: section texts, sources, and review cadence are pull
requests there. This repo owns only the wiring — the derived `when`
conditions the template emits into the generated `.daimonion.yml`
(`_shared/daimonion-when.jinja`), which `daimonion agents-md --write` matches
against kanon. The template states rules of thumb, it does not give legal advice.

## Relationship to upstream

This repository started as a fork of
[DiamondLightSource/python-copier-template](https://github.com/DiamondLightSource/python-copier-template)
and is being prepared for an independent v1.0 release (see TODO item 11).
Upstream remains credited as the origin; governance here is independent of
upstream governance.

## Changes to this document

Amendments follow the same path as any other change: an issue, then a PR
reviewed by the maintainer. Once a second maintainer exists, amendments to
this file will require both.
