"""System side of the course autograder harness (/test, /test/setup, /test/run, /test/report).

setup resets all data (like /api/v1/test/reset) and can set the clock; run executes the shared
AC-01..AC-03 suite against this system in-process and leaves it reset afterwards.
"""

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.errors import ApiError
from app.routers.test_support import parse_utc
from tester.checks import Fixtures, Report, run
from tester.harness import HarnessError, make_router


def build_router(app: FastAPI) -> APIRouter:
    fixtures = Fixtures.load(Path(os.environ.get("TESTER_FIXTURES_DIR", "fixtures")))

    def setup(params: dict[str, Any]) -> dict[str, Any]:
        now = params.get("now")
        try:
            dt = parse_utc(str(now)) if now else None
        except ApiError as exc:
            raise HarnessError(exc.status, exc.code, exc.message) from exc
        app.state.db.reset()
        app.state.clock.reset()
        if dt is not None:
            app.state.clock.set(dt)
        return {"target_base_url": None}

    def run_self_test(params: dict[str, Any], session: dict[str, Any]) -> Report:
        client = TestClient(app, base_url="http://releasegate-system")
        return run(client, fixtures, "self (in-process)")

    return make_router(
        "system",
        "ReleaseGate system under test. setup resets all data; run executes the shared "
        "AC-01..AC-03 suite against this system; report returns the result.",
        setup,
        run_self_test,
    )
