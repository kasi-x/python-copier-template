"""Render each preset into dist/<preset>/ — the static distribution.

The questionnaire's *ask-time* questions (partial questions, shared
fragments) are necessarily dynamic: copier still asks them locally when a
user runs `copier copy`. But the *result* for a preset — pyproject.toml and
the whole generated tree — is static: the same answers always produce the
same bytes. This script renders presets/<name>.yml for every preset and
writes the result under `dist/<name>/`.

The dist/ tree is the minimal deliverable, published two ways:

  - the `dist` branch (`.github/workflows/_dist_branch.yml` pushes dist/'s
    contents to it on every main push): `git clone -b dist` or
    `bootstrap.sh` fetches a preset and rewrites the few knobs that vary
    locally — names, and the log library (variants/ carries a
    logging_setup.py per preset per library, rendered the same way).
  - release assets (`.github/workflows/_static.yml`, tag pushes).

Consumers who want the full questionnaire render locally from
questions/*.yml via copier — the same render path, so it cannot drift from
what was distributed.

`--preset NAME` limits the run (useful for the edit loop);
`--check` re-renders and fails if a committed dist/ is stale.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
PRESETS = TOP / "presets"
DIST = TOP / "dist"
BOOTSTRAP = TOP / "architekton" / "bootstrap.sh"

if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))
from architekton import batch  # noqa: E402
from architekton.answers import BASE  # noqa: E402
from architekton.answers import preset_names  # noqa: E402
from architekton.answers import read_preset  # noqa: E402

# The local-rewrite knobs bootstrap.sh exposes: today just log_library.
LOG_LIBS = ["loguru", "picologging", "logging"]  # structlog is the rendered default

DIST_README = """\
# dist

Every directory here is a complete, rendered project — the flat output of
the architekton-py template for that preset. Copy the directory you want,
or run:

    curl -fsSL https://raw.githubusercontent.com/politeuma/architekton-py/dist/bootstrap.sh | bash

`bootstrap.sh` asks four questions (preset / names / log library), fetches
the preset tree, and rewrites those locally. `index.json` lists each
preset's files; `variants/` carries per-preset variants (e.g.
logging_setup.py for each logging library).

These trees are regenerated from `main` on every push by CI; do not commit
here. To re-render from scratch instead of fetching, use copier against the
`main` branch — `bootstrap.sh` runs that same render's output.
"""


def render_preset(name: str, dst: Path, extra: dict | None = None) -> None:
    """One preset -> one rendered project under dst."""
    answers = {**BASE, **read_preset(name), **(extra or {})}
    batch.render(
        str(TOP),
        dst,
        answers,
        "HEAD",
        skip_tasks=True,  # tasks print/prompt; the file side effects are tested separately
    )


def render_log_variants(names: list[str], dist: Path) -> None:
    """variants/logging_setup/<preset>/<lib>.py for presets that ship the file.

    bootstrap.sh swaps this file plus the pyproject dependency when the user
    picks a log library other than structlog. Rendered per preset so
    web_api's app/ layout and pkg_layout's src/ layout both resolve — the
    file's target path is found in the preset tree, not derived here.
    """
    out_root = dist / "variants" / "logging_setup"
    for name in names:
        preset_tree = dist / name
        if not any(preset_tree.rglob("logging_setup.py")):
            continue
        for lib in LOG_LIBS:
            with tempfile.TemporaryDirectory() as tmp:
                render_preset(name, Path(tmp) / name, {"log_library": lib})
                rendered = next((Path(tmp) / name).rglob("logging_setup.py"), None)
                if rendered:
                    dst = out_root / name / f"{lib}.py"
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(rendered, dst)


def manifest(dist: Path) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for preset in sorted(p for p in dist.iterdir() if p.is_dir() and p.name != "variants"):
        files = sorted(str(p.relative_to(preset)) for p in preset.rglob("*") if p.is_file())
        out[preset.name] = {"files": files}
    return out


def validate(dist: Path) -> list[str]:
    """Every rendered pyproject.toml must parse — the smoke test."""
    errors = []
    for pyproject in dist.rglob("pyproject.toml"):
        try:
            tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"{pyproject}: {exc}")
    return errors


def build(names: list[str], dist: Path) -> Path:
    dist.mkdir(parents=True, exist_ok=True)
    for name in names:
        dst = dist / name
        shutil.rmtree(dst, ignore_errors=True)
        print(f"render {name} -> {dst}")
        render_preset(name, dst)
    print("render log_library variants")
    render_log_variants(names, dist)
    (dist / "bootstrap.sh").write_text(BOOTSTRAP.read_text(encoding="utf-8"), encoding="utf-8")
    (dist / "README.md").write_text(DIST_README, encoding="utf-8")
    index = manifest(dist)
    (dist / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    errors = validate(dist)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"{sum(len(v['files']) for v in index.values())} files across {len(index)} presets")
    return dist


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", action="append", default=[], help="render only this preset (repeatable)")
    parser.add_argument("--out", type=Path, default=DIST)
    parser.add_argument("--check", action="store_true", help="re-render and fail if dist/ is stale")
    args = parser.parse_args(argv)

    names = args.preset or preset_names(PRESETS)
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = build(names, Path(tmp) / "dist")
            for name in names:
                a, b = fresh / name, DIST / name
                if not b.exists():
                    print(f"stale: dist/{name} missing; run gen_static.py", file=sys.stderr)
                    return 1
                # Version-stamped metadata is not drift (it names the commit
                # that rendered it); index.json is rebuilt wholesale.
                ignore = {"index.json", ".copier-answers.yml", ".architekton-manifest.yml"}
                a_files = {p.relative_to(a) for p in a.rglob("*") if p.is_file() and p.name not in ignore}
                b_files = {p.relative_to(b) for p in b.rglob("*") if p.is_file() and p.name not in ignore}
                if a_files != b_files or any((a / f).read_bytes() != (b / f).read_bytes() for f in a_files):
                    print(f"stale: dist/{name}; run gen_static.py", file=sys.stderr)
                    return 1
            for extra in ("bootstrap.sh", "README.md"):
                if (fresh / extra).read_bytes() != (DIST / extra).read_bytes():
                    print(f"stale: dist/{extra}; run gen_static.py", file=sys.stderr)
                    return 1
            a_var = {p.relative_to(fresh) for p in fresh.rglob("*") if p.is_file() and "variants" in p.parts}
            b_var = {p.relative_to(DIST) for p in DIST.rglob("*") if p.is_file() and "variants" in p.parts}
            if a_var != b_var or any((fresh / f).read_bytes() != (DIST / f).read_bytes() for f in a_var):
                print("stale: dist/variants; run gen_static.py", file=sys.stderr)
                return 1
            print("dist/ is in sync")
            return 0
    build(names, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
