"""AC-09 (REQ-08): the audit log records each state change, in order, and can't be changed.

CLAUDE.md §6.8. Action names follow the proposed vocabulary (P5-Q7, provisional). The
code-inspection half of AC-09 is docs/audit-immutability.md and
tests/unit/test_audit_immutability.py.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

START = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
SBOM = (Path("fixtures") / "sbom_25_components.json").read_bytes()


def stamp(minutes: int) -> str:
    return (START + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_clock(client: TestClient, now: str) -> None:
    assert client.put("/api/v1/test/clock", json={"now": now}).status_code == 200


def events(client: TestClient) -> list[dict[str, Any]]:
    r = client.get("/api/v1/audit-logs")
    assert r.status_code == 200
    result: list[dict[str, Any]] = r.json()["events"]
    return result


def run_ac09_steps(client: TestClient) -> tuple[str, str]:
    """Reset, then four state changes one minute apart by four users, with a rejected request
    between the third and the fourth. Returns (release_id, incident_id)."""
    assert client.post("/api/v1/test/reset").status_code == 204
    set_clock(client, stamp(1))
    r = client.post(
        "/api/v1/releases",
        json={"product": "ExampleGateway", "version": "1.1.0", "support_end_date": "2030-01-01"},
        headers={"X-User-Id": "user-1"},
    )
    assert r.status_code == 201
    rid = str(r.json()["release_id"])

    set_clock(client, stamp(2))
    r = client.put(
        f"/api/v1/releases/{rid}/sbom",
        content=SBOM,
        headers={"X-User-Id": "user-2", "Content-Type": "application/json"},
    )
    assert r.status_code == 200

    set_clock(client, stamp(3))
    incident = {
        "cve_id": "CVE-2023-25577",
        "awareness_at": stamp(3),
        "classification": "mandatory",
        "rationale": "Exploitation reported by a customer.",
    }
    r = client.post("/api/v1/incidents", json=incident, headers={"X-User-Id": "user-3"})
    assert r.status_code == 201
    iid = str(r.json()["incident_id"])

    # Rejected: no rationale. Must add no event.
    rejected = {k: v for k, v in incident.items() if k != "rationale"}
    r = client.post("/api/v1/incidents", json=rejected, headers={"X-User-Id": "user-x"})
    assert r.status_code == 400

    set_clock(client, stamp(4))
    r = client.post(
        f"/api/v1/incidents/{iid}/submissions",
        json={"stage": "early_warning", "submitted_at": stamp(4)},
        headers={"X-User-Id": "user-4"},
    )
    assert r.status_code == 201
    return rid, iid


def test_ac09_four_events_in_order_with_user_entity_and_clock_time(client: TestClient) -> None:
    rid, iid = run_ac09_steps(client)
    log = events(client)
    got = [
        (e["action"], e["user_id"], e["entity_type"], e["entity_id"], e["timestamp"]) for e in log
    ]
    assert got == [
        ("RELEASE_REGISTERED", "user-1", "release", rid, stamp(1)),
        ("SBOM_STORED", "user-2", "release", rid, stamp(2)),
        ("INCIDENT_CREATED", "user-3", "incident", iid, stamp(3)),
        ("SUBMISSION_RECORDED", "user-4", "incident", iid, stamp(4)),
    ]
    assert len({e["event_id"] for e in log}) == 4


def test_ac09_events_cannot_be_changed_or_deleted(client: TestClient) -> None:
    run_ac09_steps(client)
    before = events(client)
    for event in before:
        url = f"/api/v1/audit-logs/{event['event_id']}"
        r = client.patch(url, json={"user_id": "mallory"}, headers={"X-User-Id": "mallory"})
        assert r.status_code == 405
        assert client.delete(url, headers={"X-User-Id": "mallory"}).status_code == 405
    assert events(client) == before


def test_ac09_reads_and_test_endpoints_write_no_events(client: TestClient) -> None:
    rid, iid = run_ac09_steps(client)
    before = events(client)
    client.get(f"/api/v1/releases/{rid}")
    client.get(f"/api/v1/releases/{rid}/components")
    client.get(f"/api/v1/incidents/{iid}")
    client.get(f"/api/v1/incidents/{iid}/reports/early_warning")
    set_clock(client, stamp(10))
    client.put("/api/v1/test/vulnerability-source", json={"mode": "available", "records": []})
    assert events(client) == before


def test_ac09_report_data_is_audited_too(client: TestClient) -> None:
    _, iid = run_ac09_steps(client)
    set_clock(client, stamp(5))
    r = client.put(
        f"/api/v1/incidents/{iid}/report-data/early_warning",
        json={"member_states": ["DE"]},
        headers={"X-User-Id": "user-5"},
    )
    assert r.status_code == 200
    last = events(client)[-1]
    assert (last["action"], last["user_id"], last["entity_id"], last["timestamp"]) == (
        "REPORT_DATA_STORED",
        "user-5",
        iid,
        stamp(5),
    )
