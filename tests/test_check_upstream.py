"""The upstream-pin checker's verdicts: a throttled lookup is not drift.

The weekly check walks ~20 endpoints from one runner IP, and the failure
that motivated this module was exactly that: one throttled PyPI response
made ``pypi_latest`` return None, ``_resolve_pypi_floor`` translated that
into "REMOVED", and the run filed a phantom "Template pins are behind
upstream" issue about a package that was alive the whole time. The
contract fixed here: only PyPI's own 404 may report a REMOVED floor, an
unresolved lookup reports a separate ``[warn]`` status that fails the run
without being drift, and the drift-issue step files only on ``[DRIFT]``.
"""

from __future__ import annotations

import http.client
import sys
import time
from pathlib import Path
from typing import Any
from typing import ClassVar

import pytest

TOP = Path(__file__).resolve().parent.parent
if str(TOP) not in sys.path:
    sys.path.insert(0, str(TOP))

from tools import check_upstream as cu  # noqa: E402


def _pin(upstream: str) -> cu.Pin:
    return cu.Pin(name="PyPI floor [mcp] mcp[cli]", current=">=2.0,<3", upstream=upstream, checkable=True)


def test_a_failed_lookup_reports_unresolved_never_removed(monkeypatch: pytest.MonkeyPatch):
    """A transient PyPI failure must not read as a removed package."""

    def _throttled(package: str) -> str:
        msg = f"GET https://pypi.org/pypi/{package}/json -> HTTP 429 (persistent after retries)"
        raise RuntimeError(msg)

    monkeypatch.setattr(cu, "pypi_latest", _throttled)
    # the contract under test is the checker's internal verdict strings
    status = cu._resolve_pypi_floor(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        "PyPI floor [mcp] mcp[cli]",
        ">=2.0,<3",
    )
    assert isinstance(status, str), "a lookup failure resolves to a status string, never None"
    assert "lookup failed" in status, f"a throttled lookup became a verdict: {status}"
    assert "REMOVED" not in status, "an unresolved lookup must not claim the package was removed"


def test_a_gone_package_still_reports_removed(monkeypatch: pytest.MonkeyPatch):
    """The real signal this must keep: PyPI itself saying the package is gone."""
    monkeypatch.setattr(cu, "pypi_latest", lambda package: None)
    status = cu._resolve_pypi_floor(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        "PyPI floor [mcp] mcp[cli]",
        ">=2.0,<3",
    )
    assert status == "REMOVED floor 2.0 matches no PyPI release"


def test_lookup_failure_is_warn_and_removal_is_drift():
    """The two statuses must land in different severity lanes."""
    warn_is_drift, warn_message = cu._is_drift(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        _pin("lookup failed (HTTP 429; re-run)")
    )
    removed_is_drift, removed_message = cu._is_drift(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        _pin("REMOVED floor 2.0 matches no PyPI release")
    )
    assert warn_is_drift and removed_is_drift, "both must fail the run"
    assert "[warn]" in warn_message and "[DRIFT]" not in warn_message, (
        "a warn must not carry the [DRIFT] marker the drift-issue step keys on"
    )
    assert "[DRIFT]" in removed_message, "a removed floor must stay a [DRIFT]"


def test_report_exits_nonzero_on_warn_without_claiming_drift(capsys: pytest.CaptureFixture[str]):
    """A warn-only report fails the run but states what kind of failure it is."""
    code = cu.report([_pin("lookup failed (HTTP 429; re-run)")])
    out = capsys.readouterr().out
    assert code == 1, "a run that could not check a pin must not report success"
    assert "lookups failed" in out and "[DRIFT]" not in out, "the message must name the failure kind"


class _FakeResponse:
    def __init__(self, status: int):
        self.status = status
        self.body = b"{}"

    def read(self) -> bytes:
        return self.body

    def getheader(self, name: str, default: str = "") -> str:
        _ = name
        return default


class _RecordingConnection:
    """Minimal HTTPSConnection double: 429, 429, 200 from one shared stream.

    The retries walk one request through three connections, so the response
    stream must survive the reconnects; every argument is recorded rather
    than ignored, which is what makes the double assertable.
    """

    responses: ClassVar[Any] = None
    requests: ClassVar[list[str]] = []

    def __init__(self, host: str, timeout: int) -> None:
        _RecordingConnection.requests.append(f"connect {host} {timeout}")

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        _RecordingConnection.requests.append(f"{method} {path} {sorted(headers)}")

    def getresponse(self) -> _FakeResponse:
        return next(_RecordingConnection.responses)

    def close(self) -> None:
        _RecordingConnection.requests.append("close")


def test_https_get_retries_a_throttled_response(monkeypatch: pytest.MonkeyPatch):
    """429/5xx are retried with a backoff, and the last attempt's verdict wins."""
    _RecordingConnection.responses = iter([_FakeResponse(429), _FakeResponse(429), _FakeResponse(200)])
    _RecordingConnection.requests = []
    sleeps: list[float] = []
    monkeypatch.setattr(http.client, "HTTPSConnection", _RecordingConnection)
    monkeypatch.setattr(time, "sleep", sleeps.append)

    status, body, _ = cu.https_get("pypi.org", "/pypi/mcp/json", attempts=3)

    assert (status, body) == (200, "{}"), "the third attempt must win"
    assert len(sleeps) == 2, f"two throttled responses, two backoffs: {sleeps}"
    assert _RecordingConnection.requests.count("close") == 3, "every connection is closed"
