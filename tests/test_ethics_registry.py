"""Registry guard for the ethics/regional/operational sections.

_shared/ethics/REGISTRY.yml is the single source for accumulated rule
sections (region/sector/domain). Until a section graduates to a genre
(questions/ + witness leaf) it stays draft and no template/ file may
include it (leaf +0). These tests hold the registry's contract: row
shape, header agreement, draft isolation, and the denylist the first
section exists for.
"""

import re
import sys
from datetime import UTC
from datetime import date
from datetime import datetime
from pathlib import Path

import yaml

TOP = Path(__file__).resolve().parent.parent
ETHICS = TOP / "_shared" / "ethics"
REGISTRY = ETHICS / "REGISTRY.yml"

VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.\d+$")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEADER_RE = re.compile(r"\{#\s*ethics:\s*id=(\S+)\s+version=(\S+)\s+status=(\S+)")
TRIGGER_SPAN_RE = re.compile(r"`((?:\(\?i\))[^`]+)`")


def _load_registry():
    """The registry rows (version 1, non-empty section list)."""
    payload = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    assert payload.get("version") == 1, "registry version must be 1"
    sections = payload.get("sections")
    assert isinstance(sections, list) and sections, "sections must be a non-empty list"
    return sections


def _datestr(value: object) -> str | None:
    """A registry date (YAML parses unquoted dates) as an ISO string."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _read(path: Path) -> str:
    """File text, tolerating nothing: non-files read as empty."""
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def test_registry_rows_are_well_formed():
    """Every row names its rule, version, sources, scope and lifecycle state."""
    required = {
        "id",
        "file",
        "version",
        "effective",
        "review_by",
        "sources",
        "scale",
        "audience",
        "enforcement",
        "status",
        "rendered_from",
        "superseded_by",
    }
    ids = []
    for row in _load_registry():
        assert required <= set(row), f"{row.get('id')}: missing keys {sorted(required - set(row))}"
        assert ID_RE.fullmatch(str(row["id"])), f"bad id {row['id']!r}"
        ids.append(str(row["id"]))
        assert VERSION_RE.fullmatch(str(row["version"])), f"{row['id']}: bad version {row['version']!r}"
        assert str(row["file"]).startswith("_shared/ethics/"), f"{row['id']}: must live under _shared/ethics/"
        assert (TOP / str(row["file"])).is_file(), f"{row['id']}: missing file {row['file']}"
        effective, review_by = _datestr(row["effective"]), _datestr(row["review_by"])
        assert review_by is not None and re.fullmatch(r"\d{4}-\d{2}-\d{2}", review_by), f"{row['id']}: bad review_by"
        if effective is not None:
            assert review_by > effective, f"{row['id']}: review_by must be after effective"
        sources = row["sources"]
        assert isinstance(sources, list) and sources, f"{row['id']}: sources must be non-empty"
        assert set(row["scope"]) == {"jurisdiction", "sector", "category"}, f"{row['id']}: bad scope keys"
        assert row["scale"] in {"domestic", "regional", "global"}, f"{row['id']}: bad scale"
        audience = row["audience"]
        assert isinstance(audience, list) and audience, f"{row['id']}: audience must be non-empty"
        assert all(ID_RE.fullmatch(str(entry)) for entry in audience), f"{row['id']}: bad audience entry"
        assert row["enforcement"] in {"L0", "L1", "L2"}, f"{row['id']}: bad enforcement"
        assert row["status"] in {"draft", "active", "kind"}, f"{row['id']}: bad status"
        if row["status"] == "draft":
            assert row["rendered_from"] == [], f"{row['id']}: draft must render from nowhere"
        else:
            assert row["rendered_from"], f"{row['id']}: distributed rows must name their parents"
    assert len(set(ids)) == len(ids), f"duplicate section ids: {ids}"


def test_section_headers_agree_with_registry():
    """The file header repeats its row (id/version/status/review date)."""
    for row in _load_registry():
        text = (TOP / str(row["file"])).read_text(encoding="utf-8")
        match = HEADER_RE.search("\n".join(text.splitlines()[:4]))
        assert match, f"{row['id']}: must open with a {{# ethics: id=.. version=.. status=.. #}} header"
        section_id, version, status = match.groups()
        assert section_id == row["id"], f"header id {section_id!r} != row {row['id']!r}"
        assert version == str(row["version"]), f"{row['id']}: header version drifted from the row"
        assert status == row["status"], f"{row['id']}: header status drifted from the row"
        review = _datestr(row["review_by"])
        assert review is not None and review in text, f"{row['id']}: body must repeat the row's review_by"


def test_section_bodies_repeat_scale_and_audience():
    """The body states its scale line and audience so humans and LLMs route it."""
    scale_ja = {"domestic": "国内問題", "regional": "地域問題", "global": "世界問題"}
    for row in _load_registry():
        text = (TOP / str(row["file"])).read_text(encoding="utf-8")
        assert scale_ja[str(row["scale"])] in text, f"{row['id']}: body must name its scale"
        for entry in row["audience"]:
            assert str(entry) in text.lower(), f"{row['id']}: body must name audience {entry!r}"


def _consumer_files():
    """Every file that could include a section: template/ + tasks + _shared/."""
    files = [path for path in (TOP / "template").rglob("*") if path.is_file()]
    tasks = TOP / "_tasks.jinja"
    if tasks.is_file():
        files.append(tasks)
    files += [path for path in (TOP / "_shared").rglob("*.jinja") if path.name != "_template.md.jinja"]
    return files


def test_draft_sections_are_not_distributed():
    """A draft section is documentation only: nothing includes it (leaf +0)."""
    for row in _load_registry():
        if row["status"] != "draft":
            continue
        text = _read(TOP / str(row["file"]))
        assert "{{" not in text, f"{row['id']}: draft sections take no copier context"
        offenders = [
            str(path.relative_to(TOP))
            for path in _consumer_files()
            if path != TOP / str(row["file"]) and str(row["file"]) in _read(path)
        ]
        assert not offenders, f"{row['id']} is draft but included from: {offenders}"


def test_distributed_sections_are_included_by_their_parents():
    """The mirror of the draft check: an active/kind row's parents include it.

    `rendered_from` is the row's claim about who renders the section; this
    holds each named parent to it, so a promotion PR cannot name a parent it
    did not wire (and a refactor cannot silently drop the include).
    """
    for row in _load_registry():
        if row["status"] == "draft":
            continue
        assert row["rendered_from"], f"{row['id']}: a distributed row must name its parents"
        for parent in row["rendered_from"]:
            path = TOP / str(parent)
            assert path.is_file(), f"{row['id']}: rendered_from names a missing parent {parent!r}"
            assert str(row["file"]) in _read(path), (
                f"{row['id']}: parent {parent!r} does not reference the section file"
            )


def test_every_row_documents_a_parseable_presence_trigger():
    """The 設定側トリガー span is the row's machine-readable half.

    tools/ethics.py's `match()` (the MCP `check_ethics` tool) scans text with
    exactly this span; a row that stops documenting it in the parseable shape
    would silently vanish from every match result, so the loader's parse is
    pinned here for all rows, drafts included. The trigger detects English
    code vocabulary (a Japanese title cannot carry it), so the only honest
    pins are: it compiles, it is case-insensitive, and no two rows share one.
    """
    sys.path.insert(0, str(TOP))
    from tools import ethics  # noqa: PLC0415

    triggers = [ethics.presence_trigger(row) for row in _load_registry()]
    for row, trigger in zip(_load_registry(), triggers, strict=True):
        re.compile(trigger)
        assert trigger.startswith("(?i)"), f"{row['id']}: the presence trigger must be case-insensitive"
    assert len(set(triggers)) == len(triggers), (
        "two rows sharing one presence trigger would be indistinguishable to check_ethics"
    )


def test_copyright_terms_table_matches_its_section():
    """The lang/ table is the structured half of baseline-copyright-ai.

    `lang/` is reserved for the translation-style dictionaries the section
    prose keeps out of AGENTS.md: the protection-term differences a
    public-domain checker must consult. The pin holds the table to the
    section it serves -- same review_by as the registry row, every
    jurisdiction carrying rules plus its own primary sources, and the
    wartime extension the section's prose names present as data, so the
    section can claim "法域差" without the checker's inputs living only in
    a paragraph.
    """
    rows = [row for row in _load_registry() if row["id"] == "baseline-copyright-ai"]
    assert rows, "the copyright-ai section must stay registered"
    review_by = _datestr(rows[0]["review_by"])
    table_path = ETHICS / "lang" / "copyright-terms.yml"
    assert table_path.is_file(), "the copyright-terms table must live under _shared/ethics/lang/"
    payload = yaml.safe_load(table_path.read_text(encoding="utf-8"))
    assert payload.get("version") == 1, "table version must be 1"
    assert payload.get("serves") == "baseline-copyright-ai", "table must name the section it serves"
    assert _datestr(payload.get("review_by")) == review_by, (
        "the table's review_by must match the baseline-copyright-ai row"
    )
    terms = payload.get("terms")
    assert isinstance(terms, dict) and terms, "terms must be a non-empty mapping"
    for jurisdiction, entry in terms.items():
        assert ID_RE.fullmatch(jurisdiction), f"bad jurisdiction id {jurisdiction!r}"
        for key in ("individual", "corporate", "notes", "sources"):
            assert key in entry, f"{jurisdiction}: missing key {key!r}"
        assert entry["individual"] and entry["corporate"], f"{jurisdiction}: term rules must be non-empty"
        assert isinstance(entry["notes"], list) and entry["notes"], f"{jurisdiction}: notes must be non-empty"
        sources = entry["sources"]
        assert isinstance(sources, list) and sources, f"{jurisdiction}: sources must be non-empty"
        assert all(str(url).startswith("https://") for url in sources), f"{jurisdiction}: sources must be https URLs"
    jp = terms.get("jp")
    assert jp is not None and "戦時加算" in "".join(jp["notes"]), (
        "jp must carry the wartime extension as data, not only in the section prose"
    )
    section_text = (TOP / str(rows[0]["file"])).read_text(encoding="utf-8")
    assert "lang/copyright-terms.yml" in section_text, (
        "the section must point at the table so the two cannot drift apart silently"
    )


def test_python_examples_are_ruff_format_clean(tmp_path: Path):
    """A section's ```python blocks survive the generated project's `task check`.

    ruff 0.16+ formats Python code blocks inside markdown files, and the
    section bodies render into the generated AGENTS.md — so an example
    whose style is off fails `ruff format --check` for every project kind
    that ships the section. The examples are checked under both generated
    widths (allow_japanese's 88 and 120). A "bad" example is bad
    semantically (verify=False, a missing scrub), never stylistically.
    """
    import subprocess  # noqa: PLC0415

    blocks: list[tuple[str, int, str]] = []
    for row in _load_registry():
        text = (TOP / str(row["file"])).read_text(encoding="utf-8")
        for index, span in enumerate(re.findall(r"```python\n(.*?)```", text, re.DOTALL)):
            blocks.append((str(row["id"]), index, span))
    assert blocks, "no python examples found: the sections lost their concrete examples"

    for line_length in (88, 120):
        for section_id, index, code in blocks:
            example = tmp_path / f"{section_id}-{index}.py"
            example.write_text(code, encoding="utf-8")
            proc = subprocess.run(  # noqa: S603
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "format",
                    "--check",
                    "--no-cache",
                    f"--line-length={line_length}",
                    str(example),
                ],
                capture_output=True,
                text=True,
            )
            assert proc.returncode == 0, (
                f"{section_id} example {index} is not ruff-format-clean at width {line_length}:\n"
                f"{proc.stdout}{proc.stderr}"
            )


def test_no_review_date_has_passed():
    """A section whose review_by is in the past is overdue, loudly.

    Every row's 制度変更ウォッチ names the date its primary sources must be
    re-checked by (the watch items are the section's half-life: OWASP
    editions rotate, CA chains rotate, statutes move). Nothing else in the
    repo surfaces a passed date -- the MCP inventory carries review_by but
    nobody is required to read it -- so this pin is the reminder: the fast
    tier runs on every push and the scheduled test run, so an overdue
    section reddens CI until someone re-checks the sources and bumps
    review_by (or supersedes the row). Reviewers other than the maintainer
    can do the re-check; the bump itself is a versioned registry edit.
    """
    today = datetime.now(tz=UTC).date()
    overdue = []
    for row in _load_registry():
        review_by = _datestr(row["review_by"])
        if review_by is not None and review_by < today.isoformat():
            overdue.append(f"{row['id']}: review_by {review_by}")
    assert not overdue, (
        "the following sections' review_by dates have passed -- re-check each "
        "section's primary sources, update the body, and bump the row's version "
        "and review_by (or supersede the row):\n  " + "\n  ".join(overdue)
    )


def test_kyushu_ntp_denylist_and_detector():
    """The first section names the retired identifiers and ships a detector."""
    rows = [row for row in _load_registry() if row["id"] == "region-kyushu-ntp"]
    assert rows, "the kyushu-ntp sample section must stay registered"
    text = (TOP / str(rows[0]["file"])).read_text(encoding="utf-8")
    for identifier in ("133.100.9.2", "133.100.11.8", "clock.nc.fukuoka-u.ac.jp"):
        assert identifier in text, f"retired identifier {identifier} must be named"
    spans = TRIGGER_SPAN_RE.findall(text)
    assert spans, "the section must document its T1 trigger regex"
    hit_topic = hit_retired = False
    for span in spans:
        pattern = re.compile(span)
        hit_topic |= bool(pattern.search("chrony"))
        hit_retired |= bool(pattern.search("server 133.100.9.2"))
    assert hit_topic and hit_retired, f"no documented trigger matches both a topic and a retired id: {spans}"
