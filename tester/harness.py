"""Course autograder harness: GET /test, POST /test/setup, POST /test/run, GET /test/report.

Mounted on both the system and the tester. setup creates a session (and resets state), run
executes the AC-01..AC-03 suite for that session, report returns the stored result. The
schemas below are the single source for both the routes and docs/openapi.yaml.
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

from tester.checks import Report

MAX_SESSIONS = 50


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


ERROR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["error"],
    "properties": {
        "error": {
            "type": "object",
            "required": ["code", "message"],
            "properties": {"code": {"type": "string"}, "message": {"type": "string"}},
        }
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
SESSION_BODY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "Optional. All fields optional; query parameters with the same names also work.",
    "properties": {
        "session_id": {
            "type": "string",
            "description": "Setup: use this id instead of a generated one. Run: which session.",
        },
        "target_base_url": {
            "type": "string",
            "description": "Tester only: system base URL to test. Defaults to our deployed system.",
        },
        "now": {
            "type": "string",
            "format": "date-time",
            "description": "System only: set the reference clock (UTC, trailing Z) after reset.",
        },
    },
}
SETUP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["session_id", "status", "role"],
    "properties": {
        "session_id": {"type": "string"},
        "status": {"type": "string", "enum": ["ready"]},
        "role": {"type": "string", "enum": ["system", "tester"]},
        "created_at": {"type": "string", "format": "date-time"},
        "target_base_url": {"type": ["string", "null"]},
    },
}
SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": {"type": "integer"},
    "description": "required_passed, required_failed, informational_passed, informational_failed",
}
RUN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["session_id", "status", "result"],
    "properties": {
        "session_id": {"type": "string"},
        "status": {"type": "string", "enum": ["completed"]},
        "result": {"type": "string", "enum": ["pass", "fail", "error"]},
        "summary": SUMMARY_SCHEMA,
        "report_url": {"type": "string"},
    },
}
REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["session_id", "status", "role", "checks"],
    "properties": {
        "session_id": {"type": "string"},
        "status": {"type": "string", "enum": ["ready", "completed"]},
        "role": {"type": "string", "enum": ["system", "tester"]},
        "target_base_url": {"type": ["string", "null"]},
        "result": {"type": ["string", "null"], "enum": ["pass", "fail", "error", None]},
        "summary": SUMMARY_SCHEMA,
        "error": {"type": ["string", "null"]},
        "started_at": {"type": ["string", "null"]},
        "finished_at": {"type": ["string", "null"]},
        "duration_ms": {"type": ["integer", "null"]},
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "ac", "title", "required", "passed", "expected", "actual"],
                "properties": {
                    "id": {"type": "string"},
                    "ac": {"type": "string"},
                    "title": {"type": "string"},
                    "required": {"type": "boolean"},
                    "passed": {"type": "boolean"},
                    "expected": {"type": "string"},
                    "actual": {"type": "string"},
                    "request": {"type": "string"},
                    "response": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        },
    },
}


def _json(schema: dict[str, Any], description: str) -> dict[str, Any]:
    return {"description": description, "content": {"application/json": {"schema": schema}}}


SESSION_BODY = {
    "requestBody": {
        "required": False,
        "content": {"application/json": {"schema": SESSION_BODY_SCHEMA}},
    }
}


class HarnessError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


SetupHook = Callable[[dict[str, Any]], dict[str, Any]]
RunHook = Callable[[dict[str, Any], dict[str, Any]], Report]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def read_params(request: Request) -> dict[str, Any]:
    """Merge query parameters with an optional JSON-object body (body wins)."""
    params: dict[str, Any] = dict(request.query_params)
    raw = await request.body()
    if raw.strip():
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HarnessError(
                400, "INVALID_REQUEST", "request body must be a JSON object"
            ) from exc
        if not isinstance(body, dict):
            raise HarnessError(400, "INVALID_REQUEST", "request body must be a JSON object")
        params.update({k: v for k, v in body.items() if v is not None})
    return params


def make_router(role: str, description: str, setup: SetupHook, run: RunHook) -> APIRouter:
    """The four /test endpoints. setup(params) may raise HarnessError; run(params, session)."""
    router = APIRouter(prefix="/test", tags=["autograder harness"])
    sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()
    lock = threading.Lock()
    run_lock = threading.Lock()

    def error(exc: HarnessError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}}
        )

    def remember(session: dict[str, Any]) -> None:
        with lock:
            sessions[session["session_id"]] = session
            sessions.move_to_end(session["session_id"])
            while len(sessions) > MAX_SESSIONS:
                sessions.popitem(last=False)

    def find(session_id: str | None) -> dict[str, Any] | None:
        with lock:
            if session_id:
                return sessions.get(str(session_id))
            return next(reversed(sessions.values()), None)

    def do_setup(params: dict[str, Any]) -> dict[str, Any]:
        extra = setup(params)
        session = {
            "session_id": str(params.get("session_id") or f"ses-{uuid.uuid4().hex[:12]}"),
            "status": "ready",
            "role": role,
            "created_at": _now(),
            "target_base_url": extra.get("target_base_url"),
            "report": None,
        }
        remember(session)
        return session

    @router.get(
        "", responses={200: _json(INFO_SCHEMA, "What this service is and its /test endpoints")}
    )
    def info() -> dict[str, Any]:
        return {
            "service": "ReleaseGate",
            "role": role,
            "description": description,
            "endpoints": {
                "setup": "POST /test/setup",
                "run": "POST /test/run",
                "report": "GET /test/report?session_id=<id>",
            },
        }

    @router.api_route(
        "/setup",
        methods=["POST"],
        openapi_extra=SESSION_BODY,
        responses={
            200: _json(SETUP_SCHEMA, "Session created; state reset"),
            400: _json(ERROR_SCHEMA, "Invalid input"),
        },
    )
    @router.api_route("/setup", methods=["GET", "PUT"], include_in_schema=False)
    async def setup_route(request: Request) -> Any:
        try:
            params = await read_params(request)
            session = await run_in_threadpool(do_setup, params)  # setup hooks block (reset, DNS)
        except HarnessError as exc:
            return error(exc)
        return {k: v for k, v in session.items() if k != "report"}

    @router.api_route(
        "/run",
        methods=["POST"],
        openapi_extra=SESSION_BODY,
        responses={
            200: _json(RUN_SCHEMA, "Suite finished; full result at /test/report"),
            400: _json(ERROR_SCHEMA, "Invalid input"),
            404: _json(ERROR_SCHEMA, "Unknown session_id"),
            409: _json(ERROR_SCHEMA, "A run is already in progress"),
        },
    )
    @router.api_route("/run", methods=["GET", "PUT"], include_in_schema=False)
    async def run_route(request: Request) -> Any:
        try:
            params = await read_params(request)
            session = find(params.get("session_id"))
            if session is None:  # no setup yet (or an unknown id): set up, then run
                session = await run_in_threadpool(do_setup, params)
        except HarnessError as exc:
            return error(exc)
        if not run_lock.acquire(blocking=False):
            return error(HarnessError(409, "RUN_IN_PROGRESS", "a run is already in progress"))
        try:
            report = await run_in_threadpool(run, params, session)
        except HarnessError as exc:
            return error(exc)
        finally:
            run_lock.release()
        session["report"] = report
        session["status"] = "completed"
        remember(session)
        return {
            "session_id": session["session_id"],
            "status": "completed",
            "result": report.result,
            "summary": report.summary,
            "report_url": f"/test/report?session_id={session['session_id']}",
        }

    @router.get(
        "/report",
        responses={
            200: _json(REPORT_SCHEMA, "Session result; status 'ready' until /test/run finishes"),
            404: _json(ERROR_SCHEMA, "Unknown session_id, or no session yet"),
        },
    )
    def report_route(session_id: str | None = None) -> Any:
        session = find(session_id)
        if session is None:
            msg = (
                f"session {session_id} not found"
                if session_id
                else "no session yet; call /test/setup"
            )
            return error(HarnessError(404, "SESSION_NOT_FOUND", msg))
        report: Report | None = session["report"]
        body: dict[str, Any] = {
            "session_id": session["session_id"],
            "status": session["status"],
            "role": role,
            "target_base_url": session["target_base_url"],
            "result": None,
            "summary": {},
            "error": None,
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "checks": [],
        }
        if report is not None:
            data = report.to_dict()
            body.update(
                {
                    k: data[k]
                    for k in (
                        "result",
                        "summary",
                        "error",
                        "started_at",
                        "finished_at",
                        "duration_ms",
                        "checks",
                    )
                }
            )
        return body

    return router
