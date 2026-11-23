"""GET /health (our own endpoint): 503 with the reason when the database can't be written."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_is_503_when_the_database_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(Settings(db_path=str(tmp_path / "h.db"), enable_test_endpoints=True))
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"

        @contextmanager
        def broken() -> Iterator[Any]:
            raise OSError("disk I/O error")
            yield  # pragma: no cover

        monkeypatch.setattr(app.state.db, "transaction", broken)
        r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "unavailable" and "disk I/O error" in r.json()["detail"]
