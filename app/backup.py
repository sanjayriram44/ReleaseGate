"""Back up the SQLite database with the online backup API and keep the newest copies (§8).

    python -m app.backup <db_path> <out_dir> [--keep 7]

Safe while the service is running: the backup API copies a consistent snapshot, and the source
is opened read-only, so a wrong path fails instead of creating an empty database. The copy is
written under a temporary name as one self-contained file (no WAL), must pass PRAGMA
integrity_check, and is then renamed to releasegate-<UTC timestamp>.db. Only then are copies
beyond --keep deleted, oldest first; a failed backup leaves the older copies alone.
deploy/backup.sh runs this nightly on the VM.
"""

import argparse
import os
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

from app.clock import Clock

_NAME = re.compile(r"^releasegate-\d{8}T\d{6}Z\.db$")


class BackupError(Exception):
    pass


def _integrity(path: Path) -> str:
    with closing(sqlite3.connect(path)) as conn:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])


def run(db_path: Path, out_dir: Path, keep: int = 7, now: datetime | None = None) -> Path:
    """Write one backup into out_dir, prune to the newest `keep`, and return its path."""
    stamp = (now or Clock().now()).strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / f"releasegate-{stamp}.db"
    with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)) as src:
        src.execute("SELECT 1 FROM sqlite_master LIMIT 1")  # fail here if it can't be read
        out_dir.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".tmp")
        try:
            with closing(sqlite3.connect(partial)) as dst:
                src.backup(dst)
                # One self-contained file (no -wal/-shm), so restoring is a plain copy.
                dst.execute("PRAGMA journal_mode=DELETE")
            result = _integrity(partial)
            if result != "ok":
                raise BackupError(f"integrity check failed on the copy: {result}")
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)
    copies = sorted((p for p in out_dir.iterdir() if _NAME.match(p.name)), reverse=True)
    for old in copies[keep:]:
        old.unlink()
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("db_path", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--keep", type=int, default=7)
    args = parser.parse_args(argv)
    if args.keep < 1:
        print("--keep must be at least 1", file=sys.stderr)
        return 2
    try:
        path = run(args.db_path, args.out_dir, args.keep)
    except (sqlite3.Error, OSError, BackupError) as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
