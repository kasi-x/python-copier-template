# python-copier-template Issues & Bugs

This file documents issues, bugs, and confusion points encountered while using the template.

## Issue 1: `docs_type` validation rejects valid choices

**Severity**: High (blocks generation)
**Date**: 2026-09-05

### Description
When providing `docs_type: zensical` via `--data-file`, the template rejects it with:
```
ValueError: Invalid choice for 'docs_type': 'zensical' is not in ['README', 'sphinx']
```

### Expected Behavior
`zensical` should be a valid choice for non-micropython projects (as documented in `_common_b.yml`).

### Root Cause
The `docs_type` question uses dynamic choices based on `micropython_pkg`:
```yaml
choices: |
    {%- if micropython_pkg %}
    - README
    - zensical
    - great-docs
    {%- else %}
    - README
    - zensical
    - sphinx
    - great-docs
    {%- endif %}
```

But validation appears to only check against `['README', 'sphinx']`, suggesting the Jinja conditional isn't being evaluated during validation.

### Workaround
Setting `use_recommended_docs: false` and providing `docs_type: zensical` still fails. The only working option seems to be `use_recommended_docs: true` (which defaults to zensical), but this also fails with "Question 'docs_type' is required".

### Root Cause (corrected 2026-09-06)
**The error message `['README', 'sphinx']` is the giveaway: it is the choice
list of the OLD DiamondLightSource template, not of this one.** This repo is
a fork that inherited upstream git tags; the latest inherited tag is `5.4.0`
(2026-08-14, DiamondLightSource content — its `copier.yml` asks
`component_owner` and offers exactly `docs_type: [README, sphinx]`). Running
`copier copy URL` **without `--vcs-ref`** makes copier check out the latest
tag, so the generator silently used the old pre-fork template where
`zensical` genuinely is an invalid choice. The dynamic-Jinja-choices theory
below was wrong: a minimal reproduction against copier 9.18.1 shows dynamic
choices render and validate correctly.

### Fix Applied (2026-09-05, kept as hardening)
Changed from Jinja-based dynamic choices to static inline choices:
```yaml
choices: [README, zensical, sphinx, great-docs]
```

### Status
**Fixed (docs)** — README / docs/tutorials now pass `--vcs-ref=main` for
URL-based copies. The inherited-tag problem is tracked in TODO 11 (tags are
retagged/deleted at the v1.0 fork detach); until then `--vcs-ref=main` is
required for every remote-URL invocation.

---

## Issue 2: `--data-file` doesn't provide answers for validation

**Severity**: Medium
**Date**: 2026-09-05

### Description
The `--data-file` flag loads data for template rendering but doesn't seem to populate the answers used for question validation. Questions still fail with "required" errors even when their values are in the data file.

### Expected Behavior
Values from `--data-file` should satisfy required question validation.

### Status
**Verified fixed (2026-09-06)**: `--data-file` values DO drive `when` gating
and satisfy required questions once `--trust` is passed. Copier silently
refuses to generate at all without `--trust` when a template declares
`_jinja_extensions` (exit status 4, no files written) — the errors reported
here were that refusal plus the docs_type choices bug (Issue 1). The README
non-interactive section now states the exact working invocation.

---

## Issue 3: `--answers-file` requires relative path

**Severity**: Low (documentation issue)
**Date**: 2026-09-05

### Description
Using an absolute path for `--answers-file` fails:
```
ValueError: "/tmp/answers.yml" is not a relative path
```

The help text says "relative to `destination_path`" but this isn't obvious from the CLI help.

### Workaround
Copy the answers file to the destination directory and use a relative path.

### Status
**Documented (2026-09-06)**: noted in the README non-interactive section.

---

## Issue 4: Non-interactive generation is difficult

**Severity**: High
**Date**: 2026-09-05

### Description
Generating a project without interactive prompts requires a specific combination of flags that isn't well-documented:
- `--defaults` for default values
- `--data-file` for custom values
- `--force` to overwrite existing files

Even with all flags, validation issues (see Issue 1) block generation.

### Expected Behavior
A documented `--non-interactive` mode or clear examples of non-interactive usage.

### Fix Applied (2026-09-05)
1. Added defaults to required questions (`package_name`, `description`, `git_platform`)
2. Added non-interactive mode documentation to README.md
3. Fixed Issue 1 (docs_type choices) which was blocking non-interactive generation

### Status
**Fixed**

---

## Issue 5: Jinja Extensions Not Found with `uvx`

**Severity**: Blocker (first-run experience)
**Date**: 2026-09-05

### Description
Running `uvx copier copy` fails with:
```
Copier could not load some Jinja extensions:
No module named 'copier_template_extensions'
```

### Root Cause
The template declares `_jinja_extensions` in `copier.yml` that depend on
`copier_template_extensions` and its own `extensions.py`. These are installed in the
template repo's `.venv` but `uvx` runs copier in an isolated environment without them.

### Workaround
Use the template's own venv copier:
```bash
/home/user/dev/python-copier-template/.venv/bin/copier copy ...
```

### Expected
`uvx copier copy` should work out of the box, or the README should document
that the template's venv copier must be used.

### Status
**Documented (2026-09-06)**: the template's own venv copier works (the
dev dependency is installed there), and the documented spell for isolated
runs is `uvx --with copier-template-extensions copier copy --trust ...`
(the same invocation the example-regeneration CI uses). Copier cannot load
custom Jinja extensions from the template directory alone; the pip package
must be importable by copier itself.

---

## Issue 6: Undocumented `component_owner` Question

**Severity**: Medium (confusion)
**Date**: 2026-09-05

### Description
When running with partial `-d` flags, copier asked for `component_owner`:
```
ValueError: Question "component_owner" is required
```

### Root Cause
This question is not in `copier.yml` or `questions/` — it appears to come from the
`copier_template_extensions` package or some dynamic source. grep for `component_owner`
in the template returns no results.

### Expected
All questions should be discoverable in the template source, or at least documented.

### Status
**Explained (2026-09-06, cause corrected)**: `component_owner` does not
exist anywhere in the current template (grep across copier.yml, questions/,
template/ — zero hits). It IS asked by the inherited upstream tag `5.4.0`:
`git show 5.4.0:copier.yml` contains a `component_owner` question. Running
`copier copy URL` without `--vcs-ref` checks out that latest tag (old
DiamondLightSource template), which is where the question came from — not
from stale `.copier-answers.yml` as first explained. Same fix as Issue 1:
pass `--vcs-ref=main` (README/docs updated), and the inherited tags are
handled at the v1.0 fork detach (TODO 11).

---

## Issue 7: Local Template Requires `--vcs-ref=HEAD` for Dirty Repos

**Severity**: Minor
**Date**: 2026-09-05

### Description
When using a local template path (not a git remote), copier warns:
```
DirtyLocalWarning: Dirty template changes included automatically.
```

### Expected
Local template copies should not require VCS flags, or this should be documented.

### Status
Documentation issue

---

## Issue 8: Pixi + Web API: No `pixi.toml` Generated

**Severity**: Minor (confusion)
**Date**: 2026-09-05

### Description
When selecting `package_manager=pixi`, the template generates a `pixi.lock` but the main
configuration is in `pyproject.toml` under `[tool.pixi.*]` sections. There's no standalone
`pixi.toml`, which some users might expect (especially those already using pixi with
`pixi.toml`).

### Note
This is actually correct per the template design, but the migration from a `pixi.toml`-based
project could be better documented.

### Status
Documentation issue

---

## Issue 9: Data Science + Web API: `src/` Directory Relationship Unclear

**Severity**: Medium (architecture confusion)
**Date**: 2026-09-05

### Description
With `web_api` + `data_science`, you get both `app/` (FastAPI) and `src/` (data science
pipeline). The `src/` layout has `src/data`, `src/features`, `src/models`, etc. — but no
clear guidance on how these interact with `app/`.

### Expected
A brief README note or AGENTS.md section explaining the intended relationship
between `app/` and `src/` when both are present.

### Status
**Fixed (2026-09-06)**: web_api + data_science projects now ship the
explanation in both places — a "two trees coexist" section in the generated
README (`app/` = the FastAPI service, `src/` = the analysis pipeline) and a
callout in AGENTS.md telling agents to keep analysis out of `app/` and not
commit data/models/reports. Covered by
`test_template_web_api_data_science_combo_guide`.

---

## Issue 10: Pixi dependency format in pyproject.toml

**Severity**: High (blocks installation)
**Date**: 2026-09-05

### Description
When using pixi with pyproject.toml, the dependency format needs to be:
```toml
[tool.pixi.dependencies]
package = "version"
```

Not separate tables per package like:
```toml
[tool.pixi.dependencies.package]
version = "version"
```

### Error
```
Error: invalid character in string
```

### Status
Documentation issue - the template should document the correct format

---

## Issue 11: PyTorch version conflict with conda-forge

**Severity**: High (blocks installation)
**Date**: 2026-09-05

### Description
The template generates conda-forge dependencies that may not have the latest versions. For example, `pytorch>=2.0` fails because conda-forge only has `pytorch<=1.0.2` for some platforms.

### Error
```
Because only pytorch<=1.0.2 is available and you require pytorch>=2.0,
we can conclude that your requirements are unsatisfiable.
```

### Expected Behavior
Either:
1. The template should not pin major versions that may not be available
2. Or provide clear guidance on how to handle version conflicts
3. Or use pip dependencies for packages not available in conda-forge

### Status
**Documented (2026-09-06)**: see [docs/how-to/pixi.md](docs/how-to/pixi.md)
— flat `[tool.pixi.dependencies]` tables, the conda vs PyPI split
(`[tool.pixi.pypi-dependencies]`), PyTorch/CUDA guidance via the PyPI index,
and a `pixi.toml` migration recipe.

---

## Issue 12: Template generates `dependencies = []` by default

**Severity**: Medium (confusion)
**Date**: 2026-09-05

### Description
The generated pyproject.toml has an empty dependencies list:
```toml
dependencies = [] # Add project dependencies here, e.g. ["click", "numpy"]
```

This requires manual editing to add project dependencies. The template could at least include the recommended dependencies for the selected project type (e.g., data science projects would get numpy, pandas, etc.).

### Expected Behavior
Auto-populate dependencies based on project type and selected options.

### Status
Enhancement request

---

## Issue 13: No migration guide from pixi.toml to pyproject.toml

**Severity**: Medium (migration pain)
**Date**: 2026-09-05

### Description
For users migrating from a pixi.toml-based project to the template's pyproject.toml format, there's no guidance on:
1. How to convert pixi.toml dependencies to [tool.pixi.dependencies] format
2. How to migrate tasks
3. How to handle feature flags

### Expected Behavior
A migration guide or tool to help convert existing pixi.toml projects.

### Status
Documentation issue

---

## Summary

| Issue | Severity | Status |
|-------|----------|--------|
| docs_type validation | High | **Fixed** |
| --data-file answers | Medium | **Verified fixed** (needs `--trust`) |
| --answers-file relative path | Low | **Documented** |
| Non-interactive mode | High | **Fixed** |
| Jinja extensions not found with `uvx` | High | **Documented** (`uvx --with ...`) |
| Undocumented `component_owner` question | Medium | **Explained** (stale upstream answers) |
| Dirty local template warning | Low | Documentation |
| No standalone `pixi.toml` | Low | **Documented** (docs/how-to/pixi.md) |
| `src/` + `app/` relationship unclear | Medium | **Fixed** (generated README + AGENTS.md note) |
| Pixi dependency format | High | **Documented** (docs/how-to/pixi.md) |
| PyTorch version conflict | High | **Documented** (docs/how-to/pixi.md) |
| Empty dependencies by default | Medium | Open (enhancement) |
| No pixi.toml migration guide | Medium | **Documented** (docs/how-to/pixi.md) |

## Fixes Applied (2026-09-05)

1. **docs_type choices** (`questions/_common_b.yml`): Changed from Jinja-based dynamic choices to static inline choices `[README, zensical, sphinx, great-docs]`
2. **Required question defaults** (`questions/_common_c.yml`): Added defaults to `package_name`, `description`, `git_platform`
3. **Non-interactive documentation** (`README.md`): Added section on non-interactive usage with examples

**2026-09-06 addition**: Issues 1 and 6 share one root cause this file
originally misattributed — generating **without `--vcs-ref`** makes copier
use the latest git tag, which here is the inherited pre-fork `5.4.0`
(DiamondLightSource template: its `docs_type` choices are exactly
`['README', 'sphinx']` and it asks `component_owner`). README /
docs/tutorials now pass `--vcs-ref=main`; Issue 2's "verified fixed" note
applies once that flag is present.
