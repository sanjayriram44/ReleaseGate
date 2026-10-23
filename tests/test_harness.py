"""The course autograder harness (/test, /test/setup, /test/run, /test/report) on both services."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app as create_system
from tester.main import create_app as create_tester

H = {"X-User-Id": "alice"}


def system(tmp_path: Path, test_endpoints: bool = True) -> TestClient:
    return TestClient(
        create_system(
            Settings(db_path=str(tmp_path / "s.db"), enable_test_endpoints=test_endpoints)
        )
    )


def make_tester(tmp_path: Path, default_target: str | None = None) -> TestClient:
    target = system(tmp_path)
    return TestClient(
        create_tester(
            "fixtures",
            client_factory=lambda _: target,
            host_check=lambda _: None,
            default_target=default_target,
        )
    )


# -- system ---------------------------------------------------------------------------------


def test_system_describes_itself(tmp_path: Path) -> None:
    body = system(tmp_path).get("/test").json()
    assert body["role"] == "system" and body["endpoints"]["setup"] == "POST /test/setup"


def test_system_setup_resets_data_and_returns_session(tmp_path: Path) -> None:
    c = system(tmp_path)
    rid = c.post(
        "/api/v1/releases",
        json={"product": "P", "version": "1", "support_end_date": "2030-01-01"},
        headers=H,
    ).json()["release_id"]
    r = c.post("/test/setup")
    assert r.status_code == 200
    assert r.json()["status"] == "ready" and r.json()["session_id"].startswith("ses-")
    assert c.get(f"/api/v1/releases/{rid}").status_code == 404
    assert c.get("/api/v1/audit-logs").json() == {"events": []}


def test_system_setup_sets_clock_and_keeps_given_session_id(tmp_path: Path) -> None:
    c = system(tmp_path)
    r = c.post("/test/setup", json={"session_id": "grader-1", "now": "2026-11-01T23:59:59Z"})
    assert r.json()["session_id"] == "grader-1"
    rel = {"product": "P", "version": "1", "support_end_date": "2026-11-01"}
    assert c.post("/api/v1/releases", json=rel, headers=H).json()["support_status"] == "supported"
    bad = c.post("/test/setup", json={"now": "2026-11-01T23:59:59+02:00"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "INVALID_REQUEST"


def test_system_run_then_report(tmp_path: Path) -> None:
    c = system(tmp_path)
    sid = c.post("/test/setup").json()["session_id"]
    assert c.get("/test/report", params={"session_id": sid}).json()["status"] == "ready"
    run = c.post("/test/run", json={"session_id": sid}).json()
    assert run["status"] == "completed" and run["result"] == "pass"
    assert run["summary"]["required_failed"] == 0
    assert run["report_url"] == f"/test/report?session_id={sid}"
    report = c.get("/test/report", params={"session_id": sid}).json()
    assert report["status"] == "completed" and report["result"] == "pass"
    assert report["role"] == "system" and len(report["checks"]) >= 30


def test_system_run_without_setup_creates_a_session(tmp_path: Path) -> None:
    c = system(tmp_path)
    run = c.post("/test/run").json()
    assert run["result"] == "pass"
    assert c.get("/test/report").json()["session_id"] == run["session_id"]  # latest


def test_report_errors(tmp_path: Path) -> None:
    c = system(tmp_path)
    r = c.get("/test/report")
    assert r.status_code == 404 and r.json()["error"]["code"] == "SESSION_NOT_FOUND"
    c.post("/test/setup")
    assert c.get("/test/report", params={"session_id": "nope"}).status_code == 404
    bad = c.post("/test/setup", content=b"not json", headers={"Content-Type": "application/json"})
    assert bad.status_code == 400


def test_get_is_accepted_for_setup_and_run(tmp_path: Path) -> None:
    c = system(tmp_path)
    sid = c.get("/test/setup").json()["session_id"]
    assert c.get("/test/run", params={"session_id": sid}).json()["result"] == "pass"


def test_harness_absent_unless_test_endpoints_enabled(tmp_path: Path) -> None:
    c = system(tmp_path, test_endpoints=False)
    assert c.get("/test").status_code == 404
    assert c.post("/test/setup").status_code == 404


# -- tester ---------------------------------------------------------------------------------


def test_tester_describes_itself(tmp_path: Path) -> None:
    assert make_tester(tmp_path).get("/test").json()["role"] == "tester"


def test_tester_setup_needs_a_target_without_default(tmp_path: Path) -> None:
    r = make_tester(tmp_path).post("/test/setup")
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_TARGET"


def test_tester_setup_run_report_against_given_target(tmp_path: Path) -> None:
    c = make_tester(tmp_path)
    setup = c.post("/test/setup", json={"target_base_url": "http://system.example:8080/"}).json()
    assert setup["target_base_url"] == "http://system.example:8080"
    run = c.post("/test/run", json={"session_id": setup["session_id"]}).json()
    assert run["result"] == "pass" and run["summary"]["required_passed"] >= 30
    report = c.get(f"/test/report?session_id={setup['session_id']}").json()
    assert report["role"] == "tester" and report["target_base_url"] == "http://system.example:8080"
    assert {ch["ac"] for ch in report["checks"]} >= {"AC-01", "AC-02", "AC-03"}


def test_tester_uses_default_target_and_alternate_names(tmp_path: Path) -> None:
    c = make_tester(tmp_path, default_target="http://our-system:8080")
    assert c.post("/test/setup").json()["target_base_url"] == "http://our-system:8080"
    alt = c.post("/test/setup", params={"system_base_url": "http://other:9000"}).json()
    assert alt["target_base_url"] == "http://other:9000"


def test_tester_rejects_bad_target(tmp_path: Path) -> None:
    r = make_tester(tmp_path).post("/test/setup", json={"target_base_url": "ftp://x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_TARGET"


def test_base_url_with_trailing_slash_still_works(tmp_path: Path) -> None:
    """A registered base URL ending in "/" makes clients call //test/... ."""
    for c in (system(tmp_path), make_tester(tmp_path, default_target="http://our-system:8080")):
        base = str(c.base_url).rstrip("/")
        assert c.get(f"{base}//test").status_code == 200
        sid = c.post(f"{base}//test/setup").json()["session_id"]
        assert c.post(f"{base}//test/run", json={"session_id": sid}).json()["result"] == "pass"
        assert c.get(f"{base}//test/report", params={"session_id": sid}).status_code == 200
