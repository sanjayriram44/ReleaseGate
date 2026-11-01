"""AC-04 (REQ-03) and AC-05 (REQ-04) with the shared CVE fixtures.

fixtures/ground_truth.json is a DRAFT until one checker per team verifies it (decision Q7), so a
pass here shows the system matches the draft, not that the draft is right.
"""

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

FIXTURES = Path("fixtures")
H = {"X-User-Id": "ac04"}


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def seeded(client: TestClient) -> dict[str, str]:
    dataset = load("cve_dataset.json")
    keys: dict[str, str] = {}
    for rel in dataset["releases"]:
        r = client.post("/api/v1/releases", json=rel["request"], headers=H)
        assert r.status_code == 201
        rid = r.json()["release_id"]
        keys[rid] = rel["key"]
        if rel["sbom_file"]:
            body = (FIXTURES / rel["sbom_file"]).read_bytes()
            put = client.put(
                f"/api/v1/releases/{rid}/sbom",
                content=body,
                headers={**H, "Content-Type": "application/json"},
            )
            assert put.status_code == 200
    records = load("vulnerabilities.json")["records"]
    r = client.put(
        "/api/v1/test/vulnerability-source", json={"mode": "available", "records": records}
    )
    assert r.status_code == 200
    assert (
        client.put("/api/v1/test/clock", json={"now": dataset["reference_clock"]}).status_code
        == 200
    )
    return keys


def as_sets(
    body: dict[str, Any], keys: dict[str, str]
) -> dict[str, set[tuple[str, frozenset[str]]]]:
    return {
        group: {
            (keys[a["release_id"]], frozenset(c["purl"] for c in a["matched_components"]))
            for a in body[group]
        }
        for group in ("supported", "unsupported")
    }


def expected_sets(case: dict[str, Any]) -> dict[str, set[tuple[str, frozenset[str]]]]:
    return {
        group: {(e["release"], frozenset(e["matched_purls"])) for e in case[group]}
        for group in ("supported", "unsupported")
    }


@pytest.mark.parametrize("case", load("ground_truth.json")["cves"], ids=lambda c: c["cve_id"])
def test_ac04_matches_ground_truth(
    client: TestClient, seeded: dict[str, str], case: dict[str, Any]
) -> None:
    t0 = time.monotonic()
    r = client.get(f"/api/v1/vulnerabilities/{case['cve_id']}/affected-releases")
    assert time.monotonic() - t0 <= 10
    assert r.status_code == case["expect_status"]
    assert r.json()["cve_id"] == case["cve_id"]
    assert as_sets(r.json(), seeded) == expected_sets(case)


def test_ac05_unknown_and_unreachable(client: TestClient, seeded: dict[str, str]) -> None:
    truth = load("ground_truth.json")
    for case in (truth["unknown_cve"],):
        r = client.get(f"/api/v1/vulnerabilities/{case['cve_id']}/affected-releases")
        assert (r.status_code, r.json()["error"]["code"]) == (
            case["expect_status"],
            case["expect_code"],
        )
    records = load("vulnerabilities.json")["records"]
    client.put(
        "/api/v1/test/vulnerability-source", json={"mode": "unreachable", "records": records}
    )
    case = truth["unreachable"]
    t0 = time.monotonic()
    r = client.get(f"/api/v1/vulnerabilities/{case['cve_id']}/affected-releases")
    assert time.monotonic() - t0 <= 15
    assert (r.status_code, r.json()["error"]["code"]) == (
        case["expect_status"],
        case["expect_code"],
    )


def test_fixtures_are_marked_as_drafts() -> None:
    """Remove this test, and the _status fields, once both checkers sign off (decision Q7)."""
    for name in ("vulnerabilities.json", "cve_dataset.json", "ground_truth.json"):
        assert load(name)["_status"].startswith("DRAFT")
