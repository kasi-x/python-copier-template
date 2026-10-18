# The shortest path to change the template

One page: the smallest change that does what you want, and the one command
that proves it. Everything else in these docs explains the machinery; this
page skips it.

## First, find the files

Name the setting you want to change (or part of its name) and the
repository lists every file it touches, plus what to run afterwards:

```shell
task where -- docs_type      # or: architekton-py where sentry
```

## Which change are you making?

| You want to … | Touch | Prove it with |
|---|---|---|
| Fix prose (README, docs, comments) | the file itself | `task lint type-check` |
| Change what a render produces (`template/`, `partials/`, `questions/`) | the source file(s) | `task verify-delta` — narrows the 272 witness leaves to the ones your edit can affect, re-renders only those, and exits 0 when every candidate is byte-identical |
| Change the questions (`questions/NN-<area>.yml`) | the area's file; NN is the ask order | `task regen` then `task test-fast` |
| Add a field rule (licensing drift, personal data, …) | nothing here — see below | — |

The full blast-radius table (what CI gates per scope) is in
[CONTRIBUTING](https://github.com/politeuma/architekton-py/blob/main/CONTRIBUTING.md).

## Field rules live upstream

Ethics / regional / operational rule text is not template content: it lives
in [law-map's guidance tree](https://github.com/politeuma/law-map/tree/main/guidance/sections)
(`guidance/sections/<tier>/<slug>.md`, plain Markdown with YAML front
matter; the generated index is `guidance/sections/MANIFEST.yml`). This
template only derives the abstract `when` conditions in
`partials/daimonion-when.jinja`. So a rule fix is a law-map pull request
(copy `guidance/sections/_template.md`, run `just manifest`); only a *new*
condition extends the macro here — see [How to add an ethics section](ethics-section.md).

## The meta-tooling, in one paragraph

`architekton/` (~50 modules, [mapped by job](https://github.com/politeuma/architekton-py/blob/main/architekton/README.md)), the 25 workflows, and the Quint specs exist to hold
the render contract: Z3 enumerates the 272 answer leaves, the render matrix
renders each one, invariants check the output, and the update rehearsal
proves `copier update` lands cleanly. You do not need to understand any of
it to change the template — `verify-delta` (template edits) and `regen`
(questionnaire edits) run the relevant slice for you. Read
[Authoring Template Sources](../explanations/template-dev.md) when a guard
fails and you need to know why, not before.

## Commands

```shell
task where -- <setting> # which files to edit
task lint type-check   # docs-only change
task verify-delta      # template payload change: which leaves can this affect?
task regen             # questionnaire change: leaves -> verdicts -> docs
task test-fast         # the edit loop (~1 min)
```
