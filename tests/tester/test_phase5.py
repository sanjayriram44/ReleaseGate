"""The Phase 5 tester checks (AC-08, AC-09) against our system and against faulty targets."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tester.checks import Fixtures, Report, run

FIXTURES = Fixtures.load(Path("fixtures"))
Mutate = Callable[[httpx.Request, Any], Any]


def system(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(Settings(db_path=str(tmp_path / "s.db"), enable_test_endpoints=True))
    )


def faulty(tmp_path: Path, mutate: Mutate) -> httpx.Client:
    """Our system, with JSON responses rewritten by mutate(request, body)."""
    inner = system(tmp_path)

    def handle(request: httpx.Request) -> httpx.Response:
        resp = inner.request(
            request.method, request.url.path, content=request.content, headers=request.headers
        )
        try:
            body = resp.json()
        except ValueError:
            return httpx.Response(resp.status_code, content=resp.content)
        return httpx.Response(resp.status_code, json=mutate(request, body))

    return httpx.Client(base_url="http://faulty", transport=httpx.MockTransport(handle))


def phase5(report: Report) -> dict[str, Any]:
    return {c.id: c for c in report.checks if c.ac in ("AC-08", "AC-09")}


def failed(report: Report, required: bool) -> set[str]:
    return {c.id for c in report.checks if c.required is required and not c.passed}


def test_our_system_passes_every_phase5_check(tmp_path: Path) -> None:
    report = run(system(tmp_path), FIXTURES, "http://testserver")
    checks = phase5(report)
    assert report.error is None and report.result == "pass"
    assert [cid for cid, c in checks.items() if not c.passed] == []
    for cid in (
        "ac08.complete.early_warning.missing",
        "ac08.incomplete.vulnerability_notification.missing",
        "ac08.unknown_incident.get",
        "ac09.four_events",
        "ac09.order",
        "ac09.timestamps",
        "ac09.rejected_adds_nothing",
        "ac09.immutable",
    ):
        assert checks[cid].required, cid
    for cid in ("ac08.put_body", "ac08.invalid_stage.get", "ac09.actions"):
        assert not any(k.endswith(cid.split(".", 1)[1]) and v.required for k, v in checks.items())
    assert len([c for c in checks.values() if c.ac == "AC-08" and c.required]) >= 25
    assert set(report.operations) >= {
        "PUT /api/v1/incidents/{incidentId}/report-data/{stage}",
        "GET /api/v1/incidents/{incidentId}/reports/{stage}",
    }


def test_wrong_missing_fields_fail_ac08(tmp_path: Path) -> None:
    def drop_one(request: httpx.Request, body: Any) -> Any:
        if request.method == "GET" and "/reports/vulnerability_notification" in request.url.path:
            body["missing_fields"] = body.get("missing_fields", [])[1:]
        return body

    report = run(faulty(tmp_path, drop_one), FIXTURES, "http://faulty")
    assert "ac08.incomplete.vulnerability_notification.missing" in failed(report, required=True)
    assert "ac08.complete.vulnerability_notification.missing" not in failed(report, required=True)


def test_rewritten_report_text_fails_ac08(tmp_path: Path) -> None:
    def trim(request: httpx.Request, body: Any) -> Any:
        if request.method == "GET" and "/reports/final_report" in request.url.path:
            body["data"] = {k: v.upper() for k, v in body.get("data", {}).items()}
        return body

    report = run(faulty(tmp_path, trim), FIXTURES, "http://faulty")
    assert "ac08.complete.final_report.data" in failed(report, required=True)


def test_audit_timestamps_off_the_clock_fail_ac09(tmp_path: Path) -> None:
    def shift(request: httpx.Request, body: Any) -> Any:
        if request.url.path == "/api/v1/audit-logs":
            for e in body.get("events", []):
                e["timestamp"] = "2030-01-01T00:00:00Z"
        return body

    report = run(faulty(tmp_path, shift), FIXTURES, "http://faulty")
    assert "ac09.timestamps" in failed(report, required=True)


def test_other_action_names_are_only_informational(tmp_path: Path) -> None:
    def rename(request: httpx.Request, body: Any) -> Any:
        if request.url.path == "/api/v1/audit-logs":
            for e in body.get("events", []):
                e["action"] = e["action"].lower()
        return body

    report = run(faulty(tmp_path, rename), FIXTURES, "http://faulty")
    assert "ac09.actions" in failed(report, required=False)
    assert not {c for c in failed(report, required=True) if c.startswith("ac09")}


def test_report_fixture_is_loaded_for_the_tester() -> None:
    raw = json.loads(Path("fixtures/report_cases.json").read_text())
    assert FIXTURES.reports == raw
