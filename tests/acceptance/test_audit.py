import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.sbom_helpers import make_sbom, raw

H = {"X-User-Id": "alice"}


def events(client: TestClient) -> list[dict[str, Any]]:
    r = client.get("/api/v1/audit-logs")
    assert r.status_code == 200
    return list(r.json()["events"])


def reg(client: TestClient, version: str = "1.0", user: str = "alice") -> str:
    r = client.post(
        "/api/v1/releases",
        json={"product": "R", "version": version, "support_end_date": "2030-01-01"},
        headers={"X-User-Id": user},
    )
    return str(r.json()["release_id"])


def put(client: TestClient, rid: str, body: bytes, user: str = "alice") -> Any:
    return client.put(
        f"/api/v1/releases/{rid}/sbom",
        content=body,
        headers={"X-User-Id": user, "Content-Type": "application/json"},
    )


def test_empty_log(client: TestClient) -> None:
    assert events(client) == []


def test_each_state_change_writes_one_event_with_user(client: TestClient) -> None:
    client.put("/api/v1/test/clock", json={"now": "2026-06-15T12:00:00Z"})
    rid = reg(client, user="alice")
    put(client, rid, raw(make_sbom(2)), user="bob")
    put(client, rid, raw(make_sbom(3)), user="carol")
    evs = events(client)
    assert [(e["action"], e["user_id"]) for e in evs] == [
        ("RELEASE_REGISTERED", "alice"),
        ("SBOM_STORED", "bob"),
        ("SBOM_REPLACED", "carol"),
    ]
    assert all(e["entity_type"] == "release" and e["entity_id"] == rid for e in evs)
    assert all(e["timestamp"] == "2026-06-15T12:00:00Z" for e in evs)
    assert evs[1]["details"] == {"component_count": 2}
    assert evs[2]["details"] == {"component_count": 3}
    assert len({e["event_id"] for e in evs}) == 3


def test_failed_requests_write_no_events(client: TestClient) -> None:
    rid = reg(client)
    assert len(events(client)) == 1
    client.post("/api/v1/releases", json={"product": "R"}, headers=H)  # 400
    dup = {"product": "R", "version": "1.0", "support_end_date": "2030-01-01"}
    assert client.post("/api/v1/releases", json=dup, headers=H).status_code == 409
    put(client, rid, b"garbage")  # 400
    put(client, "rel-nope", raw(make_sbom(1)))  # 404
    client.post(
        "/api/v1/releases", json={"product": "x", "version": "1", "support_end_date": "2030-01-01"}
    )
    assert len(events(client)) == 1


def test_empty_sbom_then_replace_is_replaced(client: TestClient) -> None:
    rid = reg(client)
    doc = make_sbom(0)
    del doc["components"]
    put(client, rid, raw(doc))
    put(client, rid, raw(make_sbom(1)))
    assert [e["action"] for e in events(client)][1:] == ["SBOM_STORED", "SBOM_REPLACED"]


def test_patch_and_delete_are_405(client: TestClient) -> None:
    reg(client)
    eid = events(client)[0]["event_id"]
    for method in ("patch", "delete"):
        r = getattr(client, method)(f"/api/v1/audit-logs/{eid}", headers=H)
        assert r.status_code == 405
        assert r.json()["error"]["code"] == "AUDIT_IMMUTABLE"
    assert len(events(client)) == 1


def test_rejected_ac01_case_writes_no_audit_event(client: TestClient) -> None:
    spec = json.loads(Path("fixtures/releases.json").read_text())
    client.put("/api/v1/test/clock", json={"now": spec["reference_clock"]})
    for case in spec["ac01"]["cases"]:
        client.post("/api/v1/releases", json=case["request"], headers=H)
    entities = [e["details"]["version"] for e in events(client)]
    assert "4.0.0" not in entities and len(entities) == 3
