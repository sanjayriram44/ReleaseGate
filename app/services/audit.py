import json
import sqlite3
import uuid
from typing import Any

from app.clock import Clock, format_utc


def record(
    conn: sqlite3.Connection,
    clock: Clock,
    user_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Append an audit row inside the caller's transaction (never commits on its own)."""
    conn.execute(
        "INSERT INTO audit_log(event_id, timestamp, user_id, action, entity_type, entity_id,"
        " details) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            f"evt-{uuid.uuid4().hex[:12]}",
            format_utc(clock.now()),
            user_id,
            action,
            entity_type,
            entity_id,
            json.dumps(details) if details is not None else None,
        ),
    )
