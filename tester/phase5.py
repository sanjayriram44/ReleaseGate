"""Phase 5 checks: report generation (AC-08, REQ-07) and the audit log (AC-09, REQ-08).

Required checks follow the shared contract and the AC text (CLAUDE.md §6.8). Checks that rest on
a proposed pod answer (docs/pod-questions-phase5.md, P5-Q1..Q7; not yet agreed with Team 2) are
informational, so they never fail another team's run (CLAUDE.md §7 rule 4). AC-08's expected
values come from fixtures/report_cases.json, a DRAFT until one checker per team verifies it
(P5-Q11). AC-10 needs a restart, so it runs in two steps outside this run (tester/ac10.py).
"""

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from tester.checks import Runner

USER = {"X-User-Id": "releasegate-tester"}
STAGES = ("early_warning", "vulnerability_notification", "final_report")
REPORT_KEYS = {"incident_id", "stage", "generated_at", "data", "missing_fields"}
AC09_START = "2026-11-20T09:00:00Z"
AC09_USERS = ("tester-ac09-1", "tester-ac09-2", "tester-ac09-3", "tester-ac09-4")
# Proposed (P5-Q7): informational until Team 2 agrees.
AC09_ACTIONS = ("RELEASE_REGISTERED", "SBOM_STORED", "INCIDENT_CREATED", "SUBMISSION_RECORDED")
AC09_ENTITY_TYPES = ("release", "release", "incident", "incident")


def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _close(value: Any, want: str, seconds: float = 2) -> bool:
    got, expected = _instant(value), _instant(want)
    return (
        got is not None and expected is not None and abs(got - expected).total_seconds() <= seconds
    )


def _events(r: "Runner") -> tuple[httpx.Response, list[Any]]:
    g = r.call("GET", "/api/v1/audit-logs")
    events = (_json(g) or {}).get("events") if isinstance(_json(g), dict) else None
    return g, events if isinstance(events, list) else []


def _report_problems(report: Any, iid: str, stage: str, clock: str) -> list[str]:
    """What makes a body not a valid GeneratedReport for this incident, stage and clock."""
    if not isinstance(report, dict):
        return ["body is not a JSON object"]
    problems = []
    if not REPORT_KEYS <= set(report):
        problems.append(f"missing {sorted(REPORT_KEYS - set(report))}")
    if report.get("incident_id") != iid or report.get("stage") != stage:
        problems.append("wrong incident_id or stage")
    if not _close(report.get("generated_at"), clock):
        problems.append(f"generated_at {report.get('generated_at')!r} is not the clock {clock}")
    if not isinstance(report.get("data"), dict):
        problems.append("data is not an object")
    fields = report.get("missing_fields")
    if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
        problems.append("missing_fields is not an array of strings")
    return problems


def _put(r: "Runner", iid: str, stage: str, body: Any) -> httpx.Response:
    return r.call("PUT", f"/api/v1/incidents/{iid}/report-data/{stage}", json=body, headers=USER)


def _get(r: "Runner", iid: str, stage: str) -> httpx.Response:
    return r.call("GET", f"/api/v1/incidents/{iid}/reports/{stage}")


# -- AC-08 ------------------------------------------------------------------------------------


def ac08(r: "Runner") -> None:
    cases = r.fx.reports
    clock = cases["reference_clock"]
    ids: dict[str, str] = {}
    for case in cases["incidents"]:
        key = case["key"]
        c = r.call("POST", "/api/v1/incidents", json=case["create"], headers=USER)
        body = _json(c)
        iid = body.get("incident_id") if c.status_code == 201 and isinstance(body, dict) else None
        created = r.record(
            f"ac08.{key}.create",
            "AC-08",
            f"Create the {key} incident",
            isinstance(iid, str),
            "201 with an incident_id",
            f"{c.status_code}, incident_id={iid!r}",
            c,
        )
        if not created or not isinstance(iid, str):
            continue
        ids[key] = iid
        p = r.call(
            "PATCH",
            f"/api/v1/incidents/{iid}",
            json={"fix_available_at": case["fix_available_at"]},
            headers=USER,
        )
        r.expect_status(f"ac08.{key}.fix", "AC-08", f"Record the {key} incident's fix", p, 200)
        for stage in STAGES:
            resp = _put(r, iid, stage, case["report_data"][stage])
            r.expect_status(
                f"ac08.{key}.put.{stage}", "AC-08", f"PUT {stage} report data ({key})", resp, 200
            )
            if stage == "vulnerability_notification":
                body = _json(resp)
                keys = set(body) if isinstance(body, dict) else set()
                shaped = REPORT_KEYS <= keys
                r.record(
                    f"ac08.{key}.put_body",
                    "AC-08",
                    "PUT report data returns the stage's GeneratedReport (P5-Q3, proposed)",
                    resp.status_code == 200 and shaped,
                    "200 with a GeneratedReport body",
                    f"{resp.status_code}, keys {sorted(keys)}",
                    resp,
                    required=False,
                )

    r.set_clock(clock)
    for case in cases["incidents"]:
        key = case["key"]
        if key not in ids:
            continue
        iid = ids[key]
        for stage in STAGES:
            g = _get(r, iid, stage)
            report = _json(g)
            problems = _report_problems(report, iid, stage, clock) if g.status_code == 200 else []
            r.record(
                f"ac08.{key}.{stage}.shape",
                "AC-08",
                f"GET {stage} report ({key}) is a GeneratedReport with generated_at = clock",
                g.status_code == 200 and not problems,
                f"200, GeneratedReport for {stage}, generated_at={clock}",
                f"{g.status_code}, {'; '.join(problems) or 'ok'}",
                g,
            )
            if g.status_code != 200 or not isinstance(report, dict):
                continue
            want_data = case["report_data"][stage]
            r.record(
                f"ac08.{key}.{stage}.data",
                "AC-08",
                f"{stage} data ({key}) is exactly what was PUT",
                report.get("data") == want_data,
                json.dumps(want_data)[:200],
                json.dumps(report.get("data"))[:200],
                g,
            )
            want = set(case["expected"][stage]["missing_fields"])
            got = report.get("missing_fields")
            r.record(
                f"ac08.{key}.{stage}.missing",
                "AC-08",
                f"{stage} missing_fields ({key}) are exactly {sorted(want) or 'none'}",
                isinstance(got, list) and set(got) == want and len(got) == len(want),
                f"{sorted(want)} (as a set)",
                f"{got}",
                g,
            )
    if ids:
        _ac08_edges(r, next(iter(ids.values())), clock)


def _ac08_edges(r: "Runner", iid: str, clock: str) -> None:
    """The fixture's edge cases: unknown incident is required (404 is in the contract); the rest
    rest on proposals and are informational."""
    cases = r.fx.reports
    fields = cases["stage_fields"]
    for stage, method in (("early_warning", "PUT"), ("early_warning", "GET")):
        resp = (
            _put(r, "inc-does-not-exist", stage, {"member_states": ["DE"]})
            if method == "PUT"
            else _get(r, "inc-does-not-exist", stage)
        )
        r.expect_rejection(
            f"ac08.unknown_incident.{method.lower()}",
            "AC-08",
            f"{method} report for an unknown incident → 404",
            resp,
            404,
        )

    c = r.call(
        "POST",
        "/api/v1/incidents",
        json={**cases["incidents"][0]["create"], "rationale": "AC-08 edge cases."},
        headers=USER,
    )
    fresh = (_json(c) or {}).get("incident_id") if c.status_code == 201 else None
    if not isinstance(fresh, str):
        return
    before = len(_events(r)[1])
    for stage in STAGES:
        g = _get(r, fresh, stage)
        report = _json(g) if g.status_code == 200 else {}
        want = fields[stage]["required"]
        ok = isinstance(report, dict) and report.get("data") == {}
        ok = ok and isinstance(report.get("missing_fields"), list)
        ok = ok and set(report.get("missing_fields", [])) == set(want)
        r.record(
            f"ac08.nothing_stored.{stage}",
            "AC-08",
            f"Nothing stored: {stage} has data {{}} and every required field missing (P5-Q1)",
            g.status_code == 200 and ok,
            f"200, data={{}}, missing_fields={want}",
            f"{g.status_code}, {json.dumps(report)[:160]}",
            g,
            required=False,
        )
    r.record(
        "ac08.read_only",
        "AC-08",
        "Generating reports writes no audit event (P5-Q6)",
        len(_events(r)[1]) == before,
        f"{before} events",
        f"{len(_events(r)[1])} events",
        required=False,
    )

    complete = cases["incidents"][0]["report_data"]
    blank = {**complete["vulnerability_notification"], "user_mitigations": "   "}
    _put(r, fresh, "vulnerability_notification", blank)
    g = _get(r, fresh, "vulnerability_notification")
    got = (_json(g) or {}).get("missing_fields") if g.status_code == 200 else None
    r.record(
        "ac08.blank_string_is_missing",
        "AC-08",
        "A whitespace-only required field is listed as missing (P5-Q2)",
        got == ["user_mitigations"],
        "['user_mitigations']",
        f"{g.status_code}, {got}",
        g,
        required=False,
    )
    _put(r, fresh, "early_warning", {"member_states": []})
    g = _get(r, fresh, "early_warning")
    got = (_json(g) or {}).get("missing_fields") if g.status_code == 200 else None
    r.record(
        "ac08.empty_member_states_is_missing",
        "AC-08",
        "An empty member_states array is listed as missing (P5-Q2)",
        got == ["member_states"],
        "['member_states']",
        f"{g.status_code}, {got}",
        g,
        required=False,
    )

    _put(r, fresh, "early_warning", {"member_states": ["DE"]})
    resp = _put(r, fresh, "early_warning", {"member_states": ["DE"], "severity": "High"})
    after = _json(_get(r, fresh, "early_warning")) or {}
    r.record(
        "ac08.field_from_another_stage",
        "AC-08",
        "A field from another stage → 400 INVALID_REQUEST, stored data unchanged (P5-Q4)",
        resp.status_code == 400
        and ((_json(resp) or {}).get("error") or {}).get("code") == "INVALID_REQUEST"
        and after.get("data") == {"member_states": ["DE"]},
        "400 INVALID_REQUEST; data still {member_states: [DE]}",
        f"{resp.status_code}, data={after.get('data')}",
        resp,
        required=False,
    )
    for method in ("PUT", "GET"):
        resp = (
            _put(r, fresh, "interim_report", {})
            if method == "PUT"
            else _get(r, fresh, "interim_report")
        )
        r.expect_rejection(
            f"ac08.invalid_stage.{method.lower()}",
            "AC-08",
            f"{method} an invalid stage → 400 (P5-Q5)",
            resp,
            400,
            required=False,
        )
    r.set_clock(clock)


# -- AC-09 ------------------------------------------------------------------------------------


def _minute(n: int) -> str:
    start = datetime.fromisoformat(AC09_START)
    return (start + timedelta(minutes=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ac09(r: "Runner") -> None:
    """Reset; four state changes one minute apart by four users, a rejected request between the
    third and fourth; then the log's order, users, entities, timestamps and immutability."""
    reset = r.call("POST", "/api/v1/test/reset")
    if not r.expect_status("ac09.reset", "AC-09", "POST /test/reset before AC-09", reset, 204):
        return
    stamps = [_minute(i + 1) for i in range(4)]

    r.set_clock(stamps[0])
    rel = r.call(
        "POST",
        "/api/v1/releases",
        json={"product": "AuditGateway", "version": "1.0.0", "support_end_date": "2030-01-01"},
        headers={"X-User-Id": AC09_USERS[0]},
    )
    rid = (_json(rel) or {}).get("release_id") if rel.status_code == 201 else None
    r.set_clock(stamps[1])
    sbom = r.call(
        "PUT",
        f"/api/v1/releases/{rid}/sbom",
        content=r.fx.sbom_bytes,
        headers={"X-User-Id": AC09_USERS[1], "Content-Type": "application/json"},
    )
    r.set_clock(stamps[2])
    incident = {
        "cve_id": "CVE-2023-25577",
        "awareness_at": stamps[2],
        "classification": "mandatory",
        "rationale": "AC-09 audit check.",
    }
    inc = r.call("POST", "/api/v1/incidents", json=incident, headers={"X-User-Id": AC09_USERS[2]})
    iid = (_json(inc) or {}).get("incident_id") if inc.status_code == 201 else None
    count_before = len(_events(r)[1])
    rejected = r.call(
        "POST",
        "/api/v1/incidents",
        json={k: v for k, v in incident.items() if k != "rationale"},
        headers={"X-User-Id": "tester-ac09-rejected"},
    )
    count_after = len(_events(r)[1])
    r.set_clock(stamps[3])
    sub = r.call(
        "POST",
        f"/api/v1/incidents/{iid}/submissions",
        json={"stage": "early_warning", "submitted_at": stamps[3]},
        headers={"X-User-Id": AC09_USERS[3]},
    )
    steps_ok = (rel.status_code, sbom.status_code, inc.status_code, sub.status_code) == (
        201,
        200,
        201,
        201,
    )
    r.record(
        "ac09.steps",
        "AC-09",
        "Register, upload SBOM, open incident, record early warning",
        steps_ok,
        "201, 200, 201, 201",
        f"{rel.status_code}, {sbom.status_code}, {inc.status_code}, {sub.status_code}",
        sub,
    )
    r.record(
        "ac09.rejected_adds_nothing",
        "AC-09",
        "A rejected request (incident without rationale) adds no audit event",
        rejected.status_code == 400 and count_after == count_before,
        f"400 and {count_before} events",
        f"{rejected.status_code} and {count_after} events",
        rejected,
    )

    g, events = _events(r)
    dicts = [e for e in events if isinstance(e, dict)]
    r.record(
        "ac09.four_events",
        "AC-09",
        "The audit log has exactly four events",
        g.status_code == 200 and len(dicts) == len(events) == 4,
        "200, 4 events",
        f"{g.status_code}, {len(events)} events",
        g,
    )
    users = [e.get("user_id") for e in dicts]
    entities = [e.get("entity_id") for e in dicts]
    r.record(
        "ac09.order",
        "AC-09",
        "Events are in step order with each step's user and entity",
        users == list(AC09_USERS) and entities == [rid, rid, iid, iid],
        f"users {list(AC09_USERS)}, entities {[rid, rid, iid, iid]}",
        f"users {users}, entities {entities}",
        g,
    )
    times = [e.get("timestamp") for e in dicts]
    r.record(
        "ac09.timestamps",
        "AC-09",
        "Each event's timestamp is the clock at its step (±2 s)",
        len(times) == 4 and all(_close(t, s) for t, s in zip(times, stamps, strict=True)),
        f"{stamps}",
        f"{times}",
        g,
    )
    actions = [e.get("action") for e in dicts]
    r.record(
        "ac09.actions",
        "AC-09",
        "Action names follow the proposed vocabulary (P5-Q7)",
        actions == list(AC09_ACTIONS),
        f"{list(AC09_ACTIONS)}",
        f"{actions}",
        g,
        required=False,
    )
    types = [e.get("entity_type") for e in dicts]
    r.record(
        "ac09.entity_types",
        "AC-09",
        "entity_type is release or incident (P5-Q7)",
        types == list(AC09_ENTITY_TYPES),
        f"{list(AC09_ENTITY_TYPES)}",
        f"{types}",
        g,
        required=False,
    )

    refused = []
    for event in dicts:
        eid = event.get("event_id")
        for method in ("PATCH", "DELETE"):
            resp = r.call(
                method,
                f"/api/v1/audit-logs/{eid}",
                json={"user_id": "mallory"} if method == "PATCH" else None,
                headers={"X-User-Id": "mallory"},
            )
            refused.append(resp.status_code)
    _, after = _events(r)
    r.record(
        "ac09.immutable",
        "AC-09",
        "PATCH and DELETE on every event → 405, and the log is unchanged",
        bool(refused) and all(s == 405 for s in refused) and after == events,
        f"{len(dicts) * 2} × 405, log unchanged",
        f"{refused}, log {'unchanged' if after == events else 'CHANGED'}",
        g,
    )
