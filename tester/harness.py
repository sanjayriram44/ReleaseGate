"""Course autograder harness, spec v2 ("Cross-team Testing Interface", student-facing-specv2,
which applies to Phases 5 and 6).

Every tester exposes POST /test/setup, POST /test/run and GET /test/report; every system exposes
POST /test/setup and GET /test/report next to the pod's project API (a system /test/run is not
required, so ours has none). Error bodies are {"message", "source"}, with source tester, system,
communication or unknown: 400 for an invalid request, 404 for an unknown session, 409 for a
conflict or a report that isn't ready, 500 for an aborted operation or a service failure.
GET /test (a short description of the service) is our own extra. The schemas below are the
single source for the routes and the /test section of docs/openapi.yaml.
"""

import json
import re
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from tester.coverage import unavailable

MAX_SESSIONS = 200
SOURCES = ("tester", "system", "communication", "unknown")


class CollapseSlashes:
    """ASGI middleware: //test/setup -> /test/setup, so a base URL registered with a trailing
    slash still reaches every route when a client appends "/test/..." to it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and "//" in scope["path"]:
            path = re.sub(r"/{2,}", "/", scope["path"])
            scope = {**scope, "path": path, "raw_path": path.encode()}
        await self.app(scope, receive, send)


# -- schemas ----------------------------------------------------------------------------------

ERROR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["message", "source"],
    "properties": {
        "message": {"type": "string", "minLength": 1},
        "source": {"type": "string", "enum": list(SOURCES)},
    },
}
INFO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["service", "role", "endpoints"],
    "properties": {
        "service": {"type": "string"},
        "role": {"type": "string", "enum": ["system", "tester"]},
        "description": {"type": "string"},
        "endpoints": {"type": "object", "additionalProperties": {"type": "string"}},
    },
}
SESSION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["session_id"],
    "properties": {"session_id": {"type": "string", "minLength": 1}},
}
SYSTEM_SETUP_BODY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["session_id"],
    "properties": {
        "session_id": {"type": "string", "minLength": 1},
        "setup": {
            "type": "object",
            "description": "Pod-defined starting data; {} if none. Optional: now (date-time) sets "
            "the test clock after the reset.",
            "properties": {"now": {"type": "string", "format": "date-time"}},
        },
    },
}
TESTER_SETUP_BODY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["target_url"],
    "properties": {"target_url": {"type": "string", "format": "uri"}},
}
COVERAGE_ENTRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["covered", "total", "basis"],
    "properties": {
        "covered": {"type": ["integer", "null"], "minimum": 0},
        "total": {"type": ["integer", "null"], "minimum": 0},
        "basis": {"type": "string", "minLength": 1},
    },
}
SYSTEM_REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["session_id", "coverage"],
    "properties": {
        "session_id": {"type": "string"},
        "coverage": {
            "type": "object",
            "required": ["code"],
            "properties": {"code": COVERAGE_ENTRY_SCHEMA},
        },
    },
}
RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["test_id", "outcome", "message"],
    "properties": {
        "test_id": {"type": "string", "minLength": 1},
        "outcome": {"type": "string", "enum": ["pass", "fail", "error", "skip"]},
        "source": {"type": "string", "enum": list(SOURCES)},
        "message": {"type": "string", "minLength": 1},
        "ac": {"type": "string"},
        "required": {"type": "boolean"},
    },
}
SUITE_REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["session_id", "target_url", "results", "coverage"],
    "properties": {
        "session_id": {"type": "string"},
        "target_url": {"type": "string"},
        "results": {"type": "array", "items": RESULT_SCHEMA},
        "coverage": {
            "type": "object",
            "required": ["code", "component", "system"],
            "properties": {
                "code": COVERAGE_ENTRY_SCHEMA,
                "component": COVERAGE_ENTRY_SCHEMA,
                "system": COVERAGE_ENTRY_SCHEMA,
                "model": COVERAGE_ENTRY_SCHEMA,
            },
        },
        "summary": {"type": "object", "additionalProperties": {"type": "integer"}},
    },
}


def _json(schema: dict[str, Any], description: str) -> dict[str, Any]:
    return {"description": description, "content": {"application/json": {"schema": schema}}}


def _body(schema: dict[str, Any]) -> dict[str, Any]:
    return {"requestBody": {"required": True, "content": {"application/json": {"schema": schema}}}}


# -- plumbing ---------------------------------------------------------------------------------


class HarnessError(Exception):
    """A /test error: status, a nonempty message and its source. code is only for our own
    /api/v1/runs endpoint, which keeps the project's {"error": {"code", "message"}} shape."""

    def __init__(self, status: int, message: str, source: str, code: str = "ERROR") -> None:
        super().__init__(message)
        self.status, self.message, self.code = status, message or "error", code
        self.source = source if source in SOURCES else "unknown"


def error(exc: HarnessError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status, content={"message": exc.message, "source": exc.source}
    )


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def read_params(request: Request, source: str) -> dict[str, Any]:
    """Query parameters merged with an optional JSON-object body (body wins)."""
    params: dict[str, Any] = dict(request.query_params)
    raw = await request.body()
    if raw.strip():
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HarnessError(400, "request body must be a JSON object", source) from exc
        if not isinstance(body, dict):
            raise HarnessError(400, "request body must be a JSON object", source)
        params.update({k: v for k, v in body.items() if v is not None})
    return params


def session_id_of(params: dict[str, Any], source: str) -> str:
    sid = params.get("session_id")
    if not isinstance(sid, str) or not sid.strip():
        raise HarnessError(400, "session_id must be a nonempty string", source)
    return sid


class Sessions:
    """Sessions by id, oldest dropped first after MAX_SESSIONS; kept until the process stops."""

    def __init__(self) -> None:
        self._items: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.lock = threading.Lock()

    def reserve(self, sid: str, session: dict[str, Any]) -> bool:
        """Add a new session; False if the id already exists."""
        with self.lock:
            if sid in self._items:
                return False
            self._items[sid] = session
            while len(self._items) > MAX_SESSIONS:
                self._items.popitem(last=False)
            return True

    def drop(self, sid: str) -> None:
        with self.lock:
            self._items.pop(sid, None)

    def get(self, sid: str) -> dict[str, Any] | None:
        with self.lock:
            return self._items.get(sid)


def _info(router: APIRouter, role: str, description: str, endpoints: dict[str, str]) -> None:
    @router.get(
        "", responses={200: _json(INFO_SCHEMA, "What this service is and its /test endpoints")}
    )
    def info() -> dict[str, Any]:
        return {
            "service": "ReleaseGate",
            "role": role,
            "description": description,
            "endpoints": endpoints,
        }


def _report_session_id(session_id: str | None, source: str) -> str:
    if session_id is None or not session_id.strip():
        raise HarnessError(400, "the session_id query parameter is required", source)
    return session_id


# -- system -----------------------------------------------------------------------------------

Prepare = Callable[[str, dict[str, Any]], None]
CodeCoverage = Callable[[str], dict[str, Any]]


def system_router(description: str, prepare: Prepare, code_coverage: CodeCoverage) -> APIRouter:
    """POST /test/setup prepares state for the supplied session id (prepare(session_id, setup));
    GET /test/report returns that session's code coverage (code_coverage(session_id))."""
    router = APIRouter(prefix="/test", tags=["autograder harness"])
    sessions = Sessions()
    _info(
        router,
        "system",
        description,
        {"setup": "POST /test/setup", "report": "GET /test/report?session_id=<id>"},
    )

    @router.post(
        "/setup",
        status_code=201,
        openapi_extra=_body(SYSTEM_SETUP_BODY_SCHEMA),
        responses={
            201: _json(SESSION_SCHEMA, "Resources and initial state are ready"),
            400: _json(ERROR_SCHEMA, "Invalid request"),
            409: _json(ERROR_SCHEMA, "The session ID already exists"),
            500: _json(ERROR_SCHEMA, "Preparation failed"),
        },
    )
    async def setup(request: Request) -> Any:
        try:
            params = await read_params(request, "system")
            sid = session_id_of(params, "system")
            start = params.get("setup", {})
            if not isinstance(start, dict):
                raise HarnessError(400, "setup must be a JSON object ({} if none)", "system")
            if params.get("now") and "now" not in start:  # older callers sent now at the top
                start = {**start, "now": params["now"]}
            if not sessions.reserve(sid, {"state": "preparing", "created_at": _now()}):
                raise HarnessError(409, f"session {sid} already exists", "system")
        except HarnessError as exc:
            return error(exc)
        try:
            await run_in_threadpool(prepare, sid, start)
        except HarnessError as exc:
            sessions.drop(sid)
            return error(exc)
        except Exception as exc:  # noqa: BLE001 - any preparation failure is a 500 from the system
            sessions.drop(sid)
            return error(HarnessError(500, f"could not prepare session {sid}: {exc}", "system"))
        session = sessions.get(sid)
        if session is not None:
            session["state"] = "ready"
        return JSONResponse(status_code=201, content={"session_id": sid})

    @router.get(
        "/report",
        responses={
            200: _json(SYSTEM_REPORT_SCHEMA, "Code coverage measured for this session so far"),
            400: _json(ERROR_SCHEMA, "Missing session_id"),
            404: _json(ERROR_SCHEMA, "Unknown session"),
            409: _json(ERROR_SCHEMA, "Preparation is still in progress"),
        },
    )
    def report(session_id: str | None = None) -> Any:
        try:
            sid = _report_session_id(session_id, "system")
            session = sessions.get(sid)
            if session is None:
                raise HarnessError(404, f"unknown session {sid}", "system")
            if session["state"] != "ready":
                raise HarnessError(409, f"session {sid} is still being prepared", "system")
        except HarnessError as exc:
            return error(exc)
        return {"session_id": sid, "coverage": {"code": code_coverage(sid)}}

    return router


# -- tester -----------------------------------------------------------------------------------

TesterSetup = Callable[[str, dict[str, Any]], dict[str, Any]]
TesterRun = Callable[[str, dict[str, Any]], dict[str, Any]]


def tester_router(description: str, setup: TesterSetup, run: TesterRun) -> APIRouter:
    """setup(session_id, params) checks the target, prepares it through its system setup and
    returns the fields to keep (target_url, ...), or raises HarnessError. run(session_id, session)
    runs the suite and returns the complete suite report. One run per session."""
    router = APIRouter(prefix="/test", tags=["autograder harness"])
    sessions = Sessions()
    _info(
        router,
        "tester",
        description,
        {
            "setup": "POST /test/setup",
            "run": "POST /test/run",
            "report": "GET /test/report?session_id=<id>",
        },
    )

    @router.post(
        "/setup",
        status_code=201,
        openapi_extra=_body(TESTER_SETUP_BODY_SCHEMA),
        responses={
            201: _json(SESSION_SCHEMA, "The target system is ready; same session ID"),
            400: _json(ERROR_SCHEMA, "Invalid request or target URL"),
            500: _json(ERROR_SCHEMA, "Setup failed (system setup errors keep their status)"),
        },
    )
    async def setup_route(request: Request) -> Any:
        sid = str(uuid.uuid4())
        try:
            params = await read_params(request, "tester")
            fields = await run_in_threadpool(setup, sid, params)
        except HarnessError as exc:
            return error(exc)
        except Exception as exc:  # noqa: BLE001 - a setup failure inside the tester
            return error(HarnessError(500, f"tester setup failed: {exc}", "tester"))
        sessions.reserve(sid, {**fields, "state": "ready", "report": None})
        return JSONResponse(status_code=201, content={"session_id": sid})

    @router.post(
        "/run",
        openapi_extra=_body(SESSION_SCHEMA),
        responses={
            200: _json(SUITE_REPORT_SCHEMA, "The complete suite report"),
            400: _json(ERROR_SCHEMA, "Invalid request"),
            404: _json(ERROR_SCHEMA, "Unknown session"),
            409: _json(ERROR_SCHEMA, "The session's suite is running or has already run"),
            500: _json(ERROR_SCHEMA, "The tester aborted; GET /test/report has what was kept"),
        },
    )
    async def run_route(request: Request) -> Any:
        try:
            params = await read_params(request, "tester")
            sid = session_id_of(params, "tester")
            session = sessions.get(sid)
            if session is None:
                raise HarnessError(404, f"unknown session {sid}", "tester")
            with sessions.lock:
                if session["state"] != "ready":
                    raise HarnessError(
                        409, f"session {sid} has already run; set up a new session", "tester"
                    )
                session["state"] = "running"
        except HarnessError as exc:
            return error(exc)
        try:
            report = await run_in_threadpool(run, sid, session)
        except HarnessError as exc:
            if exc.status == 409:  # the target is busy with another run: nothing ran
                session["state"] = "ready"
                return error(exc)
            session.update(state="aborted", report=_aborted(sid, session, exc.message))
            return error(HarnessError(500, exc.message, exc.source))
        except Exception as exc:  # noqa: BLE001 - the tester itself failed
            message = f"the tester aborted: {type(exc).__name__}: {exc}"
            session.update(state="aborted", report=_aborted(sid, session, message))
            return error(HarnessError(500, message, "tester"))
        session.update(state="completed", report=report)
        return report

    @router.get(
        "/report",
        responses={
            200: _json(SUITE_REPORT_SCHEMA, "The stored suite report"),
            400: _json(ERROR_SCHEMA, "Missing session_id"),
            404: _json(ERROR_SCHEMA, "Unknown session"),
            409: _json(ERROR_SCHEMA, "The suite has not ended; try again later"),
        },
    )
    def report_route(session_id: str | None = None) -> Any:
        try:
            sid = _report_session_id(session_id, "tester")
            session = sessions.get(sid)
            if session is None:
                raise HarnessError(404, f"unknown session {sid}", "tester")
            if session["state"] in ("ready", "running"):
                raise HarnessError(409, f"the suite for session {sid} has not ended", "tester")
        except HarnessError as exc:
            return error(exc)
        return session["report"]

    return router


def _aborted(sid: str, session: dict[str, Any], message: str) -> dict[str, Any]:
    """What an aborted run keeps: the error, and every coverage measure unavailable."""
    why = "The tester aborted before the suite finished."
    return {
        "session_id": sid,
        "target_url": session.get("target_url", ""),
        "results": [
            {"test_id": "suite.aborted", "outcome": "error", "source": "tester", "message": message}
        ],
        "coverage": {
            "code": unavailable(why),
            "component": unavailable(why),
            "system": unavailable(why),
        },
        "summary": {"pass": 0, "fail": 0, "error": 1, "skip": 0},
    }
