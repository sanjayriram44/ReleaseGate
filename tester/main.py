"""ReleaseGate tester: runs the shared AC-01..AC-03 checks against any system base URL.

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
from tester.harness import HarnessError, make_router

# Accepted names for the system under test in /test/setup and /test/run.
TARGET_KEYS = ("target_base_url", "system_base_url", "base_url", "system_url", "target")

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
            raise HarnessError(400, "INVALID_TARGET", str(exc)) from exc
        return target

    def execute(target: str) -> Report:
        with runs_lock:
            lock = target_locks.setdefault(target, threading.Lock())
        # One run per target at a time: each run resets the target's data.
        if not lock.acquire(blocking=False):
            raise HarnessError(
                409, "RUN_IN_PROGRESS", f"a run against {target} is already in progress"
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

    def harness_setup(params: dict[str, Any]) -> dict[str, Any]:
        url = next((params[k] for k in TARGET_KEYS if params.get(k)), None) or default_target
        if not url:
            raise HarnessError(
                400, "INVALID_TARGET", "give target_base_url (the system base URL to test)"
            )
        return {"target_base_url": checked_target(str(url))}

    def harness_run(params: dict[str, Any], session: dict[str, Any]) -> Report:
        return execute(session["target_base_url"])

    app.include_router(
        make_router(
            "tester",
            "ReleaseGate tester. setup selects the system to test (target_base_url, default: our "
            "deployed system); run executes AC-01..AC-03 against it over HTTP, resetting its "
            "data; report returns every check.",
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
