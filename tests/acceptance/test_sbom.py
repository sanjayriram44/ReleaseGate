import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

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
