#!/usr/bin/env python3
"""The Project Details every render fixture in this repo starts from.

TODO §23.1: the same handful of values used to be literals in seven places --
`tests/test_recommended_path.py`, `tests/test_mcp_server.py`,
`tests/test_batch.py`, `test_example.py`'s `copy_project_recommended`
(the split moved it to `tests/support.py`), `tools/z3_witnesses.py` (whose
comment admitted it "mirrors tests/test_recommended_path.py:25-34"),
`example-answers.yml` and `batches/base.yml` (whose own comment made the same
promise). Nothing compared them, so tightening a validator (the e-mail, the
URLs derived from `github_org`) meant finding all seven by hand.

Why here and not in `tests/`: `tools/z3_witnesses.py` and `tools/batch.py` are
the repo's tools, and a tool cannot import a test module's fixture without
inverting the dependency; a test module importing another test module's fixture
couples modules that only share data. `tools/questionnaire.py` is the natural
owner of question *names* and defaults, but these values are the choices the
suite makes (a real-shaped e-mail, a real-looking org), not the questionnaire's.

`tests/test_questionnaire.py` checks every answer key any fixture uses against
the live questionnaire, and checks `batches/base.yml` against this dict, so a
rename in `copier.yml` or a hand-edited sample fails there instead of quietly
rendering a default.
"""

from __future__ import annotations

from typing import Any

# The Project Details the suite pins on purpose. copier's own defaults are
# placeholders (`my_package`, `Your Name`, `you@example.com`), so a fixture that
# took them would exercise placeholders in the validators that read these fields
# (CITATION.cff, codemeta.json, the generated pyproject URLs). `repo_name` and
# `distribution_name` are deliberately absent: copier derives them from
# `package_name`, and pinning them here would mean every fixture that overrides
# `package_name` had to restate the derivation by hand.
BASE: dict[str, Any] = {
    "package_name": "smoke_example",
    "description": "An example project",
    "git_platform": "github.com",
    "github_org": "kasi-x",
    "author_name": "kasi-x",
    "author_email": "kashimiya.exe@gmail.com",
}
