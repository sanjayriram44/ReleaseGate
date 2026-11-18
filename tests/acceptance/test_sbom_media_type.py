"""The SBOM upload checks Content-Type: the contract's request body lists only application/json.

Team 2's 2026-11-02 run stored an SBOM sent as text/plain (CLAUDE.md §4 item 3, P5-Q9). The
accepted set is app.routers.sbom.SBOM_MEDIA_TYPES; a missing header is still open in P5-Q9.
"""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.routers import sbom as sbom_router

H = {"X-User-Id": "alice"}
SBOM = (Path("fixtures") / "sbom_25_components.json").read_bytes()
WRONG_TYPE = {"code": "INVALID_REQUEST", "message": "Content-Type must be application/json"}


def release(client: TestClient) -> str:
    r = client.post(
        "/api/v1/releases",
        json={"product": "Router", "version": "1.0", "support_end_date": "2030-01-01"},
        headers=H,
    )
    return str(r.json()["release_id"])


def put(client: TestClient, rid: str, headers: dict[str, str]) -> Any:
    return client.put(f"/api/v1/releases/{rid}/sbom", content=SBOM, headers=headers)


def audit_count(client: TestClient) -> int:
    return len(client.get("/api/v1/audit-logs").json()["events"])


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "application/json; charset=utf-8",
        "Application/JSON",
        "application/vnd.cyclonedx+json",
        "application/vnd.cyclonedx+json; version=1.6",
    ],
)
def test_json_media_types_are_accepted(client: TestClient, content_type: str) -> None:
    r = put(client, release(client), {**H, "Content-Type": content_type})
    assert r.status_code == 200 and r.json()["component_count"] == 25


@pytest.mark.parametrize(
    "content_type",
    ["text/plain", "application/xml", "application/x-www-form-urlencoded", "text/json", ""],
)
def test_other_media_types_are_400_and_nothing_changes(
    client: TestClient, content_type: str
) -> None:
    rid = release(client)
    assert put(client, rid, {**H, "Content-Type": "application/json"}).status_code == 200
    before = (client.get(f"/api/v1/releases/{rid}/components").json(), audit_count(client))
    r = put(client, rid, {**H, "Content-Type": content_type})
    assert r.status_code == 400 and r.json() == {"error": WRONG_TYPE}
    after = (client.get(f"/api/v1/releases/{rid}/components").json(), audit_count(client))
    assert after == before


def test_unknown_release_is_still_404_first(client: TestClient) -> None:
    r = put(client, "rel-does-not-exist", {**H, "Content-Type": "text/plain"})
    assert r.status_code == 404


def test_missing_user_is_still_reported_first(client: TestClient) -> None:
    r = put(client, release(client), {"Content-Type": "text/plain"})
    assert r.status_code == 400 and "X-User-Id" in r.json()["error"]["message"]


def test_missing_content_type_is_accepted_pending_p5_q9(client: TestClient) -> None:
    # Undecided (P5-Q9 proposes 400). Until Team 2 answers, the behaviour doesn't change.
    assert sbom_router.ALLOW_MISSING_CONTENT_TYPE is True
    r = client.put(f"/api/v1/releases/{release(client)}/sbom", content=SBOM, headers=H)
    assert r.status_code == 200


def test_missing_content_type_is_400_when_disallowed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sbom_router, "ALLOW_MISSING_CONTENT_TYPE", False)
    r = client.put(f"/api/v1/releases/{release(client)}/sbom", content=SBOM, headers=H)
    assert r.status_code == 400 and r.json() == {"error": WRONG_TYPE}
