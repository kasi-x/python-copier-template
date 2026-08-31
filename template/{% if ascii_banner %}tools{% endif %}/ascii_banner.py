"""Regenerate the ASCII-art banner in README.md.

Replaces the marker block between ``<!-- ASCII-BANNER-START -->`` and
``<!-- ASCII-BANNER-END -->`` with a figlet rendering of the repo name.

Uses the bundled MIT-licensed copy of pyfiglet (see ``_figlet.py``) and the
``slant`` font, so no external dependencies are required.

Usage:
    python tools/ascii_banner.py <repo_name> [path/to/README.md]
"""

from __future__ import annotations

import sys
from pathlib import Path

import _figlet

START = "<!-- ASCII-BANNER-START -->"
END = "<!-- ASCII-BANNER-END -->"


def render_banner(text: str) -> str:
    return _figlet.figlet_format(text, font="slant")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    repo_name = sys.argv[1]
    readme = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("README.md")

    if not readme.exists():
        print(f"README not found: {readme}", file=sys.stderr)
        return 1

    banner = f'<pre align="center">\n{render_banner(repo_name)}</pre>'
    block = f"{START}\n{banner}\n{END}"

    text = readme.read_text()
    if START in text and END in text:
        start_idx = text.index(START)
        end_idx = text.index(END) + len(END)
        text = text[:start_idx] + block + text[end_idx:]
    else:
        # No banner yet; insert after the first heading if present, else at top.
        marker = f"\n\n{block}\n"
        lines = text.split("\n", 1)
        text = lines[0] + marker + (lines[1] if len(lines) > 1 else "")

    # Ensure the file ends with exactly one newline (end-of-file-fixer).
    if not text.endswith("\n"):
        text += "\n"

    readme.write_text(text)
    print(f"Banner written to {readme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
