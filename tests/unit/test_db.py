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
