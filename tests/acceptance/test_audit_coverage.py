"""Every state-changing operation writes exactly one audit event (REQ-08; CLAUDE.md §6.6).

WRITE_ACTIONS is the inventory in docs/audit-immutability.md. A new POST/PUT/PATCH/DELETE outside
the test endpoints fails test_every_write_operation_is_in_the_inventory until it's added here.
"""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

H = {"X-User-Id": "auditor"}
SBOM = (Path("fixtures") / "sbom_25_components.json").read_bytes()

WRITE_ACTIONS = {
    ("post", "/api/v1/releases"): ("RELEASE_REGISTERED", "release"),
    ("put", "/api/v1/releases/{releaseId}/sbom"): ("SBOM_STORED", "release"),
    ("post", "/api/v1/incidents"): ("INCIDENT_CREATED", "incident"),
    ("patch", "/api/v1/incidents/{incidentId}"): ("FIX_AVAILABLE_RECORDED", "incident"),
    ("post", "/api/v1/incidents/{incidentId}/submissions"): ("SUBMISSION_RECORDED", "incident"),
    ("put", "/api/v1/incidents/{incidentId}/report-data/{stage}"): (
        "REPORT_DATA_STORED",
        "incident",
    ),
}
# Always 405: they exist to say the audit log can't be changed.
REFUSED = {("patch", "/api/v1/audit-logs/{eventId}"), ("delete", "/api/v1/audit-logs/{eventId}")}


def events(client: TestClient) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = client.get("/api/v1/audit-logs").json()["events"]
    return result


def test_every_write_operation_is_in_the_inventory(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    writes = {
        (method, path)
        for path, item in paths.items()
        for method in item
        if method in ("post", "put", "patch", "delete")
        and not path.startswith(("/api/v1/test", "/test"))
    }
    assert writes - REFUSED == set(WRITE_ACTIONS)
    assert REFUSED <= writes


def test_each_write_operation_writes_one_matching_event(client: TestClient) -> None:
    def expect(key: tuple[str, str], response: Any, entity_id: str | None = None) -> str:
        assert response.status_code in (200, 201), response.text
        log = events(client)
        assert len(log) == len(seen) + 1, key
        action, entity_type = WRITE_ACTIONS[key]
        last = log[-1]
        assert (last["action"], last["entity_type"], last["user_id"]) == (
            action,
            entity_type,
            "auditor",
        )
        if entity_id is not None:
            assert last["entity_id"] == entity_id
        seen.append(key)
        return str(last["entity_id"])

    seen: list[tuple[str, str]] = []
    release = {"product": "p", "version": "1", "support_end_date": "2030-01-01"}
    rid = expect(
        ("post", "/api/v1/releases"), client.post("/api/v1/releases", json=release, headers=H)
    )
    expect(
        ("put", "/api/v1/releases/{releaseId}/sbom"),
        client.put(
            f"/api/v1/releases/{rid}/sbom",
            content=SBOM,
            headers={**H, "Content-Type": "application/json"},
        ),
        rid,
    )
    incident = {
        "awareness_at": "2026-11-01T10:00:00Z",
        "classification": "mandatory",
        "rationale": "r",
    }
    iid = expect(
        ("post", "/api/v1/incidents"), client.post("/api/v1/incidents", json=incident, headers=H)
    )
    expect(
        ("patch", "/api/v1/incidents/{incidentId}"),
        client.patch(
            f"/api/v1/incidents/{iid}", json={"fix_available_at": "2026-11-05T00:00:00Z"}, headers=H
        ),
        iid,
    )
    expect(
        ("post", "/api/v1/incidents/{incidentId}/submissions"),
        client.post(
            f"/api/v1/incidents/{iid}/submissions",
            json={"stage": "early_warning", "submitted_at": "2026-11-02T09:00:00Z"},
            headers=H,
        ),
        iid,
    )
    expect(
        ("put", "/api/v1/incidents/{incidentId}/report-data/{stage}"),
        client.put(
            f"/api/v1/incidents/{iid}/report-data/early_warning",
            json={"member_states": ["DE"]},
            headers=H,
        ),
        iid,
    )
    assert set(seen) == set(WRITE_ACTIONS)
