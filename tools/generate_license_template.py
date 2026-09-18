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

- the gated LICENSE template (the full if/elif chain, one branch per
  license choice)

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
    # branch Jinja picks renders with exactly one trailing newline too. The
    # closing tag is `{% endif -%}` followed by exactly one "\n": the `-`
    # strips that newline (so copier's `keep_trailing_newline` has nothing to
    # append after a rendered branch), and the newline keeps the file
    # POSIX-final so editors and git do not re-add one behind the generator's
    # back -- regeneration must stay byte-clean against the shipped template.
    parts.append("{% endif -%}\n")
    return "".join(parts)


def main() -> None:
    licenses = load_licenses()

    license_path = (
        TEMPLATE_DIR / "{% if not existing_project or 'license' not in adopt_protect %}LICENSE{% endif %}.jinja"
    )
    license_path.write_text(render_chain(licenses), encoding="utf-8")
    print(f"wrote {license_path}")

    print("\n# Paste into copier.yml's `license:` question if the set changed:")
    print("    choices:")
    for spdx, title, _body in licenses:
        print(f"        {title}: {spdx}")
    print("        Proprietary / all rights reserved: Proprietary")
    print("        Confidential / trade secrets: Confidential")


if __name__ == "__main__":
    main()
