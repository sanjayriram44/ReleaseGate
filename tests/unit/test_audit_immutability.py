"""G7, audit integrity (CLAUDE.md §0.2, §6.6): code-inspection evidence for AC-09.

No code changes or removes an audit row except the gated test reset, the only INSERT is
app.services.audit.record, and the triggers reject UPDATE and DELETE.

Limit: the scan reads SQL in string literals. SQL built from variables (an f-string table name)
would escape it; review rejects that, and none exists today.
"""

import ast
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db import Database

ROOT = Path(__file__).resolve().parents[2]
AUDIT = r"(?:audit_log|audit_no_update|audit_no_delete|audit_no_replace)\b"
WRITES = re.compile(
    r"\bUPDATE\s+(?:OR\s+\w+\s+)?" + AUDIT
    + r"|\bDELETE\s+FROM\s+" + AUDIT
    + r"|\bDROP\s+(?:TABLE|TRIGGER)\s+(?:IF\s+EXISTS\s+)?" + AUDIT
    + r"|\b(?:INSERT\s+OR\s+)?REPLACE\s+INTO\s+" + AUDIT
    + r"|\bALTER\s+TABLE\s+" + AUDIT,
    re.IGNORECASE,
)  # fmt: skip
INSERTS = re.compile(r"\bINSERT\s+(?:OR\s+\w+\s+)?INTO\s+audit_log\b", re.IGNORECASE)


def sql_strings(path: Path) -> Iterator[tuple[str, str]]:
    """(qualified function name or "<module>", string literal) for every string in a file."""
    tree = ast.parse(path.read_text())

    def walk(node: ast.AST, scope: str) -> Iterator[tuple[str, str]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                inner = child.name if scope == "<module>" else f"{scope}.{child.name}"
                yield from walk(child, inner)
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                yield scope, child.value
            else:
                yield from walk(child, scope)

    yield from walk(tree, "<module>")


def find(pattern: re.Pattern[str]) -> set[tuple[str, str]]:
    return {
        (str(path.relative_to(ROOT)), scope)
        for path in sorted((ROOT / "app").rglob("*.py"))
        for scope, text in sql_strings(path)
        if pattern.search(text)
    }


def test_only_the_gated_reset_changes_or_removes_audit_rows() -> None:
    # Positive control: the scan does see the reset's statements, and nothing else.
    assert find(WRITES) == {("app/db.py", "Database.reset")}


def test_the_only_insert_is_audit_record() -> None:
    assert find(INSERTS) == {("app/services/audit.py", "record")}


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit_log SET user_id = 'x'",
        "update OR ignore audit_log set x = 1",
        "DELETE FROM audit_log",
        "DROP TRIGGER IF EXISTS audit_no_delete",
        "DROP TABLE audit_log",
        "INSERT OR REPLACE INTO audit_log VALUES (1)",
        "REPLACE INTO audit_log VALUES (1)",
        "ALTER TABLE audit_log RENAME TO x",
    ],
)
def test_the_scan_recognises_writes(sql: str) -> None:
    assert WRITES.search(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log",
        "SELECT * FROM audit_log ORDER BY seq",
        "DELETE FROM report_data",
        "UPDATE vulnerability_source_state SET mode = 'available'",
    ],
)
def test_the_scan_ignores_reads_and_trigger_definitions(sql: str) -> None:
    assert not WRITES.search(sql)


def _db_with_event(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "g7.db"))  # production default: allow_reset=False
    db.init_schema()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO audit_log(event_id, timestamp, user_id, action, entity_type, entity_id)"
            " VALUES ('evt-1', '2026-11-20T09:00:00Z', 'u', 'RELEASE_REGISTERED', 'release',"
            " 'rel-1')"
        )
    return db


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit_log SET user_id = 'mallory'",
        "UPDATE audit_log SET timestamp = '2000-01-01T00:00:00Z' WHERE event_id = 'evt-1'",
        "DELETE FROM audit_log",
        "DELETE FROM audit_log WHERE event_id = 'evt-1'",
        "INSERT OR REPLACE INTO audit_log(seq, event_id, timestamp, user_id, action, entity_type,"
        " entity_id) VALUES (1, 'evt-1', 't', 'mallory', 'A', 'release', 'rel-1')",
    ],
)
def test_triggers_reject_changes(tmp_path: Path, sql: str) -> None:
    db = _db_with_event(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match="audit log is append-only"):
        with db.transaction() as conn:
            conn.execute(sql)
    with db.transaction() as conn:
        rows = conn.execute("SELECT event_id, user_id, timestamp FROM audit_log").fetchall()
    assert [tuple(r) for r in rows] == [("evt-1", "u", "2026-11-20T09:00:00Z")]


def test_replace_by_event_id_is_rejected_too(tmp_path: Path) -> None:
    db = _db_with_event(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match="audit log is append-only"):
        with db.transaction() as conn:
            conn.execute(
                "REPLACE INTO audit_log(event_id, timestamp, user_id, action, entity_type,"
                " entity_id) VALUES ('evt-1', 't', 'mallory', 'A', 'release', 'rel-1')"
            )


def test_new_entries_can_still_be_appended(tmp_path: Path) -> None:
    db = _db_with_event(tmp_path)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO audit_log(event_id, timestamp, user_id, action, entity_type, entity_id)"
            " VALUES ('evt-2', '2026-11-20T09:01:00Z', 'u', 'SBOM_STORED', 'release', 'rel-1')"
        )
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 2
