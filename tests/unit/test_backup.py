"""Nightly SQLite backup with the online backup API, keeping 7 copies (CLAUDE.md §8)."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import backup
from app.config import Settings
from app.main import create_app

NOW = datetime(2026, 10, 31, 3, 30, 0, tzinfo=UTC)


def make_db(path: Path) -> Path:
    app = create_app(Settings(db_path=str(path)))
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/releases",
            json={"product": "P", "version": "1", "support_end_date": "2030-01-01"},
            headers={"X-User-Id": "alice"},
        )
        assert r.status_code == 201
    return path


def test_backup_is_a_complete_named_copy(tmp_path: Path) -> None:
    db = make_db(tmp_path / "live.db")
    out = tmp_path / "backups"
    path = backup.run(db, out, keep=7, now=NOW)
    assert path == out / "releasegate-20261031T033000Z.db"
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert conn.execute("SELECT product, version FROM releases").fetchall() == [("P", "1")]
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone() == (1,)
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert sorted(p.name for p in out.iterdir()) == [path.name]  # no temporary file left


def test_keeps_only_the_newest_copies(tmp_path: Path) -> None:
    db = make_db(tmp_path / "live.db")
    out = tmp_path / "backups"
    out.mkdir()
    for day in range(20, 28):  # 8 older nightly copies
        (out / f"releasegate-202610{day}T033000Z.db").write_bytes(b"old")
    (out / "notes.txt").write_text("not a backup")
    backup.run(db, out, keep=7, now=NOW)
    assert sorted(p.name for p in out.iterdir()) == [
        "notes.txt",
        *(f"releasegate-202610{day}T033000Z.db" for day in range(22, 28)),
        "releasegate-20261031T033000Z.db",
    ]


def test_missing_database_fails_and_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "backups"
    with pytest.raises(sqlite3.OperationalError):
        backup.run(tmp_path / "absent.db", out, keep=7, now=NOW)
    assert not (tmp_path / "absent.db").exists()  # opened read-only, never created
    assert not out.exists() or list(out.iterdir()) == []


def test_failed_integrity_check_keeps_older_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = make_db(tmp_path / "live.db")
    out = tmp_path / "backups"
    out.mkdir()
    old = out / "releasegate-20261030T033000Z.db"
    old.write_bytes(b"old")
    monkeypatch.setattr(backup, "_integrity", lambda path: "database disk image is malformed")
    with pytest.raises(backup.BackupError, match="malformed"):
        backup.run(db, out, keep=1, now=NOW)
    assert list(out.iterdir()) == [old]


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = make_db(tmp_path / "live.db")
    out = tmp_path / "backups"
    assert backup.main([str(db), str(out), "--keep", "7"]) == 0
    [made] = list(out.iterdir())
    assert made.name.startswith("releasegate-") and str(made) in capsys.readouterr().out
    assert backup.main([str(tmp_path / "absent.db"), str(out)]) == 1
    assert "backup failed" in capsys.readouterr().err
    assert backup.main([str(db), str(out), "--keep", "0"]) == 2
