#!/usr/bin/env python3
"""Check the MicroPython pins in the template against official upstream.

The template pins the MicroPython release in ONE place — copier.yml's
`micropython_version` internal variable. That value drives both
freeze.py's DEFAULT_TAG (the tag the frozen-firmware build clones) and the
micropython-<port>-stubs pin in requirements-dev.txt, so the two cannot
drift apart by construction.

This script compares that single pin against the OFFICIAL MicroPython
release feed (micropython/micropython on GitHub):

- MicroPython tag (copier.yml micropython_version) — the drift check: it
  should track the latest stable release from the official project.
- Docker toolchain image tags per port — reported for awareness only (tags
  like :bookworm are distro codenames, not simple version numbers, so they
  are not auto-compared).
- The micropython-<port>-stubs pin — cross-checked against the PyPI release
  for the pinned version, so a missing stub release for a new MicroPython
  version is caught. Note these stubs come from the community
  josverl/micropython-stubs project, NOT the official MicroPython project.

Exits 0 when the MicroPython tag is current, 1 when a newer release exists
or the stubs are missing. Intended to run in CI (see
.github/workflows/check-micropython-upstream.yml) where a nonzero exit + the
drift report opens an issue.

Usage:
    python tools/check_micropython_upstream.py             # check against upstream
    python tools/check_micropython_upstream.py --offline   # report pins only
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
COPIER_YML = TOP / "copier.yml"
QUESTIONS_DIR = TOP / "questions"
FREEZE_TEMPLATE = (
    TOP
    / "template"
    / ("{% if micropython_pkg %}tools{% endif %}/{% if micropython_pkg %}micropython{% endif %}/freeze.py.jinja")
)
STUBS_TEMPLATE = TOP / "template" / ("{% if micropython_pkg %}requirements-dev.txt{% endif %}.jinja")


@dataclass
class Pin:
    name: str
    current: str
    upstream: str | None = None
    checkable: bool = False


def https_get_json(host: str, path: str) -> dict[str, object]:
    """GET a JSON resource over https.

    Uses http.client.HTTPSConnection rather than urllib.request.urlopen so
    the request is https-only by construction (no scheme from a variable, so
    ruff's S310 audit has nothing to flag).
    """
    conn = http.client.HTTPSConnection(host, timeout=30)
    try:
        conn.request(
            "GET",
            path,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "python-copier-template-maintenance",
            },
        )
        resp = conn.getresponse()
        return json.load(resp)
    finally:
        conn.close()


def github_latest_release(repo: str) -> str | None:
    """Return the latest release tag (e.g. v1.25.0) for a GitHub repo."""
    data = https_get_json("api.github.com", f"/repos/{repo}/releases/latest")
    return str(data["tag_name"])


def pypi_has_version(package: str, version: str) -> bool:
    """Return True if a package version exists on PyPI."""
    data = https_get_json("pypi.org", f"/pypi/{package}/json")
    releases = data.get("releases", {})
    assert isinstance(releases, dict)
    # PyPI stub releases look like "1.29.0.post1"; check any release whose
    # base version (before ".post") matches the firmware version.
    return any(rel.startswith(version) for rel in releases)


def extract_pins() -> list[Pin]:
    """Extract the pins from the template files (no network)."""
    # The single source of truth is the `micropython_version` internal
    # variable. The questionnaire lives in questions/*.yml fragments included
    # by copier.yml, so search both (the value must appear in exactly one).
    sources = [COPIER_YML, *QUESTIONS_DIR.glob("*.yml")]
    version = "?"
    for src in sources:
        ver_m = re.search(
            r"^micropython_version:\n    type: str\n    default: \"([^\"]+)\"",
            src.read_text(),
            re.MULTILINE,
        )
        if ver_m:
            version = ver_m.group(1)
            break
    pins: list[Pin] = [
        Pin(
            name="MicroPython version (copier.yml micropython_version)",
            current=version,
            checkable=True,
        ),
        Pin(
            name="micropython-<port>-stubs pin",
            current=f"~={version.removeprefix('v')} (community stubs)",
            checkable=True,
        ),
    ]

    # Every image reference in the PORT_INFO table, e.g. "espressif/idf:v5.4.2".
    freeze_src = FREEZE_TEMPLATE.read_text()
    seen: set[str] = set()
    for image in re.findall(r'"image": "([^"]+)"', freeze_src):
        if image not in seen:
            seen.add(image)
            pins.append(Pin(name=f"Docker image ({image})", current=image))

    return pins


def resolve_upstream(pins: list[Pin], *, offline: bool) -> None:
    """Fill in upstream values for the checkable pins."""
    for pin in pins:
        if not pin.checkable:
            continue
        if offline:
            pin.upstream = "?"
        elif pin.name.startswith("MicroPython version"):
            pin.upstream = github_latest_release("micropython/micropython")
        elif pin.name.startswith("micropython-<port>-stubs"):
            version = pin.current.split("~=")[1].split(" ")[0]
            pin.upstream = (
                "stub release exists" if pypi_has_version("micropython-esp32-stubs", version) else "NO STUB RELEASE"
            )


def report(pins: list[Pin]) -> int:
    drift = False
    for pin in pins:
        if not pin.checkable:
            print(f"[info]   {pin.name}: {pin.current}")
            continue
        if pin.upstream in (None, "?"):
            print(f"[info]   {pin.name}: {pin.current} (upstream unknown)")
            continue
        if pin.name.startswith("MicroPython version"):
            # Tag pin: exact match with the official latest release.
            if pin.current == pin.upstream:
                print(f"[ok]     {pin.name}: {pin.current}")
            else:
                print(
                    f"[DRIFT]  {pin.name}: {pin.current} -> official latest {pin.upstream}",
                )
                drift = True
        else:
            # Stub pin: report whether the pinned stub version exists.
            ok = pin.upstream == "stub release exists"
            if ok:
                print(f"[ok]     {pin.name}: {pin.current}")
            else:
                print(f"[DRIFT]  {pin.name}: {pin.current} ({pin.upstream})")
                drift = True
    print()
    if drift:
        print(
            "MicroPython pins are behind upstream. Bump micropython_version "
            "in copier.yml (it drives freeze.py's DEFAULT_TAG and the "
            "requirements-dev.txt stub pin together), then re-run the freeze "
            "smoke test.",
        )
        return 1
    print("MicroPython pins are up to date.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Report pins without hitting the network",
    )
    args = parser.parse_args()

    if not COPIER_YML.exists() or not FREEZE_TEMPLATE.exists():
        sys.exit("Template files not found; run from the repo root.")

    pins = extract_pins()
    resolve_upstream(pins, offline=args.offline)
    sys.exit(report(pins))


if __name__ == "__main__":
    main()
