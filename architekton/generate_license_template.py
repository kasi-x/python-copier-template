"""Regenerate the LICENSE templates from the vendored choosealicense.com texts.

The license bodies under ``architekton/licenses/*.txt`` are full, verbatim license
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

Run this script (`python architekton/generate_license_template.py`) after updating
the files in `architekton/licenses/` to refresh:
- the gated LICENSE template (an if/elif dispatch chain, one ``{% include
  "partials/licenses/<spdx>.jinja" %}`` branch per license choice)
- the license bodies under ``partials/licenses/`` that those branches
  include

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


PARTIALS_DIR = TOOLS_DIR.parent / "partials" / "licenses"


def render_chain(licenses: list[tuple[str, str, str]]) -> str:
    """The LICENSE template: one branch per choice, each pulling its body from a partial.

    Each branch ``{% include "partials/licenses/<spdx>.jinja" %}`` so the dispatch
    file stays small enough to scan.
    """
    parts = []
    spdxes = [spdx for spdx, _title, _body in licenses] + ["Confidential", "Proprietary"]
    for i, spdx in enumerate(spdxes):
        tag = "if" if i == 0 else "elif"
        parts.append(f'{{% {tag} license_effective == "{spdx}" -%}}\n{{% include "partials/licenses/{spdx}.jinja" %}}')
    # Each partial ends in exactly one "\n", so whichever branch Jinja picks
    # renders with exactly one trailing newline too. The closing tag is
    # `{% endif -%}` followed by exactly one "\n": the `-` strips that
    # newline (so copier's `keep_trailing_newline` has nothing to append
    # after a rendered branch), and the newline keeps the file POSIX-final
    # so editors and git do not re-add one behind the generator's back --
    # regeneration must stay byte-clean against the shipped template.
    parts.append("{% endif -%}\n")
    return "".join(parts)


def license_bodies(licenses: list[tuple[str, str, str]]) -> dict[str, str]:
    """``partials/licenses/<spdx>.jinja`` contents, keyed by the branch name."""
    bodies = {spdx: body for spdx, _title, body in licenses}
    bodies["Confidential"] = CONFIDENTIAL_BODY
    bodies["Proprietary"] = PROPRIETARY_BODY
    return bodies


def main() -> None:
    licenses = load_licenses()

    license_path = TEMPLATE_DIR / "LICENSE.jinja"
    license_path.write_text(render_chain(licenses), encoding="utf-8")
    print(f"wrote {license_path}")

    PARTIALS_DIR.mkdir(parents=True, exist_ok=True)
    for spdx, body in license_bodies(licenses).items():
        partial_path = PARTIALS_DIR / f"{spdx}.jinja"
        partial_path.write_text(body, encoding="utf-8")
    print(f"wrote {len(license_bodies(licenses))} bodies under {PARTIALS_DIR}")

    print("\n# Paste into copier.yml's `license:` question if the set changed:")
    print("    choices:")
    for spdx, title, _body in licenses:
        print(f"        {title}: {spdx}")
    print("        Proprietary / all rights reserved: Proprietary")
    print("        Confidential / trade secrets: Confidential")


if __name__ == "__main__":
    main()
