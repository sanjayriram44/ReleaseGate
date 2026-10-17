from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app as create_system
from tester.checks import Fixtures, run
from tester.main import BadTarget, create_app, normalize_target, reject_link_local

FIXTURES = Fixtures.load(Path("fixtures"))


def system(tmp_path: Path, test_endpoints: bool = True) -> TestClient:
    return TestClient(
        create_system(
            Settings(db_path=str(tmp_path / "s.db"), enable_test_endpoints=test_endpoints)
        )
    )


def failed(report: Any) -> list[str]:
    return [c.id for c in report.checks if c.required and not c.passed]


def test_our_system_passes_every_check(tmp_path: Path) -> None:
    report = run(system(tmp_path), FIXTURES, "http://testserver")
    assert report.error is None
    assert failed(report) == []
    assert report.result == "pass"
    assert report.summary["informational_failed"] == 0
    acs = {c.ac for c in report.checks}
    assert {"AC-01", "AC-02", "AC-03", "contract"} <= acs
    assert report.summary["required_passed"] >= 25


def test_run_leaves_target_reset(tmp_path: Path) -> None:
    client = system(tmp_path)
    run(client, FIXTURES, "http://testserver")
    assert client.get("/api/v1/audit-logs").json() == {"events": []}


def test_broken_system_fails_with_details(tmp_path: Path) -> None:
    broken = FastAPI()

    @broken.post("/api/v1/test/reset")
    def reset() -> Response:
        return Response(status_code=204)

    @broken.put("/api/v1/test/clock")
    def clock() -> dict[str, str]:
        return {"now": "2026-11-01T23:59:59Z"}

    @broken.post("/api/v1/releases", status_code=422)
    def register() -> dict[str, str]:
        return {"detail": "nope"}

    report = run(TestClient(broken), FIXTURES, "http://broken")
    assert report.result == "fail"
    assert "ac01.past" in failed(report)
    past = next(c for c in report.checks if c.id == "ac01.past")
    assert past.actual.startswith("422") and "nope" in past.response


def test_unreachable_target_is_an_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.Client(transport=httpx.MockTransport(refuse), base_url="http://down:8080")
    report = run(client, FIXTURES, "http://down:8080")
    assert report.result == "error"
    assert report.error is not None and "Target unreachable" in report.error


def test_test_endpoints_disabled_is_an_error(tmp_path: Path) -> None:
    report = run(system(tmp_path, test_endpoints=False), FIXTURES, "http://testserver")
    assert report.result == "error"
    assert report.error is not None and "test endpoints" in report.error


@pytest.fixture
def api(tmp_path: Path) -> TestClient:
    target = system(tmp_path)
    return TestClient(
        create_app("fixtures", client_factory=lambda _: target, host_check=lambda _: None)
    )


def test_api_run_list_and_get(api: TestClient) -> None:
    r = api.post("/api/v1/runs", json={"target_base_url": "http://system.example:8080/"})
    assert r.status_code == 201
    body = r.json()
    assert body["result"] == "pass" and body["target_base_url"] == "http://system.example:8080"
    listed = api.get("/api/v1/runs").json()["runs"]
    assert [x["run_id"] for x in listed] == [body["run_id"]]
    assert api.get(f"/api/v1/runs/{body['run_id']}").json()["checks"] == body["checks"]


def test_api_errors_use_shared_shape(api: TestClient) -> None:
    r = api.post("/api/v1/runs", json={"target_base_url": "ftp://x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_TARGET"
    r = api.post("/api/v1/runs", json={})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"
    r = api.get("/api/v1/runs/run-nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_api_serves_page_and_health(api: TestClient) -> None:
    assert "ReleaseGate Tester" in api.get("/").text
    assert api.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://1.2.3.4:8080/", "http://1.2.3.4:8080"),
        (" https://team2.example.com/base/ ", "https://team2.example.com/base"),
    ],
)
def test_normalize_target(url: str, expected: str) -> None:
    assert normalize_target(url) == expected


@pytest.mark.parametrize(
    "url", ["localhost:8080", "http://", "http://h:1/?q=1", "javascript:alert(1)"]
)
def test_normalize_target_rejects(url: str) -> None:
    with pytest.raises(BadTarget):
        normalize_target(url)


def test_metadata_server_is_refused() -> None:
    with pytest.raises(BadTarget):
        reject_link_local("http://169.254.169.254")
