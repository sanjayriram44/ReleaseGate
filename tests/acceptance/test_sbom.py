import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.routers import sbom as sbom_router
from tests.sbom_helpers import make_sbom, raw

H = {"X-User-Id": "alice"}
JSON = {**H, "Content-Type": "application/json"}
FIXTURES = Path("fixtures")


def release(client: TestClient, version: str = "1.0") -> str:
    r = client.post(
        "/api/v1/releases",
        json={"product": "Router", "version": version, "support_end_date": "2030-01-01"},
        headers=H,
    )
    return str(r.json()["release_id"])


def put(client: TestClient, rid: str, body: bytes, headers: dict[str, str] = JSON) -> Any:
    return client.put(f"/api/v1/releases/{rid}/sbom", content=body, headers=headers)


def components(client: TestClient, rid: str) -> list[dict[str, Any]]:
    r = client.get(f"/api/v1/releases/{rid}/components")
    assert r.status_code == 200
    assert r.json()["release_id"] == rid
    return list(r.json()["components"])


def test_no_sbom_returns_empty_array(client: TestClient) -> None:
    assert components(client, release(client)) == []


def test_unknown_release_components_404(client: TestClient) -> None:
    r = client.get("/api/v1/releases/nope/components")
    assert r.status_code == 404 and r.json()["error"]["code"] == "RELEASE_NOT_FOUND"


def test_upload_stores_and_returns_components(client: TestClient) -> None:
    rid = release(client)
    r = put(client, rid, raw(make_sbom(3)))
    assert r.status_code == 200
    assert r.json() == {"release_id": rid, "component_count": 3}
    got = components(client, rid)
    assert [(c["name"], c["version"], c["purl"]) for c in got] == [
        ("lib-0", "0.0.0", "pkg:npm/lib-0@0.0.0"),
        ("lib-1", "1.0.0", "pkg:npm/lib-1@1.0.0"),
        ("lib-2", "2.0.0", "pkg:npm/lib-2@2.0.0"),
    ]


def test_missing_purl_is_null(client: TestClient) -> None:
    rid = release(client)
    doc = make_sbom(1)
    del doc["components"][0]["purl"]
    assert put(client, rid, raw(doc)).status_code == 200
    assert components(client, rid)[0]["purl"] is None


def test_replace_swaps_components(client: TestClient) -> None:
    rid = release(client)
    put(client, rid, raw(make_sbom(5, prefix="old")))
    r = put(client, rid, raw(make_sbom(2, prefix="new")))
    assert r.json()["component_count"] == 2
    assert [c["name"] for c in components(client, rid)] == ["new-0", "new-1"]


def test_invalid_replacement_leaves_components_untouched(client: TestClient) -> None:
    rid = release(client)
    put(client, rid, raw(make_sbom(4)))
    before = components(client, rid)
    bad = make_sbom(2)
    del bad["bomFormat"]
    assert put(client, rid, raw(bad)).status_code == 400
    assert put(client, rid, b"garbage").status_code == 400
    assert components(client, rid) == before


def test_ac02_shared_25_component_sbom(client: TestClient) -> None:
    spec = json.loads((FIXTURES / "releases.json").read_text())["ac02"]
    sbom_bytes = (FIXTURES / spec["sbom_file"]).read_bytes()
    expected = [(c["name"], c["version"]) for c in json.loads(sbom_bytes)["components"]]
    ids: dict[str, str] = {}
    for rel in spec["releases"]:
        r = client.post("/api/v1/releases", json=rel["request"], headers=H)
        assert r.status_code == 201
        ids[rel["id"]] = r.json()["release_id"]
    for rel in spec["releases"]:
        if rel["upload_sbom"]:
            r = put(client, ids[rel["id"]], sbom_bytes)
            assert r.status_code == rel["expected"]["sbom_http_status"]
            assert r.json()["component_count"] == rel["expected"]["component_count"]
    for rel in spec["releases"]:
        got = components(client, ids[rel["id"]])
        assert len(got) == rel["expected"]["component_count"]
        if rel["upload_sbom"]:
            assert [(c["name"], c["version"]) for c in got] == expected


def test_ac03_rejections_store_nothing_and_state_reason(client: TestClient) -> None:
    rid = release(client)
    missing_field = make_sbom(2)
    del missing_field["bomFormat"]
    cases = {
        "malformed": (b'{"bomFormat": "CycloneDX", ', "not valid JSON"),
        "missing field": (raw(missing_field), "missing required field: bomFormat"),
        "plaintext": (b"this is just text", "not valid JSON"),
    }
    for label, (body, reason) in cases.items():
        r = put(client, rid, body)
        assert r.status_code == 400, label
        assert reason in r.json()["error"]["message"], label
    assert components(client, rid) == []

    r = put(client, "rel-unregistered", raw(make_sbom(1)))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RELEASE_NOT_FOUND"
    assert client.get("/api/v1/releases/rel-unregistered/components").status_code == 404


def test_put_sbom_requires_user_id(client: TestClient) -> None:
    rid = release(client)
    r = put(client, rid, raw(make_sbom(1)), headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"
    assert components(client, rid) == []


def test_upload_works_on_database_created_by_older_schema(tmp_path: Path) -> None:
    import sqlite3

    from app.config import Settings
    from app.main import create_app

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE releases (
            release_id TEXT PRIMARY KEY, product TEXT NOT NULL, version TEXT NOT NULL,
            support_end_date TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE (product, version));
        INSERT INTO releases VALUES ('r1', 'p', '1', '2030-01-01', '2026-01-01T00:00:00Z');
        """
    )
    old.close()
    with TestClient(create_app(Settings(db_path=str(path)))) as c:
        r = put(c, "r1", (FIXTURES / "sbom_25_components.json").read_bytes())
        assert r.status_code == 200 and r.json()["component_count"] == 25


def test_nested_components_are_stored_and_counted(client: TestClient) -> None:
    rid = release(client)
    doc = make_sbom(2)
    doc["components"][1]["components"] = [
        {"type": "library", "name": "inner", "version": "3.0.0", "purl": "pkg:npm/inner@3.0.0"}
    ]
    doc["metadata"] = {"component": {"type": "application", "name": "Router", "version": "1.0"}}
    r = put(client, rid, raw(doc))
    assert r.status_code == 200 and r.json()["component_count"] == 3
    assert [c["name"] for c in components(client, rid)] == ["lib-0", "lib-1", "inner"]


def test_nested_component_without_version_stores_nothing(client: TestClient) -> None:
    rid = release(client)
    assert put(client, rid, raw(make_sbom(1))).status_code == 200
    doc = make_sbom(2)
    doc["components"][1]["components"] = [{"type": "library", "name": "inner"}]
    r = put(client, rid, raw(doc))
    assert r.status_code == 400
    assert "components[1].components[0]" in r.json()["error"]["message"]
    assert [c["name"] for c in components(client, rid)] == ["lib-0"]


def test_health_answers_during_slow_sbom_upload(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long validation must not block the event loop (Phase 3 review finding 1)."""
    started, health_done = threading.Event(), threading.Event()
    real = sbom_router.parse_and_validate

    def slow(body: bytes) -> Any:
        started.set()
        health_done.wait(timeout=3)  # held until /health has answered, or 3 s
        return real(body)

    monkeypatch.setattr(sbom_router, "parse_and_validate", slow)
    rid = release(client)
    result: dict[str, Any] = {}
    upload = threading.Thread(target=lambda: result.update(r=put(client, rid, raw(make_sbom(2)))))
    upload.start()
    assert started.wait(timeout=3)
    t0 = time.monotonic()
    h = client.get("/health")
    elapsed = time.monotonic() - t0
    health_done.set()
    upload.join(timeout=5)
    assert h.status_code == 200
    assert elapsed < 1, f"/health took {elapsed:.1f} s during an upload"
    assert result["r"].status_code == 200


def test_too_deeply_nested_sbom_is_400_and_stores_nothing(client: TestClient) -> None:
    rid = release(client)
    assert put(client, rid, raw(make_sbom(2))).status_code == 200
    before = components(client, rid)
    inner: dict[str, Any] = {"type": "library", "name": "leaf", "version": "1"}
    for i in range(300):
        inner = {"type": "library", "name": f"n{i}", "version": "1", "components": [inner]}
    deep = {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1, "components": [inner]}
    r = put(client, rid, raw(deep))
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_SBOM"
    assert "nested too deeply" in r.json()["error"]["message"]
    # Some Pythons parse this much raw nesting, then reject the array: a 400 either way.
    r = put(client, rid, b"[" * 100_000 + b"]" * 100_000)
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_SBOM"
    assert components(client, rid) == before
    assert put(client, rid, raw(make_sbom(3))).status_code == 200  # still accepts a valid SBOM
