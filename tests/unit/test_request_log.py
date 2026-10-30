"""One structured JSON log line per request (CLAUDE.md §8)."""

import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.request_log import LOGGER_NAME, JsonFormatter

H = {"X-User-Id": "alice"}
RELEASE = {"product": "P", "version": "1", "support_end_date": "2030-01-01"}


def make_lines(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [r.__dict__["fields"] for r in caplog.records if r.name == LOGGER_NAME]


@pytest.fixture(autouse=True)
def _capture(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)


def test_one_line_per_request_with_the_documented_fields(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.clear()
    r = client.post("/api/v1/releases", json=RELEASE, headers=H)
    [line] = make_lines(caplog)
    assert set(line) == {
        "request_id",
        "user_id",
        "method",
        "path",
        "status",
        "latency_ms",
        "clock",
        "clock_overridden",
    }
    assert re.fullmatch(r"[0-9a-f]{32}", line["request_id"])
    assert r.headers["X-Request-Id"] == line["request_id"]
    assert line["user_id"] == "alice"
    assert (line["method"], line["path"], line["status"]) == ("POST", "/api/v1/releases", 201)
    assert isinstance(line["latency_ms"], float) and line["latency_ms"] >= 0
    assert line["clock"].endswith("Z") and line["clock_overridden"] is False


def test_caller_request_id_is_kept(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.clear()
    r = client.get("/health", headers={"X-Request-Id": "team2-run-7.case-3"})
    assert r.headers["X-Request-Id"] == "team2-run-7.case-3"
    assert make_lines(caplog)[0]["request_id"] == "team2-run-7.case-3"


@pytest.mark.parametrize("bad", ["", "x" * 129, "has space", 'quote"'])
def test_unsafe_request_id_is_replaced(
    client: TestClient, caplog: pytest.LogCaptureFixture, bad: str
) -> None:
    caplog.clear()
    r = client.get("/health", headers={"X-Request-Id": bad})
    assert re.fullmatch(r"[0-9a-f]{32}", r.headers["X-Request-Id"])
    assert make_lines(caplog)[0]["request_id"] == r.headers["X-Request-Id"]


def test_overridden_clock_is_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    client.put("/api/v1/test/clock", json={"now": "2026-12-31T23:30:00+02:00"})
    caplog.clear()
    client.get("/api/v1/audit-logs")
    [line] = make_lines(caplog)
    assert line["clock"] == "2026-12-31T21:30:00Z" and line["clock_overridden"] is True
    assert line["user_id"] is None


def test_error_code_and_message_are_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.clear()
    r = client.post("/api/v1/releases", json={**RELEASE, "product": "  "}, headers=H)
    [line] = make_lines(caplog)
    assert line["status"] == 400 == r.status_code
    assert line["error_code"] == "INVALID_REQUEST"
    assert line["error_message"] == r.json()["error"]["message"] == "product must not be blank"


def test_long_error_message_is_truncated(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    app = create_app(Settings(db_path=str(tmp_path / "x.db")))

    @app.get("/boom-long")
    def boom_long() -> None:
        from app.errors import ApiError

        raise ApiError(400, "INVALID_REQUEST", "y" * 1000)

    caplog.clear()
    with TestClient(app) as c:
        c.get("/boom-long")
    assert make_lines(caplog)[0]["error_message"] == "y" * 300 + "..."


def test_unhandled_exception_is_logged_as_500(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    app: FastAPI = create_app(Settings(db_path=str(tmp_path / "x.db")))

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaput")

    caplog.clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/boom").status_code == 500
    [line] = make_lines(caplog)
    assert line["status"] == 500 and line["error_code"] == "RuntimeError"


def test_formatter_writes_the_line_with_the_wall_time() -> None:
    record = logging.LogRecord(LOGGER_NAME, logging.INFO, "", 0, "request", None, None)
    record.fields = {"status": 200}
    record.created = 1798761600.25  # 2027-01-01T00:00:00.25Z
    assert json.loads(JsonFormatter().format(record)) == {
        "time": "2027-01-01T00:00:00.250000Z",
        "status": 200,
    }
