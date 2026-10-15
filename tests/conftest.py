from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(Settings(db_path=str(tmp_path / "test.db"), enable_test_endpoints=True))
    with TestClient(app) as c:
        yield c
