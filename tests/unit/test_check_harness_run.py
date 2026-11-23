"""scripts/check_harness_run.py passes our own tester and system, and catches a broken report."""

import importlib.util
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app as create_system
from tester.main import create_app as create_tester

spec = importlib.util.spec_from_file_location("check_harness_run", "scripts/check_harness_run.py")
assert spec and spec.loader
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


def _clients(tmp_path: Path) -> tuple[TestClient, TestClient]:
    system = TestClient(
        create_system(Settings(db_path=str(tmp_path / "s.db"), enable_test_endpoints=True))
    )
    tester = TestClient(
        create_tester("fixtures", client_factory=lambda _: system, host_check=lambda _: None)
    )
    return tester, system


def test_our_own_tester_and_system_pass(tmp_path: Path) -> None:
    tester, system = _clients(tmp_path)
    assert script.check(tester, "http://our-system:8080", own=True, system=system) == []


def test_missing_model_coverage_is_caught(tmp_path: Path) -> None:
    tester, system = _clients(tmp_path)
    problems: list[Any] = script.check(tester, "http://our-system:8080", own=False, system=system)
    assert any("coverage: expected keys" in p for p in problems)
