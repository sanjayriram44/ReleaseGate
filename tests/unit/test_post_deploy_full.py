"""scripts/post_deploy_full.py: the destructive --full post-deploy run (CLAUDE.md §8), in-process.

A restart is a fresh app on the same database file; smoke.sh is replaced by a stub.
"""

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from scripts import post_deploy_full as full
from scripts.post_deploy_check import Check, main

ROOT = Path(__file__).resolve().parents[2]
SHA = "0123456789abcdef0123456789abcdef01234567"


class Target:
    """Our system on one database file; restart() starts a fresh app on the same file."""

    def __init__(self, db: Path) -> None:
        self.db = db
        self.restarts = 0

    def connect(self) -> TestClient:
        settings = Settings(db_path=str(self.db), enable_test_endpoints=True, commit=SHA)
        return TestClient(create_app(settings))

    def restart(self) -> tuple[bool, str]:
        self.restarts += 1
        return True, "restarted in-process"


def healthy() -> Check:
    return Check("health", "PASS", "ok")


def smoke_ok() -> tuple[bool, str]:
    return True, "ALL CHECKS PASSED"


def outcomes(result: full.FullResult) -> dict[str, str]:
    return {c.name: c.outcome for c in result.checks}


def test_full_run_passes_on_our_system(tmp_path: Path) -> None:
    target = Target(tmp_path / "s.db")
    result = full.run_full(target.connect, smoke_ok, target.restart, healthy)
    assert outcomes(result) == {
        "tester": "PASS",
        "smoke": "PASS",
        "ac10-restart": "PASS",
        "reseed": "PASS",
    }
    assert target.restarts == 1
    assert result.tester is not None and result.tester.result == "pass"
    assert result.ac10 == "PASS"
    cve, err = result.latency
    assert cve is not None and err is not None and cve < 10 and err < 15


def test_reseed_leaves_demo_data_at_real_time(tmp_path: Path) -> None:
    target = Target(tmp_path / "s.db")
    full.run_full(target.connect, smoke_ok, target.restart, healthy)
    client = target.connect()
    events = client.get("/api/v1/audit-logs").json()["events"]
    actions = [e["action"] for e in events]
    assert actions[:3] == ["RELEASE_REGISTERED", "SBOM_STORED", "INCIDENT_CREATED"]
    assert actions.count("REPORT_DATA_STORED") == 2
    now = datetime.now(UTC)
    for e in events:  # stamped with real time, not a test clock
        stamp = datetime.fromisoformat(e["timestamp"])
        assert abs((now - stamp).total_seconds()) < 120
    r = client.get("/api/v1/vulnerabilities/CVE-2023-25577/affected-releases")
    assert [rel["product"] for rel in r.json()["supported"]] == ["ExampleGateway"]


def test_without_a_restart_command_ac10_is_skipped(tmp_path: Path) -> None:
    target = Target(tmp_path / "s.db")
    result = full.run_full(target.connect, smoke_ok, None, healthy)
    assert outcomes(result)["ac10-restart"] == "SKIP" and result.ac10 == "SKIP"
    assert outcomes(result)["reseed"] == "PASS"


def test_failed_restart_fails_ac10_and_still_reseeds(tmp_path: Path) -> None:
    target = Target(tmp_path / "s.db")
    result = full.run_full(target.connect, smoke_ok, lambda: (False, "ssh: timed out"), healthy)
    assert outcomes(result)["ac10-restart"] == "FAIL" and "ssh" in result.checks[2].detail
    assert outcomes(result)["reseed"] == "PASS"


def test_unhealthy_after_restart_fails_ac10(tmp_path: Path) -> None:
    target = Target(tmp_path / "s.db")
    result = full.run_full(
        target.connect, smoke_ok, target.restart, lambda: Check("health", "FAIL", "no answer")
    )
    assert outcomes(result)["ac10-restart"] == "FAIL"


def test_lost_state_after_restart_fails_ac10(tmp_path: Path) -> None:
    first, second = Target(tmp_path / "a.db"), Target(tmp_path / "b.db")
    clients = iter([first.connect(), first.connect(), second.connect(), first.connect()])
    result = full.run_full(lambda: next(clients), smoke_ok, first.restart, healthy)
    assert outcomes(result)["ac10-restart"] == "FAIL"
    assert result.ac10 == "FAIL"


def test_failed_smoke_fails(tmp_path: Path) -> None:
    target = Target(tmp_path / "s.db")
    result = full.run_full(target.connect, lambda: (False, "2 CHECK(S) FAILED"), None, healthy)
    assert outcomes(result)["smoke"] == "FAIL"


def test_latency_is_read_from_the_tester_checks() -> None:
    class C:
        def __init__(self, ac: str, actual: str) -> None:
            self.ac, self.actual = ac, actual

    class R:
        checks = [
            C("AC-04", "200 in 0.12 s; ..."),
            C("AC-04", "200 in 1.50 s; ..."),
            C("AC-05", "503 VULNERABILITY_SOURCE_UNREACHABLE in 0.40 s"),
            C("AC-06", "201 in 9.99 s"),
        ]

    assert full.latency(R()) == (1.5, 0.4)  # type: ignore[arg-type]
    R.checks = []
    assert full.latency(R()) == (None, None)  # type: ignore[arg-type]


def load_metrics() -> ModuleType:
    spec = importlib.util.spec_from_file_location("metrics_for_full", ROOT / "scripts/metrics.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["metrics_for_full"] = module
    spec.loader.exec_module(module)
    return module


def test_report_is_what_metrics_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = Target(tmp_path / "s.db")
    result = full.run_full(target.connect, smoke_ok, target.restart, healthy)
    reports = tmp_path / "reports"
    reports.mkdir()
    path = reports / "2026-12-01-deploy-full.md"
    nondestructive = [Check("health", "PASS", "ok, commit 0123456789ab")]
    full.write_report(path, SHA, "http://203.0.113.5:8080", nondestructive, result)
    text = path.read_text()
    assert f"**Commit:** `{SHA}`" in text and "**Mode:** full" in text
    assert "**AC-10:** PASS" in text

    metrics = load_metrics()
    monkeypatch.setattr(metrics, "REPORTS", reports)
    run = metrics.latest_report("deploy", full_only=True, since=metrics.PHASE5_START)
    assert run is not None and run.passed == run.total and run.commit == SHA
    in_process = {"AC-08": (1, 1), "AC-09": (1, 1)}
    assert metrics.g1(in_process)[1] == "yes"
    assert metrics.g4({"AC-04": (1, 1), "AC-05": (1, 1)})[1] == "yes"


def test_main_needs_confirmation_for_full(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["http://x", SHA, "--full"]) == 2
    err = capsys.readouterr().err
    assert "--confirm-reset" in err and "resets" in err


def test_main_stops_before_destructive_steps_when_checks_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import scripts.post_deploy_check as pdc

    monkeypatch.setattr(pdc, "run_checks", lambda *a, **k: [Check("health", "FAIL", "down")])

    def must_not_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("destructive steps ran after a failed check")

    monkeypatch.setattr(full, "run_full", must_not_run)
    assert main(["http://x", SHA, "--full", "--confirm-reset"]) == 1
    assert "destructive steps not run" in capsys.readouterr().out
