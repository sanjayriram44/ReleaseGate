"""scripts/post_deploy_check.py, non-destructive mode (CLAUDE.md §16.2), run against the app
in-process or against hand-made responses."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from scripts.post_deploy_check import CVE_QUERY, Fetch, Response, load_contract, main, run_checks

SHA = "0123456789abcdef0123456789abcdef01234567"
CONTRACT = load_contract()
UNREACHABLE = "VULNERABILITY_SOURCE_UNREACHABLE"


def make_fetch(client: TestClient) -> Fetch:
    def fetch(
        method: str, path: str, body: Any, headers: dict[str, str], timeout: float
    ) -> Response:
        started = time.perf_counter()
        r = client.request(method, path, json=body, headers=headers)
        try:
            parsed = r.json()
        except ValueError:
            parsed = None
        return Response(r.status_code, parsed, time.perf_counter() - started)

    return fetch


@pytest.fixture
def system(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        Settings(db_path=str(tmp_path / "x.db"), enable_test_endpoints=True, commit=SHA)
    )
    with TestClient(app) as c:
        yield c


def outcomes(checks: list[Any]) -> dict[str, str]:
    return {c.name: c.outcome for c in checks}


def test_healthy_deployment_passes(system: TestClient) -> None:
    checks = run_checks(make_fetch(system), SHA[:7], True, CONTRACT, wait_s=0)
    assert outcomes(checks) == {
        "health": "PASS",
        "openapi": "PASS",
        "test-endpoints": "PASS",
        "malformed-request": "PASS",
        "cve-query": "PASS",  # 404 CVE_UNKNOWN: the source has no records
    }
    # Non-destructive: nothing was written.
    assert system.get("/api/v1/audit-logs").json() == {"events": []}


def test_wrong_commit_fails(system: TestClient) -> None:
    checks = run_checks(make_fetch(system), "fedcba9", True, CONTRACT, wait_s=0)
    [health] = [c for c in checks if c.name == "health"]
    assert health.name == "health" and health.outcome == "FAIL"
    assert "fedcba9" in health.detail and SHA[:7] in health.detail


def test_test_endpoints_must_match_the_expectation(system: TestClient, tmp_path: Path) -> None:
    checks = run_checks(make_fetch(system), SHA, False, CONTRACT, wait_s=0)
    assert outcomes(checks)["test-endpoints"] == "FAIL"

    app = create_app(Settings(db_path=str(tmp_path / "off.db"), commit=SHA))
    with TestClient(app) as off:
        assert outcomes(run_checks(make_fetch(off), SHA, False, CONTRACT, wait_s=0)) == {
            "health": "PASS",
            "openapi": "PASS",  # test paths aren't expected when they're off
            "test-endpoints": "PASS",
            "malformed-request": "PASS",
            "cve-query": "PASS",
        }
        checks = run_checks(make_fetch(off), SHA, True, CONTRACT, wait_s=0)
        assert outcomes(checks)["test-endpoints"] == "FAIL"


def test_missing_contract_path_fails(system: TestClient) -> None:
    real = make_fetch(system)

    def fetch(method: str, path: str, body: Any, headers: dict[str, str], t: float) -> Response:
        r = real(method, path, body, headers, t)
        if path == "/openapi.json":
            r.body["paths"].pop("/api/v1/audit-logs")
        return r

    [openapi] = [c for c in run_checks(fetch, SHA, True, CONTRACT, wait_s=0) if c.name == "openapi"]
    assert openapi.outcome == "FAIL" and "GET /api/v1/audit-logs" in openapi.detail


def make_canned(overrides: dict[str, Response]) -> Fetch:
    """A healthy deployment's answers, with some paths' answers replaced."""
    paths = {
        p: {m: {} for m in item if m in ("get", "put", "post", "patch", "delete")}
        for p, item in CONTRACT["paths"].items()
    }
    answers = {
        "/health": Response(200, {"status": "ok", "commit": SHA}, 0.01),
        "/openapi.json": Response(200, {"paths": paths}, 0.01),
        "/test": Response(200, {"service": "x"}, 0.01),
        "/api/v1/releases": Response(
            400, {"error": {"code": "INVALID_REQUEST", "message": "product is required"}}, 0.01
        ),
        **overrides,
    }

    def fetch(method: str, path: str, body: Any, headers: dict[str, str], t: float) -> Response:
        if path.startswith("/api/v1/vulnerabilities/"):
            return answers.get("cve", Response(0, None, 0.01))
        return answers[path]

    return fetch


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (Response(404, {"error": {"code": "CVE_UNKNOWN", "message": "m"}}, 0.1), "PASS"),
        (Response(503, {"error": {"code": UNREACHABLE, "message": "m"}}, 2), "PASS"),
        (Response(404, {"error": {"code": "NOT_FOUND", "message": "Not Found"}}, 0.1), "FAIL"),
        (Response(200, {"supported": [], "unsupported": []}, 0.1), "FAIL"),
        (Response(404, {"error": {"code": "CVE_UNKNOWN", "message": "m"}}, 15.5), "FAIL"),
        (Response(0, None, 15.0), "FAIL"),  # timed out or unreachable
    ],
)
def test_cve_query_once_built(answer: Response, outcome: str) -> None:
    fetch = make_canned({"cve": answer})
    checks = run_checks(fetch, SHA, True, CONTRACT, wait_s=0, not_built=set())
    assert outcomes(checks) == {
        "health": "PASS",
        "openapi": "PASS",
        "test-endpoints": "PASS",
        "malformed-request": "PASS",
        "cve-query": outcome,
    }
    assert CVE_QUERY == ("/api/v1/vulnerabilities/{cveId}/affected-releases", "get")


@pytest.mark.parametrize(
    "answer",
    [
        Response(422, {"detail": [{"msg": "Field required"}]}, 0.01),
        Response(400, {"error": {"code": "INVALID_REQUEST"}}, 0.01),
        Response(201, {"release_id": "r1"}, 0.01),
    ],
)
def test_malformed_request_must_be_400_with_the_error_shape(answer: Response) -> None:
    checks = run_checks(make_canned({"/api/v1/releases": answer}), SHA, True, CONTRACT, wait_s=0)
    assert outcomes(checks)["malformed-request"] == "FAIL"


def test_health_not_ready_fails_and_unhealthy_db_fails() -> None:
    down = make_canned({"/health": Response(0, None, 0.01)})
    assert outcomes(run_checks(down, SHA, True, CONTRACT, wait_s=0))["health"] == "FAIL"
    bad_db = make_canned({"/health": Response(503, {"status": "unavailable", "commit": SHA}, 0)})
    assert outcomes(run_checks(bad_db, SHA, True, CONTRACT, wait_s=0))["health"] == "FAIL"


def test_main_rejects_full_mode_and_bad_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["http://x", SHA, "--full"]) == 2
    assert "--full" in capsys.readouterr().err
    assert main(["http://x", "not-a-sha"]) == 2
