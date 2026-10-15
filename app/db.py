import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS releases (
    release_id TEXT PRIMARY KEY,
    product TEXT NOT NULL,
    version TEXT NOT NULL,
    support_end_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (product, version)
);
CREATE TABLE IF NOT EXISTS components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    release_id TEXT NOT NULL REFERENCES releases(release_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    purl TEXT
);
CREATE INDEX IF NOT EXISTS idx_components_release ON components(release_id, position);
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details TEXT
);
"""

AUDIT_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        # isolation_level=None: autocommit; transactions are explicit via transaction().
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_schema(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(SCHEMA + AUDIT_TRIGGERS)
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """One atomic unit of work: commits on success, rolls back on any exception."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")
        finally:
            conn.close()

    def reset(self) -> None:
        """Test reset: wipe all data including the audit log, then restore the triggers."""
        with self.transaction() as conn:
            conn.execute("DROP TRIGGER IF EXISTS audit_no_update")
            conn.execute("DROP TRIGGER IF EXISTS audit_no_delete")
            conn.execute("DELETE FROM components")
            conn.execute("DELETE FROM releases")
            conn.execute("DELETE FROM audit_log")
            conn.execute("DELETE FROM sqlite_sequence")
            for stmt in AUDIT_TRIGGERS.split("END;"):
                if stmt.strip():
                    conn.execute(stmt + "END;")
