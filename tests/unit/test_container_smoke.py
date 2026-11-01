"""scripts/container_smoke.py, run in-process: a restart is a fresh app on the same database."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def make_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "container_smoke", ROOT / "scripts/container_smoke.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["container_smoke"] = module
    spec.loader.exec_module(module)
    return module


def make_client(db: Path) -> TestClient:
    return TestClient(create_app(Settings(db_path=str(db), enable_test_endpoints=True)))


def test_seed_then_verify_after_restart(tmp_path: Path) -> None:
    smoke = make_module()
    db = tmp_path / "s.db"
    state = smoke.seed(make_client(db))
    assert state["incident"]["deadlines"]["early_warning"]["status"] == "met"
    assert len(state["components"]["components"]) == 25
    assert smoke.verify(make_client(db), state) == []


def test_verify_notices_a_change(tmp_path: Path) -> None:
    smoke = make_module()
    db = tmp_path / "s.db"
    state = smoke.seed(make_client(db))
    client = make_client(db)
    client.patch(
        f"/api/v1/incidents/{state['ids'][1]}",
        json={"fix_available_at": "2026-11-05T00:00:00Z"},
        headers=smoke.USER,
    )
    assert smoke.verify(client, state) == ["incident", "audit"]


def test_tester_passes_against_our_system(tmp_path: Path) -> None:
    smoke = make_module()
    assert smoke.run_tester(make_client(tmp_path / "t.db"))


def test_main_rejects_bad_arguments() -> None:
    assert make_module().main(["nope"]) == 2
