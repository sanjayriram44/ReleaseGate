"""Incidents and deadlines over HTTP: AC-06 (REQ-05), AC-07 (REQ-06), decisions Q2-Q4."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

H = {"X-User-Id": "alice"}
AWARE = "2026-11-01T10:00:00Z"
EW = "2026-11-02T10:00:00Z"
VN = "2026-11-04T10:00:00Z"


def set_clock(client: TestClient, now: str) -> None:
    assert client.put("/api/v1/test/clock", json={"now": now}).status_code == 200


def make_incident(client: TestClient, **overrides: Any) -> Any:
    body = {
        "cve_id": "CVE-2023-25577",
        "awareness_at": AWARE,
        "classification": "mandatory",
        "rationale": "Actively exploited in the field; vendor confirmed.",
        **overrides,
    }
    return client.post("/api/v1/incidents", json=body, headers=H)


def submit(client: TestClient, iid: str, stage: str, at: str) -> Any:
    return client.post(
        f"/api/v1/incidents/{iid}/submissions",
        json={"stage": stage, "submitted_at": at},
        headers=H,
    )


def audit_actions(client: TestClient) -> list[str]:
    return [e["action"] for e in client.get("/api/v1/audit-logs").json()["events"]]


# -- AC-06 ----------------------------------------------------------------------------------


def test_ac06_mandatory_incident_is_stored(client: TestClient) -> None:
    set_clock(client, "2026-11-01T12:00:00Z")
    r = make_incident(client, awareness_at="2026-11-01T12:00:00+02:00")
    assert r.status_code == 201
    inc = r.json()
    assert inc["incident_id"]
    assert inc["created_by"] == "alice"
    assert inc["classification"] == "mandatory"
    assert inc["awareness_at"] == AWARE
    assert inc["rationale"] == "Actively exploited in the field; vendor confirmed."
    assert inc["cve_id"] == "CVE-2023-25577"
    assert inc["fix_available_at"] is None
    assert inc["deadlines"] == {
        "early_warning": {"deadline_at": EW, "submitted_at": None, "status": "pending"},
        "vulnerability_notification": {
            "deadline_at": VN,
            "submitted_at": None,
            "status": "pending",
        },
        "final_report": {"deadline_at": None, "submitted_at": None, "status": "not_applicable"},
    }
    assert client.get(f"/api/v1/incidents/{inc['incident_id']}").json() == inc
    events = client.get("/api/v1/audit-logs").json()["events"]
    assert [(e["action"], e["entity_type"], e["entity_id"], e["user_id"]) for e in events] == [
        ("INCIDENT_CREATED", "incident", inc["incident_id"], "alice")
    ]


def test_ac06_voluntary_incident_has_no_deadlines(client: TestClient) -> None:
    rationale = "  Low-risk issue, reported voluntarily.\nSecond line.  "
    r = make_incident(client, classification="voluntary", cve_id=None, rationale=rationale)
    assert r.status_code == 201
    inc = r.json()
    assert inc["cve_id"] is None and inc["rationale"] == rationale
    assert {s: d["status"] for s, d in inc["deadlines"].items()} == {
        "early_warning": "not_applicable",
        "vulnerability_notification": "not_applicable",
        "final_report": "not_applicable",
    }


def test_cve_id_may_be_omitted(client: TestClient) -> None:
    body = {"awareness_at": AWARE, "classification": "mandatory", "rationale": "r"}
    r = client.post("/api/v1/incidents", json=body, headers=H)
    assert r.status_code == 201 and r.json()["cve_id"] is None


@pytest.mark.parametrize(
    ("overrides", "drop", "fragment"),
    [
        ({}, "rationale", "rationale is required"),
        ({"rationale": "   "}, None, "rationale must not be blank"),
        ({"classification": "urgent"}, None, "classification"),
        ({}, "classification", "classification is required"),
        ({"awareness_at": "2026-11-01T10:00:00"}, None, "awareness_at"),
        ({}, "awareness_at", "awareness_at is required"),
        ({"cve_id": "CVE-26-1"}, None, "cve_id"),
        ({"cve_id": "abc"}, None, "cve_id"),
    ],
)
def test_ac06_invalid_incident_is_400_and_nothing_stored(
    client: TestClient, overrides: dict[str, Any], drop: str | None, fragment: str
) -> None:
    body: dict[str, Any] = {
        "awareness_at": AWARE,
        "classification": "mandatory",
        "rationale": "r",
        **overrides,
    }
    if drop:
        del body[drop]
    r = client.post("/api/v1/incidents", json=body, headers=H)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"
    assert fragment in r.json()["error"]["message"]
    assert audit_actions(client) == []


def test_missing_user_is_400(client: TestClient) -> None:
    body = {"awareness_at": AWARE, "classification": "mandatory", "rationale": "r"}
    assert client.post("/api/v1/incidents", json=body).status_code == 400


def test_unknown_incident_is_404(client: TestClient) -> None:
    for r in (
        client.get("/api/v1/incidents/nope"),
        client.patch("/api/v1/incidents/nope", json={"fix_available_at": AWARE}, headers=H),
        submit(client, "nope", "early_warning", EW),
    ):
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "INCIDENT_NOT_FOUND"


# -- AC-07 ----------------------------------------------------------------------------------


def test_ac07_deadlines_follow_the_test_clock(client: TestClient) -> None:
    set_clock(client, AWARE)
    iid = make_incident(client).json()["incident_id"]

    # Early warning recorded exactly at +24 h: met.
    set_clock(client, EW)
    r = submit(client, iid, "early_warning", EW)
    assert r.status_code == 201
    assert r.json()["deadlines"]["early_warning"] == {
        "deadline_at": EW,
        "submitted_at": EW,
        "status": "met",
    }

    # At +72 h the notification is still pending; one second later it is overdue.
    set_clock(client, VN)
    inc = client.get(f"/api/v1/incidents/{iid}").json()
    assert inc["deadlines"]["vulnerability_notification"]["status"] == "pending"
    set_clock(client, "2026-11-04T10:00:01Z")
    inc = client.get(f"/api/v1/incidents/{iid}").json()
    assert inc["deadlines"]["vulnerability_notification"] == {
        "deadline_at": VN,
        "submitted_at": None,
        "status": "overdue",
    }

    # Fix available: final report due 14 days later; submitted after 13 days: met.
    r = client.patch(
        f"/api/v1/incidents/{iid}", json={"fix_available_at": "2026-11-05T08:00:00Z"}, headers=H
    )
    assert r.status_code == 200
    assert r.json()["fix_available_at"] == "2026-11-05T08:00:00Z"
    assert r.json()["deadlines"]["final_report"] == {
        "deadline_at": "2026-11-19T08:00:00Z",
        "submitted_at": None,
        "status": "pending",
    }
    r = submit(client, iid, "final_report", "2026-11-18T08:00:00Z")
    assert r.status_code == 201
    assert r.json()["deadlines"]["final_report"]["status"] == "met"
    assert audit_actions(client) == [
        "INCIDENT_CREATED",
        "SUBMISSION_RECORDED",
        "FIX_AVAILABLE_RECORDED",
        "SUBMISSION_RECORDED",
    ]


def test_late_submission_stays_overdue(client: TestClient) -> None:
    set_clock(client, AWARE)
    iid = make_incident(client).json()["incident_id"]
    r = submit(client, iid, "vulnerability_notification", "2026-11-04T10:00:01Z")
    assert r.json()["deadlines"]["vulnerability_notification"] == {
        "deadline_at": VN,
        "submitted_at": "2026-11-04T10:00:01Z",
        "status": "overdue",
    }


def test_submission_keeps_fractions_and_converts_offsets(client: TestClient) -> None:
    iid = make_incident(client).json()["incident_id"]
    r = submit(client, iid, "early_warning", "2026-11-02T12:00:00.250000+02:00")
    assert r.json()["deadlines"]["early_warning"]["submitted_at"] == "2026-11-02T10:00:00.250000Z"
    assert r.json()["deadlines"]["early_warning"]["status"] == "overdue"


# -- Edge cases (decisions Q2-Q4) ------------------------------------------------------------


def test_duplicate_submission_is_409(client: TestClient) -> None:
    iid = make_incident(client).json()["incident_id"]
    assert submit(client, iid, "early_warning", EW).status_code == 201
    r = submit(client, iid, "early_warning", "2026-11-02T09:00:00Z")
    assert r.status_code == 409 and r.json()["error"]["code"] == "SUBMISSION_EXISTS"
    inc = client.get(f"/api/v1/incidents/{iid}").json()
    assert inc["deadlines"]["early_warning"]["submitted_at"] == EW
    assert audit_actions(client).count("SUBMISSION_RECORDED") == 1


def test_submission_for_not_applicable_stage_is_400(client: TestClient) -> None:
    iid = make_incident(client).json()["incident_id"]
    r = submit(client, iid, "final_report", EW)  # no fix yet
    assert r.status_code == 400 and "not_applicable" in r.json()["error"]["message"]
    vol = make_incident(client, classification="voluntary").json()["incident_id"]
    assert submit(client, vol, "early_warning", EW).status_code == 400
    assert audit_actions(client) == ["INCIDENT_CREATED", "INCIDENT_CREATED"]


@pytest.mark.parametrize(
    "body",
    [
        {"stage": "late_report", "submitted_at": EW},
        {"stage": "early_warning", "submitted_at": "2026-11-02T10:00:00"},
        {"stage": "early_warning"},
        {"submitted_at": EW},
    ],
)
def test_invalid_submission_is_400(client: TestClient, body: dict[str, Any]) -> None:
    iid = make_incident(client).json()["incident_id"]
    r = client.post(f"/api/v1/incidents/{iid}/submissions", json=body, headers=H)
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_times_before_awareness_are_400(client: TestClient) -> None:
    iid = make_incident(client).json()["incident_id"]
    r = submit(client, iid, "early_warning", "2026-11-01T09:59:59Z")
    assert r.status_code == 400 and "awareness_at" in r.json()["error"]["message"]
    r = client.patch(
        f"/api/v1/incidents/{iid}", json={"fix_available_at": "2026-10-31T00:00:00Z"}, headers=H
    )
    assert r.status_code == 400 and "awareness_at" in r.json()["error"]["message"]
    assert audit_actions(client) == ["INCIDENT_CREATED"]


def test_future_times_are_accepted(client: TestClient) -> None:
    set_clock(client, AWARE)
    iid = make_incident(client).json()["incident_id"]
    assert submit(client, iid, "early_warning", "2026-11-02T09:00:00Z").status_code == 201


def test_fix_can_be_overwritten_and_each_is_audited(client: TestClient) -> None:
    iid = make_incident(client).json()["incident_id"]
    for fix, due in (
        ("2026-11-05T00:00:00Z", "2026-11-19T00:00:00Z"),
        ("2026-11-06T00:00:00Z", "2026-11-20T00:00:00Z"),
    ):
        r = client.patch(f"/api/v1/incidents/{iid}", json={"fix_available_at": fix}, headers=H)
        assert r.status_code == 200
        assert r.json()["deadlines"]["final_report"]["deadline_at"] == due
    assert audit_actions(client).count("FIX_AVAILABLE_RECORDED") == 2


def test_fix_on_voluntary_is_stored_but_not_applicable(client: TestClient) -> None:
    iid = make_incident(client, classification="voluntary").json()["incident_id"]
    fix = "2026-11-05T00:00:00Z"
    r = client.patch(f"/api/v1/incidents/{iid}", json={"fix_available_at": fix}, headers=H)
    assert r.status_code == 200 and r.json()["fix_available_at"] == fix
    assert r.json()["deadlines"]["final_report"]["status"] == "not_applicable"


@pytest.mark.parametrize(
    "body", [{}, {"fix_available_at": "soon"}, {"fix_available_at": "2026-11-05T00:00:00"}]
)
def test_invalid_patch_is_400(client: TestClient, body: dict[str, Any]) -> None:
    iid = make_incident(client).json()["incident_id"]
    r = client.patch(f"/api/v1/incidents/{iid}", json=body, headers=H)
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_incidents_survive_a_restart(tmp_path: Any) -> None:
    from app.config import Settings
    from app.main import create_app

    settings = Settings(db_path=str(tmp_path / "r.db"), enable_test_endpoints=True)
    with TestClient(create_app(settings)) as c:
        iid = make_incident(c).json()["incident_id"]
        submit(c, iid, "early_warning", EW)
        before = c.get(f"/api/v1/incidents/{iid}").json()
    with TestClient(create_app(settings)) as c:
        assert c.get(f"/api/v1/incidents/{iid}").json() == before


def test_extreme_timestamps_are_400_not_500(client: TestClient) -> None:
    r = make_incident(client, awareness_at="9999-12-31T00:00:00Z")
    assert r.status_code == 400 and "out of range" in r.json()["error"]["message"]
    iid = make_incident(client).json()["incident_id"]
    r = client.patch(
        f"/api/v1/incidents/{iid}", json={"fix_available_at": "9999-12-25T00:00:00Z"}, headers=H
    )
    assert r.status_code == 400
    r = client.put("/api/v1/test/clock", json={"now": "0001-01-01T00:30:00+01:00"})
    assert r.status_code == 400
    assert audit_actions(client) == ["INCIDENT_CREATED"]
