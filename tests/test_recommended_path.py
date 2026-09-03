"""Smoke-test the recommended (fast) path of the questionnaire.

The heavy integration tests in test_example.py exercise the long tail: they
copy with example-answers.yml, which sets every `use_recommended_*` gate to
false so every detail question is asked. What they never render is the path a
real user actually takes -- accept every "use the recommended ...?" default
and only answer project_type + Project Details. Those fast paths are covered
here.

Rendering uses `skip_tasks=True`: copier's `_tasks` (the REUSE LICENSES/
copy, ...) need a checkout or external tools, and test_example.py
already runs them. This module only checks that the whole `template/` tree
survives jinja rendering for the fast path, without paying for uv sync/docs.
"""

from pathlib import Path

import pytest
from copier import run_copy

TOP = Path(__file__).absolute().parent.parent


# Answers shared by every case: the required "Project Details" plus values
# that keep generated content self-consistent (URLs, validators, ...).
BASE = {
    "package_name": "smoke_example",
    "description": "An example project",
    "git_platform": "github.com",
    "github_org": "kasi-x",
    "author_name": "kasi-x",
    "author_email": "kashimiya.exe@gmail.com",
    "repo_name": "smoke-example",
    "distribution_name": "smoke-example",
}

# One fast-path case per project_type reachable with every use_recommended_*
# gate at its default (true): accept the recommendation, answer only the
# required Project Details. data_science/ros2/micropython are reachable too but
# test_example.py's copy_project_recommended already renders those exact paths,
# so they are not repeated here.
FAST_PATHS: list[dict[str, object]] = [
    {"project_type": "library"},
    {"project_type": "web_api"},
    {"project_type": "script"},
]

# Artifacts unique to each project_type, to prove the fast path took the right
# layout branch instead of silently copying another one.
MARKERS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "library": (("src/smoke_example/__init__.py",), ("compose.local.yml", "smoke_example/__init__.py")),
    # docker is off on the fast path, so no compose file -- the web_api-only
    # tell is the postgres service in ci.yml (test_library_no_web_api_extras
    # asserts the library side of the same distinction).
    "web_api": (("src/smoke_example/__init__.py",), ("compose.local.yml", "smoke_example/__init__.py")),
    "script": (("smoke_example/__init__.py",), ("src", "compose.local.yml")),
}

# Content that must appear for each project_type (proves the branch, not just
# the shared layout). web_api's CI gets a postgres service; the others do not.
CONTENT: dict[str, tuple[tuple[str, str], ...]] = {
    "library": (),
    "web_api": ((".github/workflows/ci.yml", "postgres"),),
    "script": (),
}


def _id(answers: dict[str, object]) -> str:
    return "-".join(f"{k}={v}" for k, v in answers.items())


@pytest.mark.parametrize("answers", FAST_PATHS, ids=[_id(a) for a in FAST_PATHS])
def test_recommended_path_renders(tmp_path: Path, answers: dict[str, object]):
    run_copy(
        src_path=str(TOP),
        dst_path=tmp_path,
        data={**BASE, **answers},
        vcs_ref="HEAD",
        defaults=True,
        unsafe=True,
        overwrite=True,
        skip_tasks=True,  # REUSE-copy tasks need a checkout; jinja is what we test
    )
    project_type = str(answers["project_type"])
    expect, not_expect = MARKERS[project_type]
    for rel in expect:
        assert (tmp_path / rel).exists(), f"expected {rel} to be generated"
    for rel in not_expect:
        assert not (tmp_path / rel).exists(), f"expected {rel} NOT to be generated"
    for rel, needle in CONTENT[project_type]:
        assert needle in (tmp_path / rel).read_text(), f"expected {needle!r} in {rel}"
    # Copier strips the .jinja suffix when rendering a template, so any
    # leftover .jinja file means a branch was copied verbatim, unrendered
    # (a regression this template has actually hit: the .jinja suffix used to
    # leak into the output for flat-layout copies of __main__.py).
    leftovers = list(tmp_path.rglob("*.jinja"))
    assert leftovers == [], f"unrendered .jinja files left in {[str(p) for p in leftovers]}"


def test_recommended_path_ships_security_hardening(tmp_path: Path):
    """The recommended path (all gates true) ships the security defaults.

    SECURITY.md and the zizmor security workflow are part of the
    recommended settings; the OpenSSF Scorecard workflow is opt-in
    (public-repo only), so it must NOT appear on the fast path.
    """
    run_copy(
        src_path=str(TOP),
        dst_path=tmp_path,
        data={**BASE, "project_type": "library"},
        vcs_ref="HEAD",
        defaults=True,
        unsafe=True,
        overwrite=True,
        skip_tasks=True,
    )
    assert (tmp_path / "SECURITY.md").exists(), "recommended path should ship SECURITY.md"
    assert (tmp_path / ".github" / "workflows" / "security.yml").exists(), (
        "recommended path should ship the zizmor security workflow"
    )
    assert not (tmp_path / ".github" / "workflows" / "scorecard.yml").exists(), (
        "scorecard is opt-in and must not appear on the recommended path"
    )
    # The generated QA test (Aqua.jl spirit) ships with the test suite.
    assert (tmp_path / "tests" / "test_qa.py").exists()
    readme = (tmp_path / "README.md").read_text()
    assert "SECURITY.md" in readme, "README should link the security policy"
