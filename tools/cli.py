#!/usr/bin/env python3
"""One command to create a project from this template.

`python-copier-template new <dir>` asks `tools/detect.py` what the target is
and dispatches to the tool that does the right thing for it:

What it does is decided by the mode `tools/detect.py` reports:

- `fresh` (missing or empty directory): one copier render of this checkout,
  `--trust` included.
- `adopt` (an existing project): `tools/adopt.py`'s transaction -- collisions
  are skipped, the files you already have are verified byte-for-byte, and the
  run rolls back if any of them changed.
- `update` (this template already generated it): refuses; `copier update` is
  the right verb.
- `foreign` (another copier template owns it): refuses, exit 3.

`--ref` defaults to this fork's newest release tag; `tools/adopt.py:resolve_ref`
returns the default branch (with the reason) only when that tag carries a
different questionnaire, so the fork's older upstream tags cannot leak in.
`--preset NAME` reads `presets/NAME.yml` as the answers file and makes the run
non-interactive -- every question the preset does not answer keeps its copier
default, which is what keeps each preset a one-family file. Without a preset
the questionnaire is the interface: copier asks it, which needs a terminal.

The CLI never edits a file the target already has: an adoption runs with the
merge step off (use `tools/adopt.py --merge` when you want the template's
dependencies and runner recipes added to your own files).

Usage::

    python -m tools.cli new my-project --preset library
    python-copier-template new /path/to/existing-project --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

import copier
import copier.errors
import yaml

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import adopt  # noqa: E402
from tools import batch  # noqa: E402
from tools import detect  # noqa: E402

PRESETS = TOP / "presets"

# Exit codes, the same contract as the tools this dispatches to: 0 ok,
# 1 failed, 2 invalid request, 3 refused (another template owns the target).
OK = 0
FAILED = 1
INVALID = 2
REFUSED = 3

# Collisions to name before the warning starts summarising them.
COLLISION_LIMIT = 12


class RequestError(Exception):
    """The request cannot be carried out as asked."""


def available_presets() -> list[str]:
    """The names `--preset` accepts: the answer files under `presets/`."""
    return sorted(path.stem for path in PRESETS.glob("*.yml"))


def preset_answers(name: str) -> dict[str, Any]:
    """The answers mapping of `presets/<name>.yml`.

    Only the questions that define the family are in there; the rest of the
    questionnaire keeps the default copier would use for a non-interactive
    run.
    """
    path = PRESETS / f"{name}.yml"
    if not path.is_file():
        known = ", ".join(available_presets()) or "(none)"
        msg = f"unknown preset {name!r}: no presets/{name}.yml. Available presets: {known}"
        raise RequestError(msg)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        msg = f"{path} is not an answers mapping"
        raise RequestError(msg)
    return loaded


def collision_warning(collisions: list[str]) -> str:
    """The one-line warning for files both the target and the template have."""
    named = ", ".join(collisions[:COLLISION_LIMIT])
    if len(collisions) > COLLISION_LIMIT:
        named += f", ... (+{len(collisions) - COLLISION_LIMIT} more)"
    return f"warning: {len(collisions)} existing file(s) the template also ships will be left alone: {named}"


def _render(target: Path, data: dict[str, Any], ref: str, *, defaults: bool) -> None:
    """Render this checkout into `target`, the way `tools/batch.py:render` does.

    The flags are that convention's (`unsafe` is copier's `--trust`); the one
    difference is `defaults`, which batch.render pins to True. A `--preset` run
    is fully specified, so it keeps copier's defaults for every question the
    preset leaves out; without a preset the questionnaire is the interface, and
    copier asks it (which needs a terminal).
    """
    with batch.report_stream_only():
        copier.run_copy(
            src_path=str(TOP),
            dst_path=target,
            data=data,
            vcs_ref=ref,
            unsafe=True,
            defaults=defaults,
            overwrite=True,
            quiet=True,
        )


def _fresh(
    target: Path,
    data: dict[str, Any],
    ref: str | None,
    *,
    dry_run: bool,
    defaults: bool,
) -> int:
    """Render this checkout into an empty (or not yet created) directory."""
    resolved, reason = adopt.resolve_ref(ref)
    if dry_run:
        print("dry run -- nothing written")
        print("mode:    fresh")
        print(f"ref:     {resolved}  ({reason})")
        print(f"target:  {target}")
        print("answers: " + ", ".join(f"{key}={value}" for key, value in sorted(data.items())))
        source = adopt.render_fresh_source(data, resolved)
        try:
            planned = sorted(str(path.relative_to(source)) for path in source.rglob("*") if path.is_file())
        finally:
            shutil.rmtree(source, ignore_errors=True)
        top = sorted({path.split("/")[0] for path in planned})
        print(f"would create {len(planned)} file(s); top level: {', '.join(top)}")
        return OK
    try:
        _render(target, data, resolved, defaults=defaults)
    except copier.errors.InteractiveSessionError as exc:
        msg = f"{exc}; pass --preset <name> for a non-interactive run"
        print(msg, file=sys.stderr)
        return INVALID
    except Exception as exc:  # noqa: BLE001  WHYNOT: copier's failure is reported, not re-raised.
        print(f"render failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return FAILED
    created = sorted(path for path in target.rglob("*") if path.is_file())
    top = sorted({str(path.relative_to(target)).split("/")[0] for path in created})
    print("mode:    fresh")
    print(f"target:  {target}")
    print(f"ref:     {resolved}  ({reason})")
    print(f"created: {len(created)} file(s); top level: {', '.join(top)}")
    return OK


def _adopt(target: Path, answers: dict[str, Any], ref: str | None, *, dry_run: bool) -> int:
    """Adopt into an existing project through `tools/adopt.py`'s transaction."""
    try:
        adoption = adopt.adopt(target, ref=ref, answers=answers, dry_run=dry_run, merge_generated=False)
    except adopt.OwnershipError as exc:
        print(str(exc), file=sys.stderr)
        return REFUSED
    except (adopt.AdoptError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return INVALID
    print(adopt.render_report(adoption))
    return OK if adoption.ok or adoption.error is None else FAILED


def new(target: Path, *, preset: str | None, ref: str | None, dry_run: bool) -> int:
    """Create (`fresh`) or adopt into (`adopt`) `target`, and report the mode."""
    try:
        answers = preset_answers(preset) if preset else {}
    except RequestError as exc:
        print(str(exc), file=sys.stderr)
        return INVALID
    target = target.resolve()
    try:
        detection = detect.detect(target)
    except (detect.DetectError, OSError) as exc:
        print(f"cannot inspect {target}: {exc}", file=sys.stderr)
        return INVALID
    if detection.mode == "foreign":
        print(detect.render_report(detection), file=sys.stderr)
        return REFUSED
    if detection.mode == "update":
        msg = (
            f"{target} was generated from this template: update it with `copier update`"
            " (or tools/adopt.py), not with a second copy"
        )
        print(msg, file=sys.stderr)
        return INVALID
    if detection.collisions:
        print(collision_warning(detection.collisions), file=sys.stderr)
    if detection.mode == "adopt":
        return _adopt(target, answers, ref, dry_run=dry_run)
    # Fresh mode derives `existing_project: false` (and nothing else) from the
    # filesystem; the preset, when there is one, overrides what it names.
    return _fresh(target, {**detection.suggested_answers, **answers}, ref, dry_run=dry_run, defaults=preset is not None)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python-copier-template",
        description="Create a project from this template: detect the mode, then render or adopt.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    new_command = subcommands.add_parser("new", help="create a project, or adopt into an existing one")
    new_command.add_argument("dir", type=Path, help="directory to create or adopt into")
    new_command.add_argument(
        "--preset",
        default=None,
        help=f"answers family under presets/ ({', '.join(available_presets())}); implies a non-interactive run",
    )
    new_command.add_argument(
        "--ref", default=None, help="template revision to expand (default: this fork's newest release tag)"
    )
    new_command.add_argument("--dry-run", action="store_true", help="plan only; write nothing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: dispatch on the mode `tools/detect.py` reports."""
    args = _parse_args(argv)
    return new(args.dir, preset=args.preset, ref=args.ref, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
