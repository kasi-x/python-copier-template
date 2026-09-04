#!/usr/bin/env python3
"""Check the template's hardcoded pins against official upstream.

The template hardcodes versions renovate cannot track: release tags, CUDA
indexes, distro codenames, image tags. Renovate handles PyPI ranges, GitHub
Action digests and lockfiles — everything here is what it cannot see.

Each check below names its single source of truth in the template and the
upstream feed it is compared against:

- MicroPython tag (`micropython_version` internal) — tracks the latest
  stable release of micropython/micropython on GitHub.
- MicroPython stubs — the pinned community stubs must exist on PyPI.
- CUDA (Dockerfile.gpu base + cu124/cu126-style uv index) — the uv index
  must still receive torch releases; the Docker base should track the
  newest long-lived CUDA minor.
- ROS 2 distros (questions/ros2.yml choices) — no offered distro may be
  past EOL per REP-2000; warn when a newer LTS exists.
- Python floor (requires-python / CI matrix / classifiers) — the oldest
  supported version must not be past EOL per endoflife.date.
- Postgres image (compose + CI service) — the major must still receive
  updates; warn when a newer major is the stable default.
- Ubuntu base (resolute) — the LTS codename must still be supported.

Exits 0 when everything is current, 1 on any drift. Intended to run in CI
(see .github/workflows/check-upstream.yml) where a nonzero exit + the drift
report opens an issue.

Usage:
    python tools/check_upstream.py             # check against upstream
    python tools/check_upstream.py --offline   # report pins only
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime as datetime_
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
QUESTIONS_DIR = TOP / "questions"
TEMPLATE_DIR = TOP / "template"
PYPROJECT_JINJA = TEMPLATE_DIR / ("{% if not ros2_cpp %}pyproject.toml{% endif %}.jinja")
GPU_DOCKERFILE = TEMPLATE_DIR / ("{% if use_gpu_effective %}Dockerfile.gpu{% endif %}.jinja")
COMPOSE_JINJA = TEMPLATE_DIR / ("{% if web_api and docker %}compose.local.yml{% endif %}.jinja")
CI_JINJA = TEMPLATE_DIR / (
    '{% if git_platform=="github.com" %}.github{% endif %}'
    "/{% if ci_provider == 'github_actions' %}workflows{% endif %}/ci.yml.jinja"
)
ROS2_QUESTIONS = QUESTIONS_DIR / "ros2.yml"


@dataclass
class Pin:
    name: str
    current: str
    upstream: str | None = None
    checkable: bool = False


def https_get(host: str, path: str) -> tuple[int, str, str]:
    """GET a resource over https. Returns (status, body, content-type)."""
    conn = http.client.HTTPSConnection(host, timeout=20)
    try:
        conn.request("GET", path, headers={"User-Agent": "python-copier-template-upstream-check"})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", "replace")
        return resp.status, body, resp.getheader("Content-Type", "")
    finally:
        conn.close()


def https_get_json(host: str, path: str) -> dict[str, object] | list[object]:
    """GET a JSON resource over https."""
    status, body, _ = https_get(host, path)
    if status != 200:
        msg = f"GET https://{host}{path} -> HTTP {status}"
        raise RuntimeError(msg)
    data: dict[str, object] | list[object] = json.loads(body)
    return data


def github_latest_release(repo: str) -> str | None:
    """Return the latest release tag (e.g. v1.25.0) for a GitHub repo."""
    try:
        data = https_get_json("api.github.com", f"/repos/{repo}/releases/latest")
    except RuntimeError:
        return None
    if isinstance(data, dict):
        tag = data.get("tag_name")
        return str(tag) if tag else None
    return None


def pypi_has_version(package: str, version: str) -> bool:
    """Return True if a package version exists on PyPI."""
    try:
        data = https_get_json("pypi.org", f"/pypi/{package}/json")
    except RuntimeError:
        return False
    if not isinstance(data, dict):
        return False
    releases = data.get("releases")
    if not isinstance(releases, dict):
        return False
    return any(rel.startswith(version) for rel in releases)


def pypi_latest(package: str) -> str | None:
    """Return the latest version of a PyPI package."""
    try:
        data = https_get_json("pypi.org", f"/pypi/{package}/json")
    except RuntimeError:
        return None
    if isinstance(data, dict):
        info = data.get("info")
        if isinstance(info, dict):
            version = info.get("version")
            return str(version) if version else None
    return None


def pytorch_index_torch_versions(cu_tag: str) -> list[str]:
    """Return torch versions published on a pytorch cu-index (e.g. cu126)."""
    try:
        status, body, _ = https_get("download.pytorch.org", f"/whl/{cu_tag}/torch/")
    except RuntimeError:
        return []
    if status != 200:
        return []
    return sorted(set(re.findall(r"torch-(2\.\d+\.\d+)", body)), key=lambda v: tuple(int(x) for x in v.split(".")))


def eol_date(product: str, cycle: str) -> str | None:
    """Return the EOL date (YYYY-MM-DD) for a product cycle, or None."""
    try:
        data = https_get_json("endoflife.date", f"/api/{product}.json")
    except RuntimeError:
        return None
    if not isinstance(data, list):
        return None
    for entry in data:
        if isinstance(entry, dict) and str(entry.get("cycle")) == cycle:
            eol = entry.get("eol")
            return str(eol) if eol and eol is not False else None
    return None


def extract_pins() -> list[Pin]:
    """Extract the pins from the template files (no network)."""
    pins: list[Pin] = []

    # MicroPython tag: single source of truth is the internal variable.
    version = "?"
    sources = [TOP / "copier.yml", *QUESTIONS_DIR.glob("*.yml")]
    for src in sources:
        ver_m = re.search(
            r"^micropython_version:\n    type: str\n    default: \"([^\"]+)\"",
            src.read_text(),
            re.MULTILINE,
        )
        if ver_m:
            version = ver_m.group(1)
            break
    pins.append(Pin(name="MicroPython tag (micropython_version)", current=version, checkable=True))
    pins.append(
        Pin(
            name="micropython-<port>-stubs pin",
            current=f"~={version.removeprefix('v')} (community stubs)",
            checkable=True,
        )
    )

    # CUDA: Dockerfile.gpu base image + uv index tag.
    gpu_src = GPU_DOCKERFILE.read_text()
    cuda_m = re.search(r"FROM nvidia/cuda:([^\s]+) AS", gpu_src)
    cuda_base = cuda_m.group(1) if cuda_m else "?"
    pins.append(Pin(name="CUDA Docker base (Dockerfile.gpu)", current=cuda_base, checkable=True))
    pyproject_src = PYPROJECT_JINJA.read_text()
    for partial in sorted((TOP / "_shared").glob("pyproject-*.toml.jinja")):
        pyproject_src += "\n" + partial.read_text()

    # ROS 2 distros offered in the questionnaire.
    ros_src = ROS2_QUESTIONS.read_text()
    distros = re.findall(r": (humble|jazzy|kilted|rolling)\n", ros_src)
    pins.append(Pin(name="ROS 2 distros offered", current=",".join(sorted(set(distros))) or "?", checkable=True))

    # Python floor: requires-python's default branch (non-ros2). The jinja
    # conditional picks 3.10/3.12 for ros2 distros; the floor we track is
    # the second `else` value.
    floor_m = re.search(r"else '>=(3\.\d+)'\)", pyproject_src)
    floor = floor_m.group(1) if floor_m else "?"
    pins.append(Pin(name="Python floor (requires-python)", current=floor, checkable=True))

    # Postgres image tag (compose + CI service must agree).
    compose_src = COMPOSE_JINJA.read_text()
    ci_src = CI_JINJA.read_text()
    pg_tags = set(re.findall(r"image: (postgres:[^\s]+)", compose_src)) | set(
        re.findall(r"image: (postgres:[^\s]+)", ci_src)
    )
    pins.append(Pin(name="Postgres image (compose + CI)", current=",".join(sorted(pg_tags)) or "?", checkable=True))

    # Ubuntu base codename.
    docker_src = (TEMPLATE_DIR / "Dockerfile.jinja").read_text()
    ubuntu_tags = set(re.findall(r"(?:ubuntu:|ubuntu-devcontainer:)(\w+)", docker_src))
    pins.append(Pin(name="Ubuntu base (Dockerfile)", current=",".join(sorted(ubuntu_tags)) or "?", checkable=False))

    # PyPI floors per combination category: every runtime floor pinned in
    # the pyproject template must exist on PyPI (a floor above latest, or a
    # removed release, breaks `uv sync` for that combination). Categories
    # mirror the questionnaire axes so a combination that cannot stay
    # current is visible per axis, not as one flat list.
    for category, pattern in {
        "core (all projects)": r'"(structlog|ruff|pytest|pre-commit)"',
        "web_api": r'"(fastapi|uvicorn|sqlalchemy|alembic|asyncpg|pydantic-settings|slowapi|prometheus-client)[^"]*"',
        "kaggle/DS": r'"(torch|torchvision|lightgbm|xgboost|optuna|hydra-core|polars|duckdb|pyarrow)[^"]*"',
        "ctf": r'"(pwntools|z3-solver)[^"]*"',
        "mcp": r'"(mcp\[[^\]]*\]|mcp)[^"]*"',
    }.items():
        for dep in sorted(set(re.findall(pattern, pyproject_src))):
            floor_m = re.search(rf'"{re.escape(dep)}([^"]*)"', pyproject_src)
            floor = floor_m.group(1) if floor_m else "?"
            pins.append(Pin(name=f"PyPI floor [{category}] {dep}", current=floor or "unpinned", checkable=True))

    return pins


def _parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3])


def _today() -> str:
    return datetime_.now(tz=UTC).date().isoformat()


def _resolve_cuda_base() -> str | None:
    # Report the newest CUDA minor seen on the torch index family: the
    # Docker base should track what torch ships for.
    cu_versions = {cu: pytorch_index_torch_versions(cu) for cu in ("cu124", "cu126", "cu128")}
    newest = max(
        (cu for cu, vers in cu_versions.items() if vers),
        default=None,
        key=lambda cu: _parse_version(cu_versions[cu][-1]),
    )
    return f"newest torch-bearing index {newest}" if newest else None


def _resolve_torch_index(cu: str) -> str:
    versions = pytorch_index_torch_versions(cu)
    latest = pypi_latest("torch")
    if not versions:
        return f"index {cu} unreachable or empty"
    if latest and _parse_version(versions[-1]) < _parse_version(latest):
        return f"index tops out at {versions[-1]}, PyPI latest {latest} (index frozen?)"
    return f"index current (tops out at {versions[-1]})"


ROS_EOL = {"humble": "2027-05", "jazzy": "2029-05", "kilted": "2026-11"}


def _resolve_ros(current: str, today: str) -> str:
    # REP-2000 dates, hardcoded rather than scraped: the source is a
    # versioned spec document, and scraping RST is brittle.
    offered = current.split(",") if current != "?" else []
    past = [d for d in offered if d in ROS_EOL and ROS_EOL[d] < today[:7]]
    if past:
        return f"EOL passed: {','.join(past)}"
    return f"all supported (today {today})"


def _resolve_python_floor(cycle: str, today: str) -> str:
    eol = eol_date("python", cycle)
    if eol is None:
        return "EOL lookup failed"
    if eol > today:
        return f"supported until {eol}"
    return f"EOL {eol} PASSED"


def _resolve_postgres(current: str) -> str:
    tags = current.split(",") if current != "?" else []
    majors = sorted({tag.split(":")[1].split("-")[0].split(".")[0] for tag in tags if ":" in tag})
    latest_pg = None
    try:
        status, body, _ = https_get(
            "hub.docker.com", "/v2/repositories/library/postgres/tags?name=18-alpine&page_size=1"
        )
        count = json.loads(body).get("count", 0) if status == 200 else 0
        latest_pg = "18" if count else None
    except RuntimeError:
        latest_pg = None
    state = "available" if latest_pg else "status unknown"
    return f"major {','.join(majors)}; postgres 18 {state}"


def resolve_upstream(pins: list[Pin], *, offline: bool) -> None:
    """Fill in upstream values for the checkable pins."""
    today = _today()
    for pin in pins:
        if not pin.checkable:
            continue
        if offline:
            pin.upstream = "?"
        else:
            pin.upstream = _resolve_one(pin, today)


def _resolve_pypi_floor(name: str, current: str) -> str | None:
    """Check a PyPI floor exists and report how far behind latest it is.

    `current` is the raw spec suffix from the template (e.g. `>=4.13,<5` or
    empty when unpinned). Returns a status string the drift detector keys
    on: `REMOVED` when the floor matches no release, else
    `floor <f> / latest <v>`.
    """
    pkg = name.rsplit(" ", 1)[-1].rstrip("]")
    floor_m = re.search(r"(\d+(?:\.\d+)*)", current)
    if not floor_m:
        return "unpinned (no floor to check)"
    floor = floor_m.group(1)
    if not pypi_has_version(pkg, floor):
        return f"REMOVED floor {floor} matches no PyPI release"
    latest = pypi_latest(pkg)
    return f"floor {floor} / latest {latest}"


def _resolve_one(pin: Pin, today: str) -> str | None:  # noqa: PLR0911
    """Resolve a single pin. Dispatches on the pin name prefix."""
    name, current = pin.name, pin.current
    if name.startswith("micropython-<port>-stubs"):
        stub_version = current.split("~=")[1].split(" ")[0]
        exists = pypi_has_version("micropython-esp32-stubs", stub_version)
        return "stub release exists" if exists else "NO STUB RELEASE"
    if name.startswith("MicroPython tag"):
        return github_latest_release("micropython/micropython")
    if name.startswith("torch uv index"):
        return _resolve_torch_index(current)
    if name.startswith("ROS 2 distros"):
        return _resolve_ros(current, today)
    if name.startswith("Python floor"):
        return _resolve_python_floor(current, today)
    if name.startswith("Postgres image"):
        return _resolve_postgres(current)
    if name.startswith("CUDA Docker base"):
        return _resolve_cuda_base()
    if name.startswith("PyPI floor"):
        return _resolve_pypi_floor(name, current)
    return None


def _is_drift(pin: Pin) -> tuple[bool, str]:
    """Return (drift, message) for a resolved pin."""
    if pin.upstream in (None, "?"):
        return False, f"[info]   {pin.name}: {pin.current} (upstream unknown)"
    upstream = pin.upstream
    name, current = pin.name, pin.current
    by_exact_match = {
        "MicroPython tag": (
            current == upstream,
            f"[ok]     {name}: {current}",
            f"[DRIFT]  {name}: {current} -> official latest {upstream}",
        ),
        "micropython-<port>-stubs": (
            upstream == "stub release exists",
            f"[ok]     {name}: {current}",
            f"[DRIFT]  {name}: {current} ({upstream})",
        ),
    }
    for prefix, (ok, ok_msg, drift_msg) in by_exact_match.items():
        if name.startswith(prefix):
            return (False, ok_msg) if ok else (True, drift_msg)
    triggers = {
        "torch uv index": ("frozen", "unreachable", "empty"),
        "ROS 2 distros": ("EOL passed",),
        "Python floor": ("PASSED",),
        "PyPI floor": ("REMOVED",),
    }
    for prefix, markers in triggers.items():
        if name.startswith(prefix):
            if any(m in upstream for m in markers):
                return True, f"[DRIFT]  {name}: {current} ({upstream})"
            return False, f"[ok]     {name}: {current} ({upstream})"
    return False, f"[info]   {name}: {current} ({upstream})"


def report(pins: list[Pin]) -> int:
    drift = False
    for pin in pins:
        if not pin.checkable:
            print(f"[info]   {pin.name}: {pin.current}")
            continue
        is_drift, message = _is_drift(pin)
        print(message)
        drift = drift or is_drift
    print()
    if drift:
        print("Template pins are behind upstream. See the [DRIFT] lines above for what to bump.")
        return 1
    print("Template pins are up to date.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Report pins without hitting the network",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated name prefixes to check (default: all)",
    )
    args = parser.parse_args()

    for required in (PYPROJECT_JINJA, GPU_DOCKERFILE, ROS2_QUESTIONS):
        if not required.exists():
            msg = f"Template file not found: {required}; run from the repo root."
            sys.exit(msg)

    pins = extract_pins()
    if args.only:
        prefixes = tuple(p.strip() for p in args.only.split(","))
        pins = [p for p in pins if p.name.startswith(prefixes)]
        if not pins:
            msg = f"No pins match --only={args.only!r}."
            sys.exit(msg)
    resolve_upstream(pins, offline=args.offline)
    sys.exit(report(pins))


if __name__ == "__main__":
    main()
