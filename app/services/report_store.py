"""Storing and loading report data (REQ-07, REQ-08). The rules live in app.services.reports."""

import json
import sqlite3
from typing import Any

from app.clock import Clock, format_utc
from app.services import audit


def load(conn: sqlite3.Connection, incident_id: str, stage: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT data FROM report_data WHERE incident_id = ? AND stage = ?", (incident_id, stage)
    ).fetchone()
    if row is None:
        return None
    data: dict[str, Any] = json.loads(row["data"])
    return data


def store(
    conn: sqlite3.Connection,
    clock: Clock,
    user_id: str,
    incident_id: str,
    stage: str,
    data: dict[str, Any],
) -> None:
    """Replace the stage's data as a whole and audit it, inside the caller's transaction. The
    audit entry names the supplied fields, never their text."""
    conn.execute(
        "INSERT INTO report_data(incident_id, stage, data, updated_by, updated_at)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT (incident_id, stage) DO UPDATE SET"
        " data = excluded.data, updated_by = excluded.updated_by,"
        " updated_at = excluded.updated_at",
        (incident_id, stage, json.dumps(data), user_id, format_utc(clock.now())),
    )
    audit.record(
        conn,
        clock,
        user_id,
        "REPORT_DATA_STORED",
        "incident",
        incident_id,
        {"stage": stage, "fields": sorted(data)},
    )
