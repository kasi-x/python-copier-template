#!/usr/bin/env python3
"""Check the vendored MANIFEST.yml against FLAGS.yml and REGISTRY.yml.

The codex declares each section's placement under an abstract `when`; this
template's FLAGS.yml maps that abstract condition to an audience token and a
gate expression, and REGISTRY.yml records which leaf classes actually carry
the section. This script is the offline consistency check between the three:
it fails when the manifest names a condition FLAGS.yml does not know, when a
section's declared audience disagrees with the registry's, or when a registry
row points at a section file the vendor did not ship.

Runs entirely on the vendored copies — no network, no render. It is the
consumer-side enforcement of the contract in docs/explanations/ethics-external.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

TOP = Path(__file__).resolve().parent.parent
ETHICS = TOP / "_shared" / "ethics"


def _load(name: str) -> dict:
    path = ETHICS / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> int:
    manifest = _load("MANIFEST.yml")
    flags = _load("FLAGS.yml")
    registry = _load("REGISTRY.yml")
    if not manifest or not flags or not registry:
        missing = [
            name
            for name, data in (("MANIFEST.yml", manifest), ("FLAGS.yml", flags), ("REGISTRY.yml", registry))
            if not data
        ]
        print(f"Missing or empty: {', '.join(missing)}", file=sys.stderr)
        return 2

    known_conditions = set(flags.get("conditions", {}))
    registry_by_file = {
        row["file"].split("_shared/ethics/")[-1]: row for row in registry.get("sections", []) if "file" in row
    }

    errors: list[str] = []
    for section in manifest.get("sections", []):
        sid = section.get("id", "?")
        when = section.get("when")
        if when not in known_conditions:
            errors.append(f"{sid}: abstract when {when!r} has no FLAGS.yml mapping (known: {sorted(known_conditions)})")
            continue
        declared = set(flags["conditions"][when].get("audience", []))
        row = registry_by_file.get(section.get("file", ""))
        if row is None:
            errors.append(f"{sid}: no REGISTRY.yml row for {section.get('file')}")
            continue
        actual = set(row.get("audience", []))
        if declared and actual and not (declared & actual):
            errors.append(
                f"{sid}: manifest when {when!r} resolves to audience {sorted(declared)} "
                f"but the registry row carries {sorted(actual)} — no overlap"
            )

    # Reverse direction: every active registry row must name a file the vendor ships.
    for rel, row in registry_by_file.items():
        if row.get("status") == "active" and not (ETHICS / rel).exists():
            errors.append(f"{row.get('id', rel)}: active but {rel} is not vendored")

    if errors:
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    print(
        f"ethics contract consistent: {len(manifest.get('sections', []))} sections, "
        f"{len(known_conditions)} conditions, {len(registry_by_file)} registry rows."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
