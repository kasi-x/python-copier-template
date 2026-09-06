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
  [docs/explanations/vision.md](docs/explanations/vision.md) and the scope
  rules in [TODO.md](TODO.md));
- merges or rejects pull requests;
- is, for now, the bus factor. This is a known risk and the reason the
  next section exists.

## Adding maintainers

A second maintainer will be added when someone has:

1. a track record here — several merged, non-trivial PRs, or substantial
   reviewed feedback on the questionnaire/design surfaces;
2. demonstrated agreement with the design principles (TODO.md, section
   "設計原則" / design principles) — in particular the reluctance to add a
   new `project_type` or option without a "what existing layer does this
   sit on?" answer;
3. time to review, not only to build.

The invitation is made by the current maintainer, publicly in an issue.

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
  (`tools/check_upstream.py`).

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
