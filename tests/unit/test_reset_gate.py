"""A production-configured app can't reach Database.reset(), the only path that deletes audit
rows (CLAUDE.md §4 item 5; evidence for AC-09's "no update or delete paths exist")."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import ResetNotAllowed
from app.main import create_app

H = {"X-User-Id": "alice"}


def _test_paths(enable_test_endpoints: bool, tmp_path: Path) -> list[str]:
    settings = Settings(db_path=str(tmp_path / "p.db"), enable_test_endpoints=enable_test_endpoints)
    paths = create_app(settings).openapi()["paths"]
    assert "/api/v1/releases" in paths
    return [p for p in paths if p.startswith(("/api/v1/test", "/test"))]


def test_production_app_mounts_no_test_routes(tmp_path: Path) -> None:
    # Positive control: a test deployment does publish the reset routes.
    assert {"/api/v1/test/reset", "/test/setup"} <= set(_test_paths(True, tmp_path))
    assert _test_paths(False, tmp_path) == []


def test_production_database_refuses_to_reset(tmp_path: Path) -> None:
    app = create_app(Settings(db_path=str(tmp_path / "p.db")))
    with pytest.raises(ResetNotAllowed):
        app.state.db.reset()


@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", "/api/v1/test/reset"), ("POST", "/test/setup"), ("POST", "/test/run")],
)
def test_production_reset_routes_are_absent_and_the_log_survives(
    tmp_path: Path, method: str, path: str
) -> None:
    with TestClient(create_app(Settings(db_path=str(tmp_path / "p.db")))) as client:
        body = {"product": "p", "version": "1", "support_end_date": "2030-01-01"}
        assert client.post("/api/v1/releases", json=body, headers=H).status_code == 201
        r = client.request(method, path, json={})
        assert r.status_code in (404, 405)
        assert len(client.get("/api/v1/audit-logs").json()["events"]) == 1


def test_test_deployment_can_still_reset(tmp_path: Path) -> None:
    settings = Settings(db_path=str(tmp_path / "t.db"), enable_test_endpoints=True)
    with TestClient(create_app(settings)) as client:
        body = {"product": "p", "version": "1", "support_end_date": "2030-01-01"}
        assert client.post("/api/v1/releases", json=body, headers=H).status_code == 201
        assert client.post("/api/v1/test/reset").status_code == 204
        assert client.get("/api/v1/audit-logs").json()["events"] == []
