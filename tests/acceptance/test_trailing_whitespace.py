"""A timestamp, date or CVE ID with trailing whitespace is invalid: 400, nothing stored.

Team 2's 2026-11-02 run found five cases where a trailing "\\n" was accepted, because Python's "$"
matches before a final newline (CLAUDE.md §4 item 1, P5-Q9).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

H = {"X-User-Id": "alice"}
NOW = "2026-11-01T12:00:00Z"
SUFFIXES = ["\n", "\r\n", " "]


def events(client: TestClient) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = client.get("/api/v1/audit-logs").json()["events"]
    return result


def assert_invalid(response: Any) -> None:
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def make_incident(client: TestClient, **overrides: Any) -> Any:
    body = {
        "cve_id": "CVE-2023-25577",
        "awareness_at": "2026-11-01T10:00:00Z",
        "classification": "mandatory",
        "rationale": "Actively exploited in the field; vendor confirmed.",
        **overrides,
    }
    return client.post("/api/v1/incidents", json=body, headers=H)


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_clock_now(client: TestClient, suffix: str) -> None:
    assert client.put("/api/v1/test/clock", json={"now": NOW}).status_code == 200
    assert_invalid(client.put("/api/v1/test/clock", json={"now": "2026-11-05T00:00:00Z" + suffix}))
    # The clock kept its value: the next audited write is stamped with it.
    r = client.post(
        "/api/v1/releases",
        json={"product": "p", "version": "1", "support_end_date": "2030-01-01"},
        headers=H,
    )
    assert r.status_code == 201
    assert events(client)[-1]["timestamp"] == NOW


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_support_end_date(client: TestClient, suffix: str) -> None:
    body = {"product": "p", "version": "1", "support_end_date": "2030-01-01" + suffix}
    assert_invalid(client.post("/api/v1/releases", json=body, headers=H))
    assert events(client) == []


@pytest.mark.parametrize("field", ["awareness_at", "cve_id"])
@pytest.mark.parametrize("suffix", SUFFIXES)
def test_incident_fields(client: TestClient, field: str, suffix: str) -> None:
    value = {"awareness_at": "2026-11-01T10:00:00Z", "cve_id": "CVE-2023-25577"}[field]
    assert_invalid(make_incident(client, **{field: value + suffix}))
    assert events(client) == []


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_fix_available_at(client: TestClient, suffix: str) -> None:
    iid = make_incident(client).json()["incident_id"]
    before = events(client)
    r = client.patch(
        f"/api/v1/incidents/{iid}",
        json={"fix_available_at": "2026-11-05T00:00:00Z" + suffix},
        headers=H,
    )
    assert_invalid(r)
    assert events(client) == before
    assert client.get(f"/api/v1/incidents/{iid}").json()["fix_available_at"] is None


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_submitted_at(client: TestClient, suffix: str) -> None:
    iid = make_incident(client).json()["incident_id"]
    before = events(client)
    r = client.post(
        f"/api/v1/incidents/{iid}/submissions",
        json={"stage": "early_warning", "submitted_at": "2026-11-02T09:00:00Z" + suffix},
        headers=H,
    )
    assert_invalid(r)
    assert events(client) == before
    deadline = client.get(f"/api/v1/incidents/{iid}").json()["deadlines"]["early_warning"]
    assert deadline["submitted_at"] is None


@pytest.mark.parametrize("suffix", ["%0A", "%0D%0A", "%20"])
def test_cve_query_path(client: TestClient, suffix: str) -> None:
    r = client.get(f"/api/v1/vulnerabilities/CVE-2023-25577{suffix}/affected-releases")
    assert_invalid(r)
