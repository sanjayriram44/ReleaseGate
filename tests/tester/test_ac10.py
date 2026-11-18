"""AC-10 (REQ-01, 02, 05, 06, 08): state survives a restart (CLAUDE.md §6.7; P5-Q8 two-step).

In-process, a restart is a fresh app on the same database file.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tester import ac10


def system(db: Path) -> TestClient:
    return TestClient(create_app(Settings(db_path=str(db), enable_test_endpoints=True)))


def test_seed_covers_everything_ac10_names(tmp_path: Path) -> None:
    state = ac10.seed(system(tmp_path / "s.db"))
    snap = state["snapshot"]
    assert set(snap) == set(ac10.KEYS)
    assert len(snap["components"]["components"]) == 25
    assert [r["release_id"] for r in snap["cve_query"]["supported"]] == [state["ids"]["release"]]
    incident = snap["incident"]
    assert incident["fix_available_at"] is not None
    assert incident["deadlines"]["early_warning"]["status"] == "met"
    assert set(snap["reports"]) == {"early_warning", "vulnerability_notification", "final_report"}
    assert snap["reports"]["vulnerability_notification"]["missing_fields"] == [
        "exploit_nature",
        "user_mitigations",
    ]
    actions = [e["action"] for e in snap["audit"]["events"]]
    assert actions == [
        "RELEASE_REGISTERED",
        "SBOM_STORED",
        "SBOM_REPLACED",
        "INCIDENT_CREATED",
        "FIX_AVAILABLE_RECORDED",
        "SUBMISSION_RECORDED",
        "REPORT_DATA_STORED",
        "REPORT_DATA_STORED",
        "REPORT_DATA_STORED",
    ]


def test_state_is_unchanged_after_a_restart(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    state = ac10.seed(system(db))
    assert ac10.verify(system(db), state) == []


def test_verify_resets_the_clock_it_needs(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    state = ac10.seed(system(db))
    restarted = system(db)
    restarted.put("/api/v1/test/clock", json={"now": "2030-01-01T00:00:00Z"})
    assert ac10.verify(restarted, state) == []


def test_verify_notices_changed_report_data(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    state = ac10.seed(system(db))
    client = system(db)
    iid = state["ids"]["incident"]
    r = client.put(
        f"/api/v1/incidents/{iid}/report-data/final_report",
        json={"severity": "Low"},
        headers=ac10.USER,
    )
    assert r.status_code == 200
    assert ac10.verify(client, state) == ["reports", "audit"]


def test_verify_notices_lost_data_without_crashing(tmp_path: Path) -> None:
    state = ac10.seed(system(tmp_path / "s.db"))
    assert ac10.verify(system(tmp_path / "empty.db"), state) == list(ac10.KEYS)


def test_command_line_two_steps(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "s.db"
    file = tmp_path / "ac10.json"
    clients = iter([system(db), system(db)])
    monkeypatch.setattr(ac10, "make_client", lambda url: next(clients))
    assert ac10.main(["snapshot", "http://target", str(file)]) == 0
    assert json.loads(file.read_text())["target"] == "http://target"
    assert ac10.main(["verify", "http://target", str(file)]) == 0


def test_command_line_reports_a_change(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    file = tmp_path / "ac10.json"
    clients = iter([system(tmp_path / "s.db"), system(tmp_path / "other.db")])
    monkeypatch.setattr(ac10, "make_client", lambda url: next(clients))
    assert ac10.main(["snapshot", "http://target", str(file)]) == 0
    assert ac10.main(["verify", "http://target", str(file)]) == 1


def test_command_line_rejects_bad_arguments() -> None:
    assert ac10.main([]) == 2
    assert ac10.main(["restart", "http://target", "x.json"]) == 2


def test_unreachable_target_is_a_clean_failure(
    tmp_path: Path,
    monkeypatch,  # type: ignore[no-untyped-def]
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    import httpx

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(
        ac10,
        "make_client",
        lambda url: httpx.Client(base_url=url, transport=httpx.MockTransport(refuse)),
    )
    file = tmp_path / "ac10.json"
    assert ac10.main(["snapshot", "http://target", str(file)]) == 1
    assert "AC-10 snapshot FAILED" in capsys.readouterr().out
    file.write_text(json.dumps(ac10.seed(system(tmp_path / "s.db"))))
    assert ac10.main(["verify", "http://target", str(file)]) == 1
    assert "AC-10 FAIL" in capsys.readouterr().out
