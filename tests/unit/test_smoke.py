from pathlib import Path

import pytest

from app.main import create_app


def test_app_builds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings come from the environment, as in production, but the database goes to tmp_path
    # so the test never touches ./data.
    db = tmp_path / "smoke.db"
    monkeypatch.setenv("DB_PATH", str(db))
    assert create_app().title
    assert db.exists()


def test_only_the_fixture_vulnerability_source_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smoke.db"))
    monkeypatch.setenv("VULN_SOURCE", "osv_snapshot")
    with pytest.raises(ValueError, match="only 'fixture'"):
        create_app()
