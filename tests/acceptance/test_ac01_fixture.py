"""AC-01 driven by the pod's shared fixtures/releases.json (agreed; do not edit expectations)."""

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

H = {"X-User-Id": "alice"}
SPEC: dict[str, Any] = json.loads(Path("fixtures/releases.json").read_text())


def set_clock(client: TestClient, now: str) -> None:
    assert client.put("/api/v1/test/clock", json={"now": now}).status_code == 200


def run_cases(client: TestClient) -> dict[str, str]:
    set_clock(client, SPEC["reference_clock"])
    ids: dict[str, str] = {}
    for case in SPEC["ac01"]["cases"]:
        r = client.post("/api/v1/releases", json=case["request"], headers=H)
        exp = case["expected"]
        assert r.status_code == exp["http_status"], case["id"]
        if r.status_code == 201:
            ids[case["id"]] = r.json()["release_id"]
            assert r.json()["support_status"] == exp["support_status"], case["id"]
        else:
            assert r.json()["error"]["code"] == exp["error_code"], case["id"]
    return ids


def test_ac01_from_shared_fixture(client: TestClient) -> None:
    ids = run_cases(client)
    for case in SPEC["ac01"]["cases"]:
        if case["id"] in ids:
            got = client.get(f"/api/v1/releases/{ids[case['id']]}").json()
            assert got["support_status"] == case["expected"]["support_status"]
    # "nothing saved": the rejected release can be registered afterwards (201, not 409)
    rejected = next(c for c in SPEC["ac01"]["cases"] if c["expected"]["http_status"] == 400)
    retry = {**rejected["request"], "support_end_date": "2027-01-01"}
    assert client.post("/api/v1/releases", json=retry, headers=H).status_code == 201


def test_ac01_rollover_one_second_later(client: TestClient) -> None:
    ids = run_cases(client)
    roll = SPEC["ac01_rollover"]
    set_clock(client, roll["clock"])
    got = client.get(f"/api/v1/releases/{ids[roll['case_id']]}").json()
    assert got["support_status"] == roll["expected"]["support_status"]
