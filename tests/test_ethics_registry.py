"""Registry guard for the ethics/regional/operational sections.

_shared/ethics/REGISTRY.yml is the single source for accumulated rule
sections (region/sector/domain). Until a section graduates to a genre
(questions/ + witness leaf) it stays draft and no template/ file may
include it (leaf +0). These tests hold the registry's contract: row
shape, header agreement, draft isolation, and the denylist the first
section exists for.
"""

import re
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
