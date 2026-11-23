"""ReleaseGate tester: runs the shared AC-01..AC-09 checks against any system base URL.

The autograder harness (POST /test/setup, POST /test/run, GET /test/report) follows spec v2;
see tester/harness.py.

POST /api/v1/runs {"target_base_url": "http://host:port"} -> report JSON.
A run calls the target's /api/v1/test/reset, so it wipes the target's data.
"""

import ipaddress
import os
import socket
import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from tester.checks import Fixtures, Report, run
from tester.coverage import is_entry, unavailable
from tester.harness import SOURCES, CollapseSlashes, HarnessError, tester_router
from tester.suite import suite_report

# Accepted names for the system under test in /test/setup and /test/run.
TARGET_KEYS = (
    "target_url",
    "target_base_url",
    "system_base_url",
    "base_url",
    "system_url",
    "target",
)

ClientFactory = Callable[[str], httpx.Client]
HostCheck = Callable[[str], None]
MAX_RUNS_KEPT = 50
TIMEOUT_S = 15.0
PAGE = (Path(__file__).parent / "page.html").read_text()


class RunRequest(BaseModel):
    target_base_url: str


class BadTarget(Exception):
    pass


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _error_parts(resp: httpx.Response) -> tuple[str, str]:
    """message and source of a system setup error, kept as the system sent them (spec v2)."""
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        nested = body.get("error")
        message = body.get("message") or (
            nested.get("message") if isinstance(nested, dict) else None
        )
        source = body.get("source")
        if isinstance(message, str) and message.strip():
            return message, source if source in SOURCES else "system"
    text = resp.text.strip()[:200]
    return (text or f"system setup answered HTTP {resp.status_code}"), "system"


def normalize_target(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BadTarget("target_base_url must be an http(s) URL such as http://203.0.113.5:8080")
    if parts.query or parts.fragment:
        raise BadTarget("target_base_url must not contain a query string or fragment")
    return f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/")


def reject_link_local(url: str) -> None:
    """Keep the tester from being pointed at cloud metadata or other link-local hosts."""
    host = urlsplit(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise BadTarget(f"cannot resolve host {host!r}") from exc
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if addr.is_link_local or addr.is_multicast or addr.is_unspecified:
            raise BadTarget(f"host {host!r} resolves to a disallowed address ({addr})")


def default_client(base_url: str) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=TIMEOUT_S, follow_redirects=False)


def create_app(
    fixtures_dir: str | None = None,
    client_factory: ClientFactory = default_client,
    host_check: HostCheck = reject_link_local,
    default_target: str | None = None,
) -> FastAPI:
    app = FastAPI(title="ReleaseGate Tester", version="1.0.0")
    app.add_middleware(CollapseSlashes)
    default_target = default_target or os.environ.get("TESTER_DEFAULT_TARGET") or None
    fixtures = Fixtures.load(
        Path(fixtures_dir or os.environ.get("TESTER_FIXTURES_DIR", "fixtures"))
    )
    runs: OrderedDict[str, Report] = OrderedDict()
    runs_lock = threading.Lock()
    target_locks: dict[str, threading.Lock] = {}

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(
            400, "INVALID_REQUEST", 'body must be JSON: {"target_base_url": "http://host:port"}'
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(
            exc.status_code, "NOT_FOUND" if exc.status_code == 404 else "ERROR", str(exc.detail)
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def page() -> str:
        return PAGE

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    def checked_target(url: str) -> str:
        try:
            target = normalize_target(url)
            host_check(target)
        except BadTarget as exc:
            raise HarnessError(400, str(exc), "tester", code="INVALID_TARGET") from exc
        return target

    def execute(target: str) -> Report:
        with runs_lock:
            lock = target_locks.setdefault(target, threading.Lock())
        # One run per target at a time: each run resets the target's data.
        if not lock.acquire(blocking=False):
            raise HarnessError(
                409, f"a run against {target} is already in progress", "tester", "RUN_IN_PROGRESS"
            )
        try:
            with client_factory(target) as client:
                report = run(client, fixtures, target)
        finally:
            lock.release()
        with runs_lock:
            runs[report.run_id] = report
            while len(runs) > MAX_RUNS_KEPT:
                runs.popitem(last=False)
        return report

    @app.post("/api/v1/runs", status_code=201, response_model=None)
    def start_run(body: RunRequest) -> dict[str, Any] | JSONResponse:
        try:
            return execute(checked_target(body.target_base_url)).to_dict()
        except HarnessError as exc:
            return _error(exc.status, exc.code, exc.message)

    def harness_setup(session_id: str, params: dict[str, Any]) -> dict[str, Any]:
        url = next((params[k] for k in TARGET_KEYS if params.get(k)), None) or default_target
        if not url:
            raise HarnessError(
                400, "target_url is required (the system base URL to test)", "tester"
            )
        target = checked_target(str(url))
        # Spec v2: pass the same session id with the starting data to the system's setup and wait.
        try:
            with client_factory(target) as client:
                resp = client.post("/test/setup", json={"session_id": session_id, "setup": {}})
        except httpx.HTTPError as exc:
            raise HarnessError(
                500, f"system setup at {target} did not answer: {exc}", "communication"
            ) from exc
        if resp.status_code not in (200, 201):
            message, source = _error_parts(resp)
            raise HarnessError(resp.status_code, message, source)
        return {
            "target_url": str(url).strip(),  # as given, to match the grader's registered URL
            "target_base_url": target,
            "own_system": _is_our_system(target),
        }

    def _is_our_system(target: str) -> bool:
        """Model coverage only when the target is our own system (spec v2)."""
        try:
            with client_factory(target) as client:
                info = client.get("/test").json()
        except (httpx.HTTPError, ValueError):
            return False
        return isinstance(info, dict) and (info.get("service"), info.get("role")) == (
            "ReleaseGate",
            "system",
        )

    def _system_code_coverage(target: str, session_id: str) -> dict[str, Any]:
        """The target system's code coverage for this session, from its GET /test/report."""
        try:
            with client_factory(target) as client:
                resp = client.get("/test/report", params={"session_id": session_id})
            code = (
                (resp.json().get("coverage") or {}).get("code") if resp.status_code == 200 else None
            )
        except (httpx.HTTPError, ValueError, AttributeError):
            return unavailable("The target system's GET /test/report did not answer.")
        if not is_entry(code):
            return unavailable(
                f"The target system's GET /test/report gave no valid code coverage "
                f"(HTTP {resp.status_code})."
            )
        assert isinstance(code, dict)
        return code

    def harness_run(session_id: str, session: dict[str, Any]) -> dict[str, Any]:
        target = session["target_base_url"]
        report = execute(target)
        code = _system_code_coverage(target, session_id)
        return suite_report(
            session_id, session["target_url"], report, code, bool(session.get("own_system"))
        )

    app.include_router(
        tester_router(
            "ReleaseGate tester. setup prepares the system at target_url through its "
            "/test/setup; run executes AC-01..AC-09 against its project API over HTTP and returns "
            "one suite report with results and coverage; report returns that stored report.",
            harness_setup,
            harness_run,
        )
    )

    @app.get("/api/v1/runs")
    def list_runs() -> dict[str, Any]:
        with runs_lock:
            items = list(reversed(runs.values()))
        return {
            "runs": [
                {
                    "run_id": r.run_id,
                    "target_base_url": r.target_base_url,
                    "started_at": r.started_at,
                    "result": r.result,
                    "summary": r.summary,
                }
                for r in items
            ]
        }

    @app.get("/api/v1/runs/{run_id}", response_model=None)
    def get_run(run_id: str) -> dict[str, Any] | JSONResponse:
        with runs_lock:
            report = runs.get(run_id)
        if report is None:
            return _error(
                404,
                "RUN_NOT_FOUND",
                f"run {run_id} not found (only the last {MAX_RUNS_KEPT} are kept)",
            )
        return report.to_dict()

    return app
