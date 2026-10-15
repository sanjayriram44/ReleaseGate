import sqlite3

from app.clock import Clock, format_utc
from app.models import Component
from app.services import audit
from app.services.releases import get_row
from app.services.sbom_validation import ParsedComponent


def replace_components(
    conn: sqlite3.Connection,
    clock: Clock,
    user_id: str,
    release_id: str,
    components: list[ParsedComponent],
) -> int:
    """Atomically swap a release's components; the caller owns the transaction."""
    row = get_row(conn, release_id)
    replaced = row["sbom_stored_at"] is not None
    conn.execute("DELETE FROM components WHERE release_id = ?", (release_id,))
    conn.executemany(
        "INSERT INTO components(release_id, position, name, version, purl) VALUES (?, ?, ?, ?, ?)",
        [(release_id, i, c.name, c.version, c.purl) for i, c in enumerate(components)],
    )
    conn.execute(
        "UPDATE releases SET sbom_stored_at = ? WHERE release_id = ?",
        (format_utc(clock.now()), release_id),
    )
    audit.record(
        conn,
        clock,
        user_id,
        "SBOM_REPLACED" if replaced else "SBOM_STORED",
        "release",
        release_id,
        {"component_count": len(components)},
    )
    return len(components)


def list_components(conn: sqlite3.Connection, release_id: str) -> list[Component]:
    rows = conn.execute(
        "SELECT name, version, purl FROM components WHERE release_id = ? ORDER BY position",
        (release_id,),
    ).fetchall()
    return [Component(name=r["name"], version=r["version"], purl=r["purl"]) for r in rows]
