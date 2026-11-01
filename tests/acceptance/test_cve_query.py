"""CVE query over HTTP: AC-05 (REQ-04) and the matching rules (decisions Q4-Q6). AC-04 with the
shared CVE fixtures is in test_ac04_fixture.py."""

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.sbom_helpers import raw

H = {"X-User-Id": "alice"}
WERKZEUG = "pkg:pypi/werkzeug@2.2.2"


def load_source(client: TestClient, records: list[dict[str, Any]], mode: str = "available") -> Any:
    r = client.put("/api/v1/test/vulnerability-source", json={"mode": mode, "records": records})
    assert r.status_code == 200
    return r


def make_release(client: TestClient, product: str, version: str, end: str, purls: list[Any]) -> str:
    r = client.post(
        "/api/v1/releases",
        json={"product": product, "version": version, "support_end_date": end},
        headers=H,
    )
    rid = str(r.json()["release_id"])
    comps = []
    for i, purl in enumerate(purls):
        comp: dict[str, Any] = {"type": "library", "name": f"c{i}", "version": "1"}
        if isinstance(purl, tuple):
            comp["name"], comp["version"], purl = purl
        if purl is not None:
            comp["purl"] = purl
        comps.append(comp)
    doc = {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1, "components": comps}
    assert (
        client.put(f"/api/v1/releases/{rid}/sbom", content=raw(doc), headers=H).status_code == 200
    )
    return rid


def query(client: TestClient, cve: str) -> Any:
    return client.get(f"/api/v1/vulnerabilities/{cve}/affected-releases")


# -- AC-05 ----------------------------------------------------------------------------------


def test_ac05_known_cve_without_matches_is_200_empty(client: TestClient) -> None:
    make_release(client, "P", "1", "2030-01-01", ["pkg:pypi/urllib3@1.26.14"])
    load_source(client, [{"cve_id": "CVE-2019-11324", "affected_purls": []}])
    r = query(client, "CVE-2019-11324")
    assert r.status_code == 200
    assert r.json() == {"cve_id": "CVE-2019-11324", "supported": [], "unsupported": []}


def test_ac05_unknown_cve_is_404(client: TestClient) -> None:
    load_source(client, [{"cve_id": "CVE-2019-11324", "affected_purls": []}])
    t0 = time.monotonic()
    r = query(client, "CVE-2099-0001")
    assert time.monotonic() - t0 < 15
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "CVE_UNKNOWN"
    assert r.json()["error"]["message"]


def test_ac05_unreachable_source_is_503_even_for_known_or_unknown(client: TestClient) -> None:
    make_release(client, "P", "1", "2030-01-01", [WERKZEUG])
    load_source(client, [{"cve_id": "CVE-2023-25577", "affected_purls": [WERKZEUG]}], "unreachable")
    for cve in ("CVE-2023-25577", "CVE-2099-0001"):
        t0 = time.monotonic()
        r = query(client, cve)
        assert time.monotonic() - t0 < 15
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "VULNERABILITY_SOURCE_UNREACHABLE"


@pytest.mark.parametrize("cve", ["CVE-26-1", "abc", "cve-2023-25577", "CVE-2023-", "CVE-2023-1a"])
def test_malformed_cve_id_is_400(client: TestClient, cve: str) -> None:
    load_source(client, [], "unreachable")  # format is checked before reachability
    r = query(client, cve)
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"
    assert "cveId" in r.json()["error"]["message"]


# -- Matching and grouping -------------------------------------------------------------------


def test_affected_releases_grouped_by_support_status_at_the_clock(client: TestClient) -> None:
    client.put("/api/v1/test/clock", json={"now": "2026-11-01T23:59:59Z"})
    old = make_release(client, "Gateway", "1.0", "2026-10-31", [WERKZEUG, "pkg:pypi/flask@2.2.2"])
    edge = make_release(client, "Gateway", "2.0", "2026-11-01", [("werkzeug", "2.2.2", WERKZEUG)])
    make_release(client, "Gateway", "3.0", "2030-01-01", ["pkg:pypi/werkzeug@2.2.3"])
    load_source(client, [{"cve_id": "CVE-2023-25577", "affected_purls": [WERKZEUG]}])
    r = query(client, "CVE-2023-25577")
    assert r.status_code == 200
    assert r.json() == {
        "cve_id": "CVE-2023-25577",
        "supported": [
            {
                "release_id": edge,
                "product": "Gateway",
                "version": "2.0",
                "support_end_date": "2026-11-01",
                "matched_components": [{"name": "werkzeug", "version": "2.2.2", "purl": WERKZEUG}],
            }
        ],
        "unsupported": [
            {
                "release_id": old,
                "product": "Gateway",
                "version": "1.0",
                "support_end_date": "2026-10-31",
                "matched_components": [{"name": "c0", "version": "1", "purl": WERKZEUG}],
            }
        ],
    }
    # One second later the boundary release is unsupported too.
    client.put("/api/v1/test/clock", json={"now": "2026-11-02T00:00:00Z"})
    body = query(client, "CVE-2023-25577").json()
    assert body["supported"] == [] and [a["version"] for a in body["unsupported"]] == ["1.0", "2.0"]


def test_qualifiers_and_subpath_are_ignored(client: TestClient) -> None:
    rid = make_release(
        client,
        "P",
        "1",
        "2030-01-01",
        [f"{WERKZEUG}?package-id=abc123", "pkg:pypi/flask@2.2.2#src/flask", None],
    )
    load_source(
        client,
        [
            {
                "cve_id": "CVE-2023-25577",
                "affected_purls": [WERKZEUG, "pkg:pypi/flask@2.2.2?arch=any"],
            }
        ],
    )
    [hit] = query(client, "CVE-2023-25577").json()["supported"]
    assert hit["release_id"] == rid
    assert [c["purl"] for c in hit["matched_components"]] == [
        f"{WERKZEUG}?package-id=abc123",
        "pkg:pypi/flask@2.2.2#src/flask",
    ]


def test_versions_must_match_exactly_and_components_without_purl_never_match(
    client: TestClient,
) -> None:
    make_release(
        client, "P", "1", "2030-01-01", ["pkg:pypi/werkzeug@2.2.20", ("werkzeug", "2.2.2", None)]
    )
    load_source(client, [{"cve_id": "CVE-2023-25577", "affected_purls": [WERKZEUG]}])
    assert query(client, "CVE-2023-25577").json()["supported"] == []


def test_matched_components_sorted_and_releases_sorted(client: TestClient) -> None:
    b = make_release(
        client, "B", "1", "2030-01-01", [("zlib", "1", "pkg:x/z@1"), ("alib", "2", "pkg:x/a@2")]
    )
    a = make_release(client, "A", "1", "2030-01-01", ["pkg:x/z@1"])
    load_source(client, [{"cve_id": "CVE-2000-1", "affected_purls": ["pkg:x/z@1", "pkg:x/a@2"]}])
    sup = query(client, "CVE-2000-1").json()["supported"]
    assert [s["release_id"] for s in sup] == [a, b]
    assert [c["name"] for c in sup[1]["matched_components"]] == ["alib", "zlib"]


def test_query_is_read_only(client: TestClient) -> None:
    make_release(client, "P", "1", "2030-01-01", [WERKZEUG])
    before = client.get("/api/v1/audit-logs").json()["events"]
    load_source(client, [{"cve_id": "CVE-2023-25577", "affected_purls": [WERKZEUG]}])
    query(client, "CVE-2023-25577")
    assert client.get("/api/v1/audit-logs").json()["events"] == before


def test_replacing_an_sbom_changes_the_answer(client: TestClient) -> None:
    rid = make_release(client, "P", "1", "2030-01-01", [WERKZEUG])
    load_source(client, [{"cve_id": "CVE-2023-25577", "affected_purls": [WERKZEUG]}])
    assert len(query(client, "CVE-2023-25577").json()["supported"]) == 1
    doc = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": "werkzeug",
                "version": "2.2.3",
                "purl": "pkg:pypi/werkzeug@2.2.3",
            }
        ],
    }
    client.put(f"/api/v1/releases/{rid}/sbom", content=raw(doc), headers=H)
    assert query(client, "CVE-2023-25577").json()["supported"] == []


# -- The test source (decision Q6) ----------------------------------------------------------


def test_put_replaces_all_records(client: TestClient) -> None:
    load_source(client, [{"cve_id": "CVE-2000-1", "affected_purls": []}])
    load_source(client, [{"cve_id": "CVE-2000-2", "affected_purls": []}])
    assert query(client, "CVE-2000-1").status_code == 404
    assert query(client, "CVE-2000-2").status_code == 200
    load_source(client, [])
    assert query(client, "CVE-2000-2").status_code == 404


def test_records_may_be_omitted_and_repeat_a_cve(client: TestClient) -> None:
    r = client.put("/api/v1/test/vulnerability-source", json={"mode": "available"})
    assert r.status_code == 200
    make_release(client, "P", "1", "2030-01-01", ["pkg:x/a@1", "pkg:x/b@1"])
    load_source(
        client,
        [
            {"cve_id": "CVE-2000-1", "affected_purls": ["pkg:x/a@1"]},
            {"cve_id": "CVE-2000-1", "affected_purls": ["pkg:x/b@1"]},
        ],
    )
    [hit] = query(client, "CVE-2000-1").json()["supported"]
    assert len(hit["matched_components"]) == 2


def test_back_to_available_after_unreachable(client: TestClient) -> None:
    records = [{"cve_id": "CVE-2000-1", "affected_purls": []}]
    load_source(client, records, "unreachable")
    assert query(client, "CVE-2000-1").status_code == 503
    load_source(client, records)
    assert query(client, "CVE-2000-1").status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"mode": "down"},
        {"mode": "available", "records": [{"cve_id": "CVE-2000-1"}]},
        {"mode": "available", "records": [{"affected_purls": []}]},
        {"mode": "available", "records": [{"cve_id": "CVE-2000-1", "affected_purls": "pkg:x/a@1"}]},
    ],
)
def test_invalid_source_config_is_400(client: TestClient, body: dict[str, Any]) -> None:
    r = client.put("/api/v1/test/vulnerability-source", json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_reset_restores_available_with_no_records(client: TestClient) -> None:
    load_source(client, [{"cve_id": "CVE-2000-1", "affected_purls": []}], "unreachable")
    assert client.post("/api/v1/test/reset").status_code == 204
    assert query(client, "CVE-2000-1").status_code == 404
    assert client.get("/health").json()["source_mode"] == "available"


def test_health_reports_source_mode(client: TestClient) -> None:
    assert client.get("/health").json()["source_mode"] == "available"
    load_source(client, [], "unreachable")
    assert client.get("/health").json()["source_mode"] == "unreachable"
