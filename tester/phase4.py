"""Phase 4 checks: incidents and deadlines (AC-06, AC-07) and the CVE query (AC-04, AC-05).

Required checks follow the shared contract and the AC text. Checks of the pod's Phase 4 answers
(docs/decisions.md, Q1-Q6; agreed with Team 2 on 2026-11-01) are informational, like the
Phase 3 decision checks, so they never fail another team's run. AC-04's expected results come
from fixtures/ground_truth.json, a DRAFT until one reviewer per team verifies it (decision Q7).
"""

import json
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from tester.checks import Runner

USER = {"X-User-Id": "releasegate-tester"}
AWARE = "2026-11-01T10:00:00Z"
CVE_LIMIT_S = 10.0  # AC-04
ERROR_LIMIT_S = 15.0  # AC-05
STORED = ("created_by", "classification", "awareness_at", "rationale")


def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


def _instant(value: Any) -> datetime | None:
    """Parse a returned timestamp; None if it isn't one. Compared as instants, not strings."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _at(base: str, **delta: float) -> str:
    dt = datetime.fromisoformat(base) + timedelta(**delta)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _deadline(incident: Any, stage: str) -> dict[str, Any]:
    if not isinstance(incident, dict) or not isinstance(incident.get("deadlines"), dict):
        return {}
    d = incident["deadlines"].get(stage)
    return d if isinstance(d, dict) else {}


def _error_code(resp: httpx.Response) -> str | None:
    body = _json(resp)
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        code = body["error"].get("code")
        return code if isinstance(code, str) else None
    return None


# -- AC-06, AC-07 ---------------------------------------------------------------------------


def _create(r: "Runner", body: dict[str, Any]) -> httpx.Response:
    return r.call("POST", "/api/v1/incidents", json=body, headers=USER)


def _audit_count(r: "Runner") -> int | None:
    events = (_json(r.call("GET", "/api/v1/audit-logs")) or {}).get("events")
    return len(events) if isinstance(events, list) else None


def ac06_ac07(r: "Runner") -> None:
    r.set_clock(AWARE)
    rationale = "Exploited in the wild.\n  Vendor advisory confirms it. "
    resp = _create(
        r,
        {
            "cve_id": "CVE-2023-25577",
            "awareness_at": AWARE,
            "classification": "mandatory",
            "rationale": rationale,
        },
    )
    inc = _json(resp) if resp.status_code == 201 else None
    aware = _instant((inc or {}).get("awareness_at"))
    want = _instant(AWARE)
    stored = (
        isinstance(inc, dict)
        and inc.get("created_by") == USER["X-User-Id"]
        and inc.get("classification") == "mandatory"
        and inc.get("rationale") == rationale
        and aware is not None
        and want is not None
        and abs((aware - want).total_seconds()) <= 2
    )
    r.record(
        "ac06.mandatory",
        "AC-06",
        "Mandatory incident stored with user, classification, UTC awareness (±2 s), rationale",
        stored,
        f"201, created_by={USER['X-User-Id']}, classification=mandatory, awareness_at≈{AWARE},"
        " rationale unchanged",
        f"{resp.status_code}, {json.dumps({k: (inc or {}).get(k) for k in STORED})}",
        resp,
    )
    iid = inc.get("incident_id") if isinstance(inc, dict) else None
    if isinstance(inc, dict) and isinstance(iid, str):
        g = r.call("GET", f"/api/v1/incidents/{iid}")
        same = _json(g) or {}
        r.record(
            "ac06.read",
            "AC-06",
            "GET the incident returns the same stored fields",
            g.status_code == 200
            and all(
                same.get(k) == inc.get(k) for k in ("created_by", "classification", "rationale")
            )
            and _instant(same.get("awareness_at")) == aware,
            "200 with the same created_by, classification, awareness_at, rationale",
            f"{g.status_code}",
            g,
        )

    resp = _create(
        r, {"awareness_at": AWARE, "classification": "voluntary", "rationale": "Voluntary report."}
    )
    vol = _json(resp) if resp.status_code == 201 else {}
    r.record(
        "ac06.voluntary",
        "AC-06",
        "Voluntary incident stored with its classification",
        resp.status_code == 201 and (vol or {}).get("classification") == "voluntary",
        "201, classification=voluntary",
        f"{resp.status_code}, classification={(vol or {}).get('classification')}",
        resp,
    )
    statuses = {s: _deadline(vol, s).get("status") for s in ("early_warning", "final_report")}
    r.record(
        "info.voluntary_not_applicable",
        "provisional",
        "Voluntary incident: every deadline not_applicable (decision Q2)",
        set(statuses.values()) == {"not_applicable"},
        "not_applicable",
        str(statuses),
        resp,
        required=False,
    )

    before = _audit_count(r)
    for cid, body, title in (
        (
            "ac06.missing_rationale",
            {"awareness_at": AWARE, "classification": "mandatory"},
            "Missing rationale → 400",
        ),
        (
            "ac06.bad_classification",
            {"awareness_at": AWARE, "classification": "urgent", "rationale": "r"},
            "Invalid classification → 400",
        ),
    ):
        r.expect_rejection(cid, "AC-06", title, _create(r, body), 400)
    after = _audit_count(r)
    r.record(
        "info.rejected_not_stored",
        "provisional",
        "Rejected incidents stored nothing (audit log unchanged)",
        before is not None and before == after,
        f"{before} audit events",
        f"{after} audit events",
        required=False,
    )
    _ac07(r)


def _ac07(r: "Runner") -> None:
    ew, vn = _at(AWARE, hours=24), _at(AWARE, hours=72)
    r.set_clock(AWARE)
    resp = _create(
        r,
        {"awareness_at": AWARE, "classification": "mandatory", "rationale": "AC-07 deadlines."},
    )
    inc = _json(resp) if resp.status_code == 201 else None
    iid = inc.get("incident_id") if isinstance(inc, dict) else None
    got = {
        s: _instant(_deadline(inc, s).get("deadline_at"))
        for s in ("early_warning", "vulnerability_notification")
    }
    r.record(
        "ac07.initial",
        "AC-07",
        "Mandatory incident: early warning at +24 h, notification at +72 h, both pending",
        got == {"early_warning": _instant(ew), "vulnerability_notification": _instant(vn)}
        and _deadline(inc, "early_warning").get("status") == "pending"
        and _deadline(inc, "vulnerability_notification").get("status") == "pending",
        f"early_warning {ew} pending, vulnerability_notification {vn} pending",
        f"{resp.status_code}, {json.dumps((inc or {}).get('deadlines'))}",
        resp,
    )
    r.record(
        "ac07.final_before_fix",
        "AC-07",
        "Final report has no deadline before fix_available_at",
        isinstance(inc, dict) and _deadline(inc, "final_report").get("deadline_at") is None,
        "final_report.deadline_at = null",
        str(_deadline(inc, "final_report").get("deadline_at")),
        resp,
    )
    if not isinstance(iid, str):
        return

    def submit(stage: str, at: str) -> httpx.Response:
        return r.call(
            "POST",
            f"/api/v1/incidents/{iid}/submissions",
            json={"stage": stage, "submitted_at": at},
            headers=USER,
        )

    r.set_clock(ew)
    s = submit("early_warning", ew)
    r.record(
        "ac07.early_warning_met",
        "AC-07",
        "Early warning recorded exactly at +24 h → met",
        s.status_code == 201 and _deadline(_json(s), "early_warning").get("status") == "met",
        "201, early_warning.status=met",
        f"{s.status_code}, {_deadline(_json(s), 'early_warning').get('status')}",
        s,
    )

    r.set_clock(vn)
    g = r.call("GET", f"/api/v1/incidents/{iid}")
    status = _deadline(_json(g), "vulnerability_notification").get("status")
    r.record(
        "info.pending_at_deadline",
        "provisional",
        "Notification still pending exactly at +72 h (decision Q2)",
        status == "pending",
        "pending",
        str(status),
        g,
        required=False,
    )
    r.set_clock(_at(AWARE, hours=72, seconds=1))
    g = r.call("GET", f"/api/v1/incidents/{iid}")
    status = _deadline(_json(g), "vulnerability_notification").get("status")
    r.record(
        "ac07.notification_overdue",
        "AC-07",
        "No notification at 72 h + 1 s → overdue",
        g.status_code == 200 and status == "overdue",
        "200, vulnerability_notification.status=overdue",
        f"{g.status_code}, {status}",
        g,
    )

    fix = _at(AWARE, days=4)
    p = r.call("PATCH", f"/api/v1/incidents/{iid}", json={"fix_available_at": fix}, headers=USER)
    due = _instant(_deadline(_json(p), "final_report").get("deadline_at"))
    r.record(
        "ac07.final_deadline",
        "AC-07",
        "fix_available_at sets the final report deadline to +14 days",
        p.status_code == 200 and due == _instant(_at(fix, days=14)),
        f"200, final_report.deadline_at={_at(fix, days=14)}",
        f"{p.status_code}, {due}",
        p,
    )
    s = submit("final_report", _at(fix, days=13))
    r.record(
        "ac07.final_met",
        "AC-07",
        "Final report 13 days after the fix → met",
        s.status_code == 201 and _deadline(_json(s), "final_report").get("status") == "met",
        "201, final_report.status=met",
        f"{s.status_code}, {_deadline(_json(s), 'final_report').get('status')}",
        s,
    )

    s = submit("early_warning", ew)
    r.record(
        "info.duplicate_submission",
        "provisional",
        "Second early warning → 409 (decision Q2, contract addition)",
        s.status_code == 409,
        "409",
        str(s.status_code),
        s,
        required=False,
    )
    s = submit("vulnerability_notification", _at(AWARE, hours=73))
    r.record(
        "info.late_submission_overdue",
        "provisional",
        "Late notification stays overdue with submitted_at set (decision Q2)",
        _deadline(_json(s), "vulnerability_notification").get("status") == "overdue"
        and _deadline(_json(s), "vulnerability_notification").get("submitted_at") is not None,
        "201, overdue, submitted_at set",
        f"{s.status_code}, {_deadline(_json(s), 'vulnerability_notification')}",
        s,
        required=False,
    )


# -- AC-04, AC-05 ---------------------------------------------------------------------------


def _query(r: "Runner", cve: str) -> tuple[httpx.Response, float]:
    t0 = time.monotonic()
    resp = r.call("GET", f"/api/v1/vulnerabilities/{cve}/affected-releases")
    return resp, time.monotonic() - t0


def _load_source(r: "Runner", mode: str, records: list[dict[str, Any]]) -> httpx.Response:
    return r.call(
        "PUT", "/api/v1/test/vulnerability-source", json={"mode": mode, "records": records}
    )


def _as_sets(body: Any, keys: dict[str, str]) -> dict[str, set[tuple[str, frozenset[str]]]]:
    out: dict[str, set[tuple[str, frozenset[str]]]] = {}
    for group in ("supported", "unsupported"):
        entries = body.get(group) if isinstance(body, dict) else None
        out[group] = {
            (
                keys.get(str(e.get("release_id")), str(e.get("release_id"))),
                frozenset(
                    str(c.get("purl"))
                    for c in e.get("matched_components") or []
                    if isinstance(c, dict)
                ),
            )
            for e in entries or []
            if isinstance(e, dict)
        }
    return out


def _fmt(sets: dict[str, set[tuple[str, frozenset[str]]]]) -> str:
    return "; ".join(
        f"{g}: " + ", ".join(f"{k} {sorted(p)}" for k, p in sorted(v)) for g, v in sets.items()
    )


def ac04_ac05(r: "Runner") -> None:
    fx = r.fx.cve
    r.call("POST", "/api/v1/test/reset")
    r.set_clock(fx.dataset["reference_clock"])
    keys: dict[str, str] = {}
    seeded = True
    for rel in fx.dataset["releases"]:
        resp = r.register(rel["request"])
        rid = (_json(resp) or {}).get("release_id")
        if resp.status_code != 201 or not isinstance(rid, str):
            seeded = False
            continue
        keys[rid] = rel["key"]
        if rel["sbom_file"]:
            seeded &= r.put_sbom(rid, fx.sboms[rel["sbom_file"]]).status_code == 200
    resp = _load_source(r, "available", fx.records)
    seeded &= resp.status_code == 200
    r.record(
        "ac04.seed",
        "AC-04",
        "CVE dataset seeded: releases, SBOMs, vulnerability records",
        seeded,
        "every release 201, every SBOM 200, PUT /test/vulnerability-source 200",
        "ok" if seeded else "a seeding call failed",
        resp,
    )
    if not seeded:
        return

    note = "Expected values: fixtures/ground_truth.json, a DRAFT until verified (decision Q7)."
    for case in fx.truth["cves"]:
        cve = case["cve_id"]
        resp, secs = _query(r, cve)
        want = {
            g: {(e["release"], frozenset(e["matched_purls"])) for e in case[g]}
            for g in ("supported", "unsupported")
        }
        got = _as_sets(_json(resp), keys)
        empty = not case["supported"] and not case["unsupported"]
        r.record(
            f"{'ac05.no_match' if empty else 'ac04.' + cve}",
            "AC-05" if empty else "AC-04",
            f"{cve}: affected releases grouped by support status within {CVE_LIMIT_S:.0f} s"
            if not empty
            else f"{cve} (known, nothing affected) → 200 with empty arrays",
            resp.status_code == 200 and got == want and secs <= CVE_LIMIT_S,
            f"200 in ≤ {CVE_LIMIT_S:.0f} s; {_fmt(want)}",
            f"{resp.status_code} in {secs:.2f} s; {_fmt(got)}",
            resp,
            note=note,
        )

    for case, title in ((fx.truth["unknown_cve"], "Unknown CVE → 404 CVE_UNKNOWN"),):
        resp, secs = _query(r, case["cve_id"])
        r.record(
            "ac05.unknown",
            "AC-05",
            f"{title} within {ERROR_LIMIT_S:.0f} s",
            resp.status_code == case["expect_status"]
            and _error_code(resp) == case["expect_code"]
            and secs <= ERROR_LIMIT_S,
            f"{case['expect_status']} {case['expect_code']} in ≤ {ERROR_LIMIT_S:.0f} s",
            f"{resp.status_code} {_error_code(resp)} in {secs:.2f} s",
            resp,
        )

    resp, _ = _query(r, "CVE-26-1")
    r.record(
        "info.malformed_cve",
        "provisional",
        "Malformed CVE ID → 400 (decision Q4, contract addition)",
        resp.status_code == 400,
        "400",
        str(resp.status_code),
        resp,
        required=False,
    )

    case = fx.truth["unreachable"]
    _load_source(r, "unreachable", fx.records)
    resp, secs = _query(r, case["cve_id"])
    r.record(
        "ac05.unreachable",
        "AC-05",
        f"Source unreachable → 503 {case['expect_code']} within {ERROR_LIMIT_S:.0f} s",
        resp.status_code == case["expect_status"]
        and _error_code(resp) == case["expect_code"]
        and secs <= ERROR_LIMIT_S,
        f"{case['expect_status']} {case['expect_code']} in ≤ {ERROR_LIMIT_S:.0f} s",
        f"{resp.status_code} {_error_code(resp)} in {secs:.2f} s",
        resp,
    )
    _load_source(r, "available", [])
