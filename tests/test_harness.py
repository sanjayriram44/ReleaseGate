"""The course autograder harness, spec v2 ("Cross-team Testing Interface", Phases 5 and 6).

System: POST /test/setup and GET /test/report. Tester: POST /test/setup, POST /test/run and
GET /test/report. Errors are {"message", "source"}.
"""

from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app as create_system
from tester.coverage import ACCEPTANCE_CRITERIA, OPERATIONS, is_entry
from tester.main import create_app as create_tester
from tester.model import DESIGN_REQUIREMENTS

H = {"X-User-Id": "alice"}
OUTCOMES = {"pass", "fail", "error", "skip"}
SOURCES = {"tester", "system", "communication", "unknown"}


def system(tmp_path: Path, test_endpoints: bool = True) -> TestClient:
    return TestClient(
        create_system(
            Settings(db_path=str(tmp_path / "s.db"), enable_test_endpoints=test_endpoints)
        )
    )


class Wrapped:
    """A target client that can rewrite some answers, for systems that aren't ours."""

    def __init__(self, target: TestClient, rewrite: Any) -> None:
        self.target, self.rewrite = target, rewrite

    def __enter__(self) -> "Wrapped":
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def request(self, method: str, url: str, **kw: Any) -> Any:
        return self.rewrite(method, str(url), kw) or self.target.request(method, url, **kw)

    def get(self, url: str, **kw: Any) -> Any:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> Any:
        return self.request("POST", url, **kw)


def make_tester(
    tmp_path: Path, default_target: str | None = None, rewrite: Any = None
) -> tuple[TestClient, TestClient]:
    target = system(tmp_path)
    factory = (lambda _: target) if rewrite is None else (lambda _: Wrapped(target, rewrite))
    tester = TestClient(
        create_tester(
            "fixtures",
            client_factory=factory,  # type: ignore[arg-type,return-value]
            host_check=lambda _: None,
            default_target=default_target,
        )
    )
    return tester, target


def is_error(r: Any, status: int, source: str) -> bool:
    body = r.json()
    return (
        r.status_code == status
        and set(body) == {"message", "source"}
        and body["source"] == source
        and bool(body["message"].strip())
    )


# -- system ---------------------------------------------------------------------------------


def test_system_describes_itself_and_has_no_run(tmp_path: Path) -> None:
    c = system(tmp_path)
    body = c.get("/test").json()
    assert body["role"] == "system" and set(body["endpoints"]) == {"setup", "report"}
    assert c.post("/test/run", json={"session_id": "x"}).status_code in (404, 405)


def test_system_setup_prepares_the_supplied_session(tmp_path: Path) -> None:
    c = system(tmp_path)
    release = {"product": "p", "version": "1", "support_end_date": "2030-01-01"}
    assert c.post("/api/v1/releases", json=release, headers=H).status_code == 201
    r = c.post("/test/setup", json={"session_id": "run-123", "setup": {}})
    assert r.status_code == 201 and r.json() == {"session_id": "run-123"}
    assert c.get("/api/v1/audit-logs").json()["events"] == []  # state reset


def test_system_setup_sets_the_clock(tmp_path: Path) -> None:
    c = system(tmp_path)
    for i, body in enumerate(
        (
            {"session_id": "a", "setup": {"now": "2026-11-01T23:59:59Z"}},
            {"session_id": "b", "now": "2026-11-01T23:59:59Z"},  # older callers
        )
    ):
        assert c.post("/test/setup", json=body).status_code == 201
        release = {"product": "p", "version": str(i), "support_end_date": "2030-01-01"}
        c.post("/api/v1/releases", json=release, headers=H)
        assert c.get("/api/v1/audit-logs").json()["events"][0]["timestamp"] == (
            "2026-11-01T23:59:59Z"
        )
    bad = c.post("/test/setup", json={"session_id": "c", "setup": {"now": "2026-11-01T23:59:59"}})
    assert is_error(bad, 400, "system")
    assert c.post("/test/setup", json={"session_id": "c", "setup": {}}).status_code == 201


def test_system_setup_errors(tmp_path: Path) -> None:
    c = system(tmp_path)
    assert c.post("/test/setup", json={"session_id": "s1", "setup": {}}).status_code == 201
    assert is_error(c.post("/test/setup", json={"session_id": "s1", "setup": {}}), 409, "system")
    assert is_error(c.post("/test/setup", json={"setup": {}}), 400, "system")
    assert is_error(c.post("/test/setup", json={"session_id": "", "setup": {}}), 400, "system")
    assert is_error(c.post("/test/setup", json={"session_id": "s2", "setup": []}), 400, "system")
    not_json = c.post("/test/setup", content=b"x", headers={"Content-Type": "application/json"})
    assert is_error(not_json, 400, "system")


def test_system_report_gives_code_coverage_for_a_prepared_session(tmp_path: Path) -> None:
    c = system(tmp_path)
    assert is_error(c.get("/test/report"), 400, "system")
    assert is_error(c.get("/test/report", params={"session_id": "nope"}), 404, "system")
    c.post("/test/setup", json={"session_id": "s1", "setup": {}})
    body = c.get("/test/report", params={"session_id": "s1"}).json()
    assert set(body) == {"session_id", "coverage"} and body["session_id"] == "s1"
    code = body["coverage"]["code"]
    assert is_entry(code) and code["covered"] is None and code["total"] is None
    assert "app/" in code["basis"]


def test_harness_absent_unless_test_endpoints_enabled(tmp_path: Path) -> None:
    c = system(tmp_path, test_endpoints=False)
    assert c.get("/test").status_code == 404
    assert c.post("/test/setup", json={"session_id": "s", "setup": {}}).status_code == 404


# -- tester ---------------------------------------------------------------------------------


def test_tester_describes_itself(tmp_path: Path) -> None:
    body = make_tester(tmp_path)[0].get("/test").json()
    assert body["role"] == "tester" and set(body["endpoints"]) == {"setup", "run", "report"}


def test_tester_setup_prepares_the_system_with_the_same_session(tmp_path: Path) -> None:
    c, target = make_tester(tmp_path)
    r = c.post("/test/setup", json={"target_url": "http://our-system:8080"})
    assert r.status_code == 201 and set(r.json()) == {"session_id"}
    sid = r.json()["session_id"]
    assert target.get("/test/report", params={"session_id": sid}).status_code == 200
    assert (
        c.post("/test/setup", json={"target_url": "http://our-system:8080"}).json()["session_id"]
        != sid
    )  # unique per session


def test_tester_setup_needs_a_valid_target(tmp_path: Path) -> None:
    c, _ = make_tester(tmp_path)
    assert is_error(c.post("/test/setup", json={}), 400, "tester")
    assert is_error(c.post("/test/setup", json={"target_url": "ftp://x"}), 400, "tester")
    assert is_error(c.post("/test/setup", json={"target_url": "http://x/?q=1"}), 400, "tester")


def test_tester_setup_returns_system_setup_errors_unchanged(tmp_path: Path) -> None:
    def fails(method: str, url: str, kw: dict[str, Any]) -> Any:
        if url == "/test/setup":
            request = httpx.Request(method, "http://t/test/setup")
            body = {"message": "Could not initialize the session database.", "source": "system"}
            return httpx.Response(503, json=body, request=request)
        return None

    c, _ = make_tester(tmp_path, rewrite=fails)
    r = c.post("/test/setup", json={"target_url": "http://team2:8080"})
    assert is_error(r, 503, "system")
    assert r.json()["message"] == "Could not initialize the session database."


def test_tester_setup_reports_communication_failures(tmp_path: Path) -> None:
    def down(method: str, url: str, kw: dict[str, Any]) -> Any:
        raise httpx.ConnectError("connection refused")

    c, _ = make_tester(tmp_path, rewrite=down)
    assert is_error(
        c.post("/test/setup", json={"target_url": "http://gone:8080"}), 500, ("communication")
    )


def test_tester_run_returns_the_suite_report_for_our_own_system(tmp_path: Path) -> None:
    c, _ = make_tester(tmp_path)
    sid = c.post("/test/setup", json={"target_url": "http://our-system:8080/"}).json()["session_id"]
    r = c.post("/test/run", json={"session_id": sid})
    assert r.status_code == 200
    report = r.json()
    assert report["session_id"] == sid and report["target_url"] == "http://our-system:8080/"
    results = report["results"]
    ids = [x["test_id"] for x in results]
    assert len(ids) == len(set(ids)) >= 100 and all(ids)
    assert all(x["outcome"] in OUTCOMES and x["message"].strip() for x in results)
    assert all(x["outcome"] == "pass" for x in results if x["required"])
    cov = report["coverage"]
    assert set(cov) == {"code", "component", "system", "model"}  # model: our own system
    assert all(is_entry(e) for e in cov.values())
    assert cov["code"]["covered"] is None  # copied from the system's GET /test/report
    assert (cov["component"]["covered"], cov["component"]["total"]) == (14, len(OPERATIONS))
    assert (cov["system"]["covered"], cov["system"]["total"]) == (9, len(ACCEPTANCE_CRITERIA))
    assert (cov["model"]["covered"], cov["model"]["total"]) == (13, len(DESIGN_REQUIREMENTS))
    assert "github.com" in cov["model"]["basis"]
    assert c.get("/test/report", params={"session_id": sid}).json() == report


def test_tester_session_rules(tmp_path: Path) -> None:
    c, _ = make_tester(tmp_path)
    sid = c.post("/test/setup", json={"target_url": "http://s:8080"}).json()["session_id"]
    assert is_error(c.get("/test/report", params={"session_id": sid}), 409, "tester")
    assert c.post("/test/run", json={"session_id": sid}).status_code == 200
    assert is_error(c.post("/test/run", json={"session_id": sid}), 409, "tester")  # no rerun
    assert is_error(c.post("/test/run", json={"session_id": "nope"}), 404, "tester")
    assert is_error(c.post("/test/run", json={}), 400, "tester")
    assert is_error(c.get("/test/report", params={"session_id": "nope"}), 404, "tester")
    assert is_error(c.get("/test/report"), 400, "tester")


def test_another_teams_system_gets_no_model_coverage(tmp_path: Path) -> None:
    def team2(method: str, url: str, kw: dict[str, Any]) -> Any:
        request = httpx.Request(method, f"http://team2{url}")
        if url == "/test":
            return httpx.Response(200, json={"service": "Team2", "role": "system"}, request=request)
        if url == "/test/report":
            code = {"covered": 812, "total": 1000, "basis": "Source lines of cra_service/"}
            body = {"session_id": kw["params"]["session_id"], "coverage": {"code": code}}
            return httpx.Response(200, json=body, request=request)
        return None

    c, _ = make_tester(tmp_path, rewrite=team2)
    sid = c.post("/test/setup", json={"target_url": "http://team2:8080"}).json()["session_id"]
    cov = c.post("/test/run", json={"session_id": sid}).json()["coverage"]
    assert set(cov) == {"code", "component", "system"}
    assert cov["code"] == {"covered": 812, "total": 1000, "basis": "Source lines of cra_service/"}


def test_invalid_system_code_coverage_is_reported_as_unavailable(tmp_path: Path) -> None:
    def bad(method: str, url: str, kw: dict[str, Any]) -> Any:
        if url == "/test/report":
            code = {"covered": 5, "total": 3, "basis": "x"}  # covered > total
            body = {"session_id": "s", "coverage": {"code": code}}
            return httpx.Response(200, json=body, request=httpx.Request(method, "http://t" + url))
        return None

    c, _ = make_tester(tmp_path, rewrite=bad)
    sid = c.post("/test/setup", json={"target_url": "http://s:8080"}).json()["session_id"]
    code = c.post("/test/run", json={"session_id": sid}).json()["coverage"]["code"]
    assert code["covered"] is None and code["total"] is None and code["basis"]


def test_base_url_with_trailing_slash_still_works(tmp_path: Path) -> None:
    """A registered base URL ending in "/" makes clients call //test/... ."""
    s = system(tmp_path)
    base = str(s.base_url).rstrip("/")
    assert s.post(f"{base}//test/setup", json={"session_id": "s", "setup": {}}).status_code == 201
    assert s.get(f"{base}//test/report", params={"session_id": "s"}).status_code == 200
    c, _ = make_tester(tmp_path)
    base = str(c.base_url).rstrip("/")
    sid = c.post(f"{base}//test/setup", json={"target_url": "http://s:8080"}).json()["session_id"]
    assert c.post(f"{base}//test/run", json={"session_id": sid}).status_code == 200
    assert c.get(f"{base}//test/report", params={"session_id": sid}).status_code == 200


def test_component_operations_match_the_contract() -> None:
    import yaml

    doc = yaml.safe_load(Path("docs/openapi.yaml").read_text())
    contract = {
        (m.upper(), p)
        for p, item in doc["paths"].items()
        for m in ("get", "put", "post", "patch", "delete")
        if m in item and p.startswith("/api/v1/") and not p.startswith("/api/v1/test/")
    }
    assert set(OPERATIONS) == contract
