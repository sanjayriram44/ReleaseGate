"""One structured JSON log line per request (CLAUDE.md §8).

Each line carries the request ID, X-User-Id, method, path, status, latency, and the clock value
when the request arrived (and whether the test clock overrode it), so a failing test can be
replayed (report §7.4). Error responses add their error code and message, which gives the
error rates, the 503 rate and the SBOM rejection reasons. The request ID is echoed in
X-Request-Id; a caller's own ID is kept when it's short and safe.
"""

import json
import logging
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.clock import Clock, format_utc

LOGGER_NAME = "releasegate.request"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_MAX_MESSAGE = 300
_MAX_ERROR_BODY = 64 * 1024

logger = logging.getLogger(LOGGER_NAME)


class JsonFormatter(logging.Formatter):
    """Write a record's fields as one JSON object, led by the wall time it was logged."""

    def format(self, record: logging.LogRecord) -> str:
        wall = datetime.fromtimestamp(record.created, UTC)
        return json.dumps({"time": format_utc(wall), **record.__dict__.get("fields", {})})


def configure_logging() -> None:
    """Send request lines to stdout as JSON; safe to call more than once."""
    if not any(isinstance(h.formatter, JsonFormatter) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope["headers"]:
        if key.lower() == name:
            return str(value.decode("latin-1"))
    return None


def _error_fields(body: bytes) -> dict[str, str]:
    try:
        error = json.loads(body)["error"]
        code, message = str(error["code"]), str(error["message"])
    except (ValueError, KeyError, TypeError):
        return {}
    if len(message) > _MAX_MESSAGE:
        message = message[:_MAX_MESSAGE] + "..."
    return {"error_code": code, "error_message": message}


class RequestLog:
    """ASGI middleware that logs each HTTP request once it has been answered."""

    def __init__(self, app: ASGIApp, clock: Clock) -> None:
        self.app = app
        self.clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        given = _header(scope, b"x-request-id")
        request_id = given if given and _SAFE_ID.match(given) else uuid.uuid4().hex
        user_id = (_header(scope, b"x-user-id") or "").strip() or None
        fields: dict[str, Any] = {
            "request_id": request_id,
            "user_id": user_id,
            "method": scope["method"],
            "path": scope["path"],
            "status": 500,
            "latency_ms": 0.0,
            "clock": format_utc(self.clock.now()),
            "clock_overridden": self.clock.overridden(),
        }
        error_body = bytearray()

        async def send_logged(message: Message) -> None:
            if message["type"] == "http.response.start":
                fields["status"] = message["status"]
                headers = [h for h in message.get("headers", []) if h[0] != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            elif message["type"] == "http.response.body" and fields["status"] >= 400:
                if len(error_body) < _MAX_ERROR_BODY:
                    error_body.extend(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_logged)
        except Exception as exc:
            fields["error_code"] = type(exc).__name__
            raise
        finally:
            fields["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            if error_body:
                fields.update(_error_fields(bytes(error_body)))
            logger.info("request", extra={"fields": fields})
