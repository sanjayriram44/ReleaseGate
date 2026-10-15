import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.sbom_helpers import make_sbom, raw

H = {"X-User-Id": "alice"}


def seed(client: TestClient) -> str:
    client.put("/api/v1/test/clock", json={"now": "2020-01-01T00:00:00Z"})
    rid = client.post(
        "/api/v1/releases",
        json={"product": "R", "version": "1", "support_end_date": "2030-01-01"},
        headers=H,
    ).json()["release_id"]
    client.put(
        f"/api/v1/releases/{rid}/sbom",
        content=raw(make_sbom(3)),
        headers={**H, "Content-Type": "application/json"},
    )
    return str(rid)


def test_reset_clears_everything_including_audit(client: TestClient) -> None:
    rid = seed(client)
    assert len(client.get("/api/v1/audit-logs").json()["events"]) == 2
    assert client.post("/api/v1/test/reset").status_code == 204
    assert client.get(f"/api/v1/releases/{rid}").status_code == 404
    assert client.get("/api/v1/audit-logs").json() == {"events": []}
    # same product/version can be registered again after reset
    r = client.post(
        "/api/v1/releases",
        json={"product": "R", "version": "1", "support_end_date": "2030-01-01"},
        headers=H,
    )
    assert r.status_code == 201


def test_reset_restores_real_clock(client: TestClient) -> None:
    client.put("/api/v1/test/clock", json={"now": "2020-01-01T00:00:00Z"})
    r = client.post(
        "/api/v1/releases",
        json={"product": "R", "version": "1", "support_end_date": "2021-01-01"},
        headers=H,
    )
    assert r.json()["support_status"] == "supported"
    client.post("/api/v1/test/reset")
    r = client.post(
        "/api/v1/releases",
        json={"product": "R", "version": "1", "support_end_date": "2021-01-01"},
        headers=H,
    )
    assert r.json()["support_status"] == "unsupported"


def test_audit_still_append_only_after_reset(client: TestClient, tmp_path: Path) -> None:
    seed(client)
    client.post("/api/v1/test/reset")
    seed(client)
    db_path = client.app.state.settings.db_path  # type: ignore[attr-defined]
    conn = sqlite3.connect(db_path)
    for sql in ("UPDATE audit_log SET user_id = 'x'", "DELETE FROM audit_log"):
        try:
            conn.execute(sql)
            raise AssertionError(f"{sql} should have been blocked")
        except sqlite3.DatabaseError as exc:
            assert "append-only" in str(exc)
    conn.close()


def test_test_endpoints_absent_unless_enabled(tmp_path: Path) -> None:
    app = create_app(Settings(db_path=str(tmp_path / "x.db"), enable_test_endpoints=False))
    with TestClient(app) as c:
        assert c.post("/api/v1/test/reset").status_code == 404
        assert c.put("/api/v1/test/clock", json={"now": "2026-01-01T00:00:00Z"}).status_code == 404
        assert c.get("/health").status_code == 200


def test_health_ok_and_leaves_no_data(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert client.get("/api/v1/audit-logs").json() == {"events": []}
