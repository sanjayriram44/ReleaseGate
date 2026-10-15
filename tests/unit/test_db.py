import sqlite3
from pathlib import Path

import pytest

from app.db import Database


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "t.db"))
    db.init_schema()
    return db


def _insert_event(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO audit_log(event_id, timestamp, user_id, action, entity_type, entity_id)"
        " VALUES ('e1', '2026-01-01T00:00:00Z', 'u', 'A', 'release', 'r1')"
    )


def test_audit_update_and_delete_blocked(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with db.transaction() as conn:
        _insert_event(conn)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        with db.transaction() as conn:
            conn.execute("UPDATE audit_log SET user_id = 'x'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        with db.transaction() as conn:
            conn.execute("DELETE FROM audit_log")


def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            _insert_event(conn)
            raise RuntimeError("boom")
    with db.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_reset_clears_audit_and_restores_triggers(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with db.transaction() as conn:
        _insert_event(conn)
    db.reset()
    with db.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
        _insert_event(conn)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        with db.transaction() as conn:
            conn.execute("DELETE FROM audit_log")


def test_old_database_without_sbom_stored_at_is_migrated(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE releases (
            release_id TEXT PRIMARY KEY, product TEXT NOT NULL, version TEXT NOT NULL,
            support_end_date TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE (product, version));
        CREATE TABLE components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            release_id TEXT NOT NULL REFERENCES releases(release_id) ON DELETE CASCADE,
            position INTEGER NOT NULL, name TEXT NOT NULL, version TEXT NOT NULL, purl TEXT);
        INSERT INTO releases VALUES ('r1', 'p', '1', '2030-01-01', '2026-01-01T00:00:00Z');
        INSERT INTO releases VALUES ('r2', 'p', '2', '2030-01-01', '2026-01-01T00:00:00Z');
        INSERT INTO components(release_id, position, name, version) VALUES ('r1', 0, 'a', '1');
        """
    )
    old.close()

    db = Database(str(path))
    db.init_schema()
    db.init_schema()  # idempotent
    with db.transaction() as conn:
        rows = {
            r["release_id"]: r["sbom_stored_at"]
            for r in conn.execute("SELECT release_id, sbom_stored_at FROM releases")
        }
    assert rows["r1"] is not None  # had components, so it counts as having an SBOM
    assert rows["r2"] is None
