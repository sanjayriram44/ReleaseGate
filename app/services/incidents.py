"""Incident cases (REQ-05, REQ-06, REQ-08). Only timestamps are stored; deadlines are computed
on every read by app.services.deadlines. Awareness and classification come from a person; the
system never infers them."""

import sqlite3
import uuid
from datetime import datetime

from app.clock import Clock, format_utc, parse_utc
from app.errors import ApiError
from app.models import Deadline, Deadlines, FixAvailable, Incident, IncidentCreate, SubmissionCreate
from app.services import audit, deadlines


def get_row(conn: sqlite3.Connection, incident_id: str) -> sqlite3.Row:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
    ).fetchone()
    if row is None:
        raise ApiError(404, "INCIDENT_NOT_FOUND", f"incident {incident_id} not found")
    return row


def _submissions(conn: sqlite3.Connection, incident_id: str) -> dict[str, datetime]:
    rows = conn.execute(
        "SELECT stage, submitted_at FROM submissions WHERE incident_id = ?", (incident_id,)
    ).fetchall()
    return {r["stage"]: parse_utc(r["submitted_at"]) for r in rows}


def _fix(row: sqlite3.Row) -> datetime | None:
    return parse_utc(row["fix_available_at"]) if row["fix_available_at"] else None


def _ts(dt: datetime | None) -> str | None:
    return format_utc(dt) if dt is not None else None


def to_incident(conn: sqlite3.Connection, row: sqlite3.Row, clock: Clock) -> Incident:
    computed = deadlines.compute(
        row["classification"],
        parse_utc(row["awareness_at"]),
        _fix(row),
        _submissions(conn, row["incident_id"]),
        clock.now(),
    )
    out = {
        stage: Deadline(
            deadline_at=_ts(d.deadline_at), submitted_at=_ts(d.submitted_at), status=d.status
        )
        for stage, d in computed.items()
    }
    return Incident(
        incident_id=row["incident_id"],
        cve_id=row["cve_id"],
        awareness_at=row["awareness_at"],
        created_by=row["created_by"],
        classification=row["classification"],
        rationale=row["rationale"],
        fix_available_at=row["fix_available_at"],
        deadlines=Deadlines(**out),
    )


def create(conn: sqlite3.Connection, clock: Clock, user_id: str, body: IncidentCreate) -> Incident:
    awareness = format_utc(parse_utc(body.awareness_at, "awareness_at"))
    incident_id = f"inc-{uuid.uuid4().hex[:8]}"
    conn.execute(
        "INSERT INTO incidents(incident_id, cve_id, awareness_at, created_by, classification,"
        " rationale, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            incident_id,
            body.cve_id,
            awareness,
            user_id,
            body.classification,
            body.rationale,
            format_utc(clock.now()),
        ),
    )
    audit.record(
        conn,
        clock,
        user_id,
        "INCIDENT_CREATED",
        "incident",
        incident_id,
        {"cve_id": body.cve_id, "classification": body.classification, "awareness_at": awareness},
    )
    return to_incident(conn, get_row(conn, incident_id), clock)


def _not_before_awareness(row: sqlite3.Row, value: datetime, field: str) -> None:
    # Decision Q3: earlier than awareness_at is rejected; later than now is allowed.
    if value < parse_utc(row["awareness_at"]):
        raise ApiError(400, "INVALID_REQUEST", f"{field} must not be earlier than awareness_at")


def record_fix(
    conn: sqlite3.Connection, clock: Clock, user_id: str, incident_id: str, body: FixAvailable
) -> Incident:
    row = get_row(conn, incident_id)
    fix = parse_utc(body.fix_available_at, "fix_available_at")
    _not_before_awareness(row, fix, "fix_available_at")
    # Decision Q3: a second value overwrites the first (audited again); stored on voluntary
    # incidents too, where every deadline stays not_applicable.
    conn.execute(
        "UPDATE incidents SET fix_available_at = ? WHERE incident_id = ?",
        (format_utc(fix), incident_id),
    )
    audit.record(
        conn,
        clock,
        user_id,
        "FIX_AVAILABLE_RECORDED",
        "incident",
        incident_id,
        {"fix_available_at": format_utc(fix), "previous": row["fix_available_at"]},
    )
    return to_incident(conn, get_row(conn, incident_id), clock)


def record_submission(
    conn: sqlite3.Connection,
    clock: Clock,
    user_id: str,
    incident_id: str,
    body: SubmissionCreate,
) -> Incident:
    row = get_row(conn, incident_id)
    submitted = parse_utc(body.submitted_at, "submitted_at")
    _not_before_awareness(row, submitted, "submitted_at")
    due = deadlines.deadline_at(
        body.stage, row["classification"], parse_utc(row["awareness_at"]), _fix(row)
    )
    if due is None:  # decision Q2: voluntary case, or a final report before a fix
        raise ApiError(
            400,
            "INVALID_REQUEST",
            f"{body.stage} is not_applicable for this incident"
            + (
                " (voluntary)" if row["classification"] == "voluntary" else " (no fix_available_at)"
            ),
        )
    try:
        conn.execute(
            "INSERT INTO submissions(incident_id, stage, submitted_at, recorded_by, recorded_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (incident_id, body.stage, format_utc(submitted), user_id, format_utc(clock.now())),
        )
    except sqlite3.IntegrityError as exc:  # decision Q2: one submission per stage
        raise ApiError(
            409, "SUBMISSION_EXISTS", f"{body.stage} has already been submitted for this incident"
        ) from exc
    audit.record(
        conn,
        clock,
        user_id,
        "SUBMISSION_RECORDED",
        "incident",
        incident_id,
        {"stage": body.stage, "submitted_at": format_utc(submitted)},
    )
    return to_incident(conn, row, clock)
