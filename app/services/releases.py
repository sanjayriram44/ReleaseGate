import sqlite3
import uuid
from datetime import date

from app.clock import Clock, format_utc
from app.errors import ApiError
from app.models import Release, ReleaseCreate
from app.services import audit


def support_status(end_date: date, clock: Clock) -> str:
    """Supported through the end of support_end_date (UTC). Computed on every read."""
    return "supported" if clock.now().date() <= end_date else "unsupported"


def to_release(row: sqlite3.Row, clock: Clock) -> Release:
    end = date.fromisoformat(row["support_end_date"])
    return Release(
        release_id=row["release_id"],
        product=row["product"],
        version=row["version"],
        support_end_date=end,
        support_status=support_status(end, clock),  # type: ignore[arg-type]
    )


def get_row(conn: sqlite3.Connection, release_id: str) -> sqlite3.Row:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM releases WHERE release_id = ?", (release_id,)
    ).fetchone()
    if row is None:
        raise ApiError(404, "RELEASE_NOT_FOUND", f"release {release_id} not found")
    return row


def register(conn: sqlite3.Connection, clock: Clock, user_id: str, body: ReleaseCreate) -> Release:
    release_id = f"rel-{uuid.uuid4().hex[:8]}"
    try:
        conn.execute(
            "INSERT INTO releases(release_id, product, version, support_end_date, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                release_id,
                body.product,
                body.version,
                body.support_end_date.isoformat(),
                format_utc(clock.now()),
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise ApiError(
            409,
            "RELEASE_EXISTS",
            f"release {body.product} {body.version} is already registered",
        ) from exc
    audit.record(
        conn,
        clock,
        user_id,
        "RELEASE_REGISTERED",
        "release",
        release_id,
        {
            "product": body.product,
            "version": body.version,
            "support_end_date": body.support_end_date.isoformat(),
        },
    )
    return to_release(get_row(conn, release_id), clock)
