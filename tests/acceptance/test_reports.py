"""Report data and report generation over HTTP: REQ-07, REQ-08, AC-08 (CLAUDE.md §6.3, §6.4, §6.8).

Built on the proposed answers to P5-Q1..Q6 (docs/decisions.md, provisional).
"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

H = {"X-User-Id": "alice"}
NOW = "2026-11-20T12:00:00Z"
CASES = json.loads(Path("fixtures/report_cases.json").read_text())
COMPLETE = CASES["incidents"][0]
INCOMPLETE = CASES["incidents"][1]
STAGES = ["early_warning", "vulnerability_notification", "final_report"]


def set_clock(client: TestClient, now: str = NOW) -> None:
    assert client.put("/api/v1/test/clock", json={"now": now}).status_code == 200


def make_incident(client: TestClient, **overrides: Any) -> str:
    body = {**COMPLETE["create"], **overrides}
    r = client.post("/api/v1/incidents", json=body, headers=H)
    assert r.status_code == 201, r.text
    return str(r.json()["incident_id"])


def put_data(
    client: TestClient, iid: str, stage: str, body: Any, headers: dict[str, str] = H
) -> Any:
    return client.put(f"/api/v1/incidents/{iid}/report-data/{stage}", json=body, headers=headers)


def get_report(client: TestClient, iid: str, stage: str) -> Any:
    return client.get(f"/api/v1/incidents/{iid}/reports/{stage}")


def events(client: TestClient) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = client.get("/api/v1/audit-logs").json()["events"]
    return result


def assert_400(response: Any, message: str | None = None) -> None:
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    if message is not None:
        assert response.json()["error"]["message"] == message


# -- PUT .../report-data/{stage} ---------------------------------------------------------------


def test_put_stores_the_stage_and_returns_its_report(client: TestClient) -> None:
    set_clock(client)
    iid = make_incident(client)
    body = COMPLETE["report_data"]["vulnerability_notification"]
    r = put_data(client, iid, "vulnerability_notification", body)
    assert r.status_code == 200
    assert r.json() == {
        "incident_id": iid,
        "stage": "vulnerability_notification",
        "generated_at": NOW,
        "data": body,
        "missing_fields": [],
    }


def test_put_writes_one_audit_entry_without_the_text(client: TestClient) -> None:
    set_clock(client)
    iid = make_incident(client)
    before = events(client)
    body = {"severity": "High", "impact": "Denial of service", "vulnerability_description": None}
    r = put_data(client, iid, "final_report", body, {"X-User-Id": "bob"})
    assert r.status_code == 200
    after = events(client)
    assert after[: len(before)] == before and len(after) == len(before) + 1
    entry = after[-1]
    assert {k: entry[k] for k in ("user_id", "action", "entity_type", "entity_id")} == {
        "user_id": "bob",
        "action": "REPORT_DATA_STORED",
        "entity_type": "incident",
        "entity_id": iid,
    }
    assert entry["timestamp"] == NOW
    assert entry["details"] == {
        "stage": "final_report",
        "fields": ["impact", "severity", "vulnerability_description"],
    }
    assert "Denial" not in json.dumps(entry)


def test_put_replaces_the_whole_stage(client: TestClient) -> None:
    iid = make_incident(client)
    full = COMPLETE["report_data"]["final_report"]
    assert put_data(client, iid, "final_report", full).status_code == 200
    partial = {"severity": "Low"}
    r = put_data(client, iid, "final_report", partial)
    assert r.json()["data"] == partial
    assert r.json()["missing_fields"] == [
        "vulnerability_description",
        "impact",
        "corrective_measure_details",
    ]


def test_put_keeps_other_stages(client: TestClient) -> None:
    iid = make_incident(client)
    early = COMPLETE["report_data"]["early_warning"]
    assert put_data(client, iid, "early_warning", early).status_code == 200
    assert put_data(client, iid, "final_report", {"severity": "Low"}).status_code == 200
    assert get_report(client, iid, "early_warning").json()["data"] == early


def test_values_are_stored_exactly_as_sent(client: TestClient) -> None:
    iid = make_incident(client)
    body = {"member_states": [" de", "FR "]}
    assert put_data(client, iid, "early_warning", body).json()["data"] == body
    text = {"severity": "  High\n", "impact": ""}
    r = put_data(client, iid, "final_report", text)
    assert r.json()["data"] == text
    assert "impact" in r.json()["missing_fields"]


def test_nulls_are_accepted_and_reported_missing(client: TestClient) -> None:
    iid = make_incident(client)
    r = put_data(client, iid, "early_warning", {"member_states": None})
    assert r.status_code == 200
    assert r.json()["data"] == {} and r.json()["missing_fields"] == ["member_states"]


def test_voluntary_incident_and_final_report_before_the_fix_are_allowed(
    client: TestClient,
) -> None:
    iid = make_incident(client, classification="voluntary")
    body = COMPLETE["report_data"]["final_report"]
    r = put_data(client, iid, "final_report", body)
    assert r.status_code == 200 and r.json()["missing_fields"] == []


def test_unknown_incident_is_404_before_the_stage_or_body(client: TestClient) -> None:
    for stage in ("early_warning", "interim_report"):
        r = put_data(client, "inc-does-not-exist", stage, "not an object")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "INCIDENT_NOT_FOUND"


@pytest.mark.parametrize(
    ("stage", "body", "message"),
    [
        (
            "interim_report",
            {},
            "stage must be one of early_warning, vulnerability_notification, final_report",
        ),
        (
            "early_warning",
            {"member_states": ["DE"], "severity": "High"},
            "severity does not belong to stage early_warning",
        ),
        ("final_report", {"colour": "red"}, "colour is not a report data field"),
        ("final_report", {"severity": 3}, "severity must be a string"),
        (
            "early_warning",
            {"member_states": "DE"},
            "member_states must be an array of non-empty strings",
        ),
        ("early_warning", ["DE"], "request body must be a JSON object"),
    ],
)
def test_invalid_put_is_400_and_changes_nothing(
    client: TestClient, stage: str, body: Any, message: str
) -> None:
    set_clock(client)
    iid = make_incident(client)
    early = COMPLETE["report_data"]["early_warning"]
    assert put_data(client, iid, "early_warning", early).status_code == 200
    before = events(client)
    assert_400(put_data(client, iid, stage, body), message)
    assert events(client) == before
    assert get_report(client, iid, "early_warning").json()["data"] == early


@pytest.mark.parametrize(
    ("content", "content_type", "message"),
    [
        (b'{"severity": ', "application/json", "request body is not valid JSON"),
        (b"", "application/json", "request body is not valid JSON"),
        (b"\xff\xfe", "application/json", "request body is not valid JSON"),
        (b'{"severity": "High"}', "text/plain", "Content-Type must be application/json"),
        (b'{"severity": "High"}', None, "Content-Type must be application/json"),
    ],
)
def test_body_that_is_not_json_is_400(
    client: TestClient, content: bytes, content_type: str | None, message: str
) -> None:
    iid = make_incident(client)
    before = events(client)
    headers = {**H, "Content-Type": content_type} if content_type else H
    r = client.put(
        f"/api/v1/incidents/{iid}/report-data/final_report", content=content, headers=headers
    )
    assert_400(r, message)
    assert events(client) == before


def test_put_without_user_is_400(client: TestClient) -> None:
    iid = make_incident(client)
    before = events(client)
    r = put_data(client, iid, "early_warning", {"member_states": ["DE"]}, headers={})
    assert_400(r, "X-User-Id header is required")
    assert events(client) == before


# -- GET .../reports/{stage} -------------------------------------------------------------------


@pytest.mark.parametrize("stage", STAGES)
def test_nothing_stored_lists_every_required_field(client: TestClient, stage: str) -> None:
    set_clock(client)
    iid = make_incident(client)
    r = get_report(client, iid, stage)
    assert r.status_code == 200
    assert r.json() == {
        "incident_id": iid,
        "stage": stage,
        "generated_at": NOW,
        "data": {},
        "missing_fields": CASES["stage_fields"][stage]["required"],
    }


def test_generated_at_follows_the_clock_and_nothing_is_stored(client: TestClient) -> None:
    iid = make_incident(client)
    assert put_data(client, iid, "early_warning", {"member_states": ["DE"]}).status_code == 200
    before = events(client)
    for now in ("2026-11-20T12:00:00Z", "2026-11-21T08:30:00.250000Z"):
        set_clock(client, now)
        r = get_report(client, iid, "early_warning")
        assert r.json()["generated_at"] == now
        assert r.json()["data"] == {"member_states": ["DE"]}
    assert events(client) == before


def test_data_holds_only_the_requested_stage(client: TestClient) -> None:
    iid = make_incident(client)
    assert put_data(client, iid, "early_warning", {"member_states": ["DE"]}).status_code == 200
    r = get_report(client, iid, "final_report")
    assert r.json()["data"] == {}


def test_get_unknown_incident_is_404_before_the_stage(client: TestClient) -> None:
    for stage in ("early_warning", "interim_report"):
        r = get_report(client, "inc-does-not-exist", stage)
        assert r.status_code == 404 and r.json()["error"]["code"] == "INCIDENT_NOT_FOUND"


def test_get_invalid_stage_is_400(client: TestClient) -> None:
    assert_400(get_report(client, make_incident(client), "interim_report"))


def test_reports_survive_a_restart(tmp_path: Path) -> None:
    from app.config import Settings
    from app.main import create_app

    settings = Settings(db_path=str(tmp_path / "r.db"), enable_test_endpoints=True)
    with TestClient(create_app(settings)) as first:
        set_clock(first)
        iid = make_incident(first)
        for stage, body in COMPLETE["report_data"].items():
            assert put_data(first, iid, stage, body).status_code == 200
        before = [get_report(first, iid, s).json() for s in STAGES]
    with TestClient(create_app(settings)) as second:
        set_clock(second)
        assert [get_report(second, iid, s).json() for s in STAGES] == before


# -- AC-08 (REQ-07), from fixtures/report_cases.json (DRAFT until verified, P5-Q11) ------------


def test_ac08_reports_from_the_fixture(client: TestClient) -> None:
    ids = {}
    for case in CASES["incidents"]:
        iid = make_incident(client, **case["create"])
        r = client.patch(
            f"/api/v1/incidents/{iid}",
            json={"fix_available_at": case["fix_available_at"]},
            headers=H,
        )
        assert r.status_code == 200
        for stage, body in case["report_data"].items():
            assert put_data(client, iid, stage, body).status_code == 200
        ids[case["key"]] = iid
    set_clock(client, CASES["reference_clock"])
    for case in CASES["incidents"]:
        for stage in STAGES:
            r = get_report(client, ids[case["key"]], stage)
            assert r.status_code == 200
            report = r.json()
            assert set(report) == {
                "incident_id",
                "stage",
                "generated_at",
                "data",
                "missing_fields",
            }
            assert report["incident_id"] == ids[case["key"]] and report["stage"] == stage
            assert report["generated_at"] == CASES["reference_clock"]
            assert report["data"] == case["report_data"][stage]
            expected = case["expected"][stage]["missing_fields"]
            assert set(report["missing_fields"]) == set(expected), (case["key"], stage)


def test_ac08_incomplete_case_names_exactly_the_two_missing_fields() -> None:
    expected = INCOMPLETE["expected"]["vulnerability_notification"]["missing_fields"]
    assert set(expected) == {"exploit_nature", "user_mitigations"}
