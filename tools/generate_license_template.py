"""Regenerate the LICENSE templates from the vendored choosealicense.com texts.

The license bodies under ``tools/licenses/*.txt`` are full, verbatim license
texts sourced from https://github.com/github/choosealicense.com (the same
data GitHub's own repository-creation license picker uses), with a small,
explicit set of bracketed placeholders swapped for Jinja expressions:

    [year] / [yyyy] / [Year]                                -> {{ license_year }}
    [fullname] / [name of copyright owner/holder]            -> {{ author_name }}
    [email]                                                  -> {{ author_email }}
    [project] / [Software Name]                              -> {{ repo_name }}
    [projecturl]                                              -> {{ repo_url }}

Nothing else in the legal text is touched (in particular, the GPL family's
own "how to apply these terms" appendix, which uses angle brackets like
``<year>``/``<name of author>``, is left exactly as published).

Run this script (`python tools/generate_license_template.py`) after updating
the files in `tools/licenses/` to refresh:

- `template/{% if detail_level == 'detailed' %}LICENSE{% endif %}.jinja`
  (the full if/elif chain, one branch per license choice)
- `template/{% if detail_level == 'simple' %}LICENSE{% endif %}.jinja`
  (just the MIT text, used when detail_level == 'simple' so that mode never
  has to evaluate the full chain above)

It also prints the `license:` question's `choices:` mapping to paste into
`copier.yml` if the license set has changed.
"""

from __future__ import annotations

import json
from pathlib import Path

TOOLS_DIR = Path(__file__).parent
LICENSES_DIR = TOOLS_DIR / "licenses"
TEMPLATE_DIR = TOOLS_DIR.parent / "template"

PROPRIETARY_BODY = """\
Copyright (c) {{ license_year }} {{ author_name }}. All Rights Reserved.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
ALL CONTENTS OF THIS REPOSITORY ARE PROPRIETARY AND CONFIDENTIAL.
UNAUTHORIZED COPYING, REPRODUCTION, OR DISTRIBUTION OF THIS SOFTWARE,
VIA ANY MEDIUM, IS STRICTLY PROHIBITED.
"""

CONFIDENTIAL_BODY = """\
Copyright (c) {{ license_year }} {{ author_name }}. All Rights Reserved.

CONFIDENTIAL AND PROPRIETARY INFORMATION.

This repository contains trade secrets and confidential information
belonging to {{ author_name }}.
Access to this source code is strictly limited to authorized personnel.
Unauthorized copying, disclosure, or distribution of this software, in
whole or in part, via any medium, is strictly prohibited without prior
written permission.
"""


def load_licenses() -> list[tuple[str, str, str]]:
    """Return a list of (spdx_id, title, body) sorted by title."""
    meta = json.loads((LICENSES_DIR / "_meta.json").read_text(encoding="utf-8"))
    licenses = []
    for stem, info in meta.items():
        body = (LICENSES_DIR / f"{stem}.txt").read_text(encoding="utf-8")
        licenses.append((info["spdx"], info["title"], body))
    licenses.sort(key=lambda x: x[1])
    return licenses


def render_chain(licenses: list[tuple[str, str, str]]) -> str:
    parts = []
    for i, (spdx, _title, body) in enumerate(licenses):
        tag = "if" if i == 0 else "elif"
        parts.append(f'{{% {tag} license_effective == "{spdx}" -%}}\n{body}')
    parts.append(f'{{% elif license_effective == "Confidential" -%}}\n{CONFIDENTIAL_BODY}')
    parts.append(f'{{% elif license_effective == "Proprietary" -%}}\n{PROPRIETARY_BODY}')
    # No separator: each body already ends in exactly one "\n", so whichever
    # branch Jinja picks renders with exactly one trailing newline too. And no
    # newline after `{% endif %}` itself: copier sets `keep_trailing_newline`,
    # so a trailing "\n" in the *source* here would be appended, literally,
    # after every rendered branch.
    parts.append("{% endif %}")
    return "".join(parts)


def render_simple(licenses: list[tuple[str, str, str]]) -> str:
    """MIT, Confidential or Proprietary — simple mode's `license_simple` choices."""
    mit_body = next(body for spdx, _title, body in licenses if spdx == "MIT")
    return (
        f'{{% if license_effective == "MIT" -%}}\n{mit_body}'
        f'{{% elif license_effective == "Confidential" -%}}\n{CONFIDENTIAL_BODY}'
        f'{{% elif license_effective == "Proprietary" -%}}\n{PROPRIETARY_BODY}'
        "{% endif %}"
    )


def main() -> None:
    licenses = load_licenses()

    # No trailing newline after the source's closing `{% endif %}`: copier
    # sets `keep_trailing_newline`, so one here would be appended, literally,
    # after every rendered branch (each branch's own body already ends in
    # exactly one "\n").
    detailed_path = TEMPLATE_DIR / "{% if detail_level == 'detailed' %}LICENSE{% endif %}.jinja"
    detailed_path.write_text(render_chain(licenses), encoding="utf-8")
    print(f"wrote {detailed_path}")

    simple_path = TEMPLATE_DIR / "{% if detail_level == 'simple' %}LICENSE{% endif %}.jinja"
    simple_path.write_text(render_simple(licenses), encoding="utf-8")
    print(f"wrote {simple_path}")

    print("\n# Paste into copier.yml's `license:` question if the set changed:")
    print("    choices:")
    for spdx, title, _body in licenses:
        print(f"        {title}: {spdx}")
    print("        Proprietary / all rights reserved: Proprietary")
    print("        Confidential / trade secrets: Confidential")


if __name__ == "__main__":
    main()
