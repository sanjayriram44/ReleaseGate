"""Lowercase "t" and "z" are accepted in every timestamp field and come back as "T" and "Z".

RFC 3339 §5.6 allows them and the contract's `format: date-time` is RFC 3339. Team 2's
2026-11-02 run had four failures here (CLAUDE.md §4 item 2, P5-Q9).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

H = {"X-User-Id": "alice"}


def make_incident(client: TestClient, awareness_at: str = "2026-11-01T10:00:00Z") -> Any:
    body = {
        "cve_id": "CVE-2023-25577",
        "awareness_at": awareness_at,
        "classification": "mandatory",
        "rationale": "Actively exploited in the field; vendor confirmed.",
    }
    return client.post("/api/v1/incidents", json=body, headers=H)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-01t23:59:59z", "2026-11-01T23:59:59Z"),
        ("2026-11-01t23:59:59+02:00", "2026-11-01T21:59:59Z"),
    ],
)
def test_clock_now(client: TestClient, value: str, expected: str) -> None:
    r = client.put("/api/v1/test/clock", json={"now": value})
    assert r.status_code == 200 and r.json() == {"now": expected}


def test_awareness_at(client: TestClient) -> None:
    r = make_incident(client, "2026-11-01t10:00:00z")
    assert r.status_code == 201
    assert r.json()["awareness_at"] == "2026-11-01T10:00:00Z"
    assert r.json()["deadlines"]["early_warning"]["deadline_at"] == "2026-11-02T10:00:00Z"


def test_fix_available_at(client: TestClient) -> None:
    iid = make_incident(client).json()["incident_id"]
    r = client.patch(
        f"/api/v1/incidents/{iid}", json={"fix_available_at": "2026-11-05t00:00:00z"}, headers=H
    )
    assert r.status_code == 200 and r.json()["fix_available_at"] == "2026-11-05T00:00:00Z"


def test_submitted_at(client: TestClient) -> None:
    iid = make_incident(client).json()["incident_id"]
    r = client.post(
        f"/api/v1/incidents/{iid}/submissions",
        json={"stage": "early_warning", "submitted_at": "2026-11-02t09:00:00.5+01:00"},
        headers=H,
    )
    assert r.status_code == 201
    deadline = client.get(f"/api/v1/incidents/{iid}").json()["deadlines"]["early_warning"]
    assert deadline["submitted_at"] == "2026-11-02T08:00:00.500000Z"


def test_lowercase_t_without_a_zone_is_still_400(client: TestClient) -> None:
    r = make_incident(client, "2026-11-01t10:00:00")
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"
