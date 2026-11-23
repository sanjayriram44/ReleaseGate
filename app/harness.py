"""System side of the course autograder harness (spec v2): POST /test/setup and GET /test/report.

setup prepares the supplied session: it resets all data (like /api/v1/test/reset) and the test
clock, then sets the clock if setup.now is given. One session's state at a time: a new setup
resets it. report returns the session's code coverage. Per-session runtime instrumentation isn't
enabled on the deployed service, so the counts are null and the basis says why (the spec's rule
for an unavailable measure); our own test suite's app/ line coverage is quoted for context.
"""

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI

from app.clock import parse_utc
from app.errors import ApiError
from tester.coverage import code_coverage, unavailable
from tester.harness import HarnessError, system_router


def build_router(app: FastAPI) -> APIRouter:
    suite = code_coverage(Path(os.environ.get("CODE_COVERAGE_FILE", ".coverage-baseline")))
    basis = (
        "Source lines of the app/ package. Lines executed during this session are not counted: "
        "runtime instrumentation is not enabled on the deployed service, so the counts are null."
    )
    if suite is not None:
        basis += f" For context, our own test suite executes {suite}% of app/ lines."

    def prepare(session_id: str, setup: dict[str, Any]) -> None:
        now = setup.get("now")
        try:
            dt = parse_utc(str(now)) if now else None
        except ApiError as exc:
            raise HarnessError(400, f"setup.{exc.message}", "system") from exc
        app.state.db.reset()
        app.state.clock.reset()
        if dt is not None:
            app.state.clock.set(dt)

    return system_router(
        "ReleaseGate system under test. setup resets all data and prepares the session; report "
        "returns the session's code coverage.",
        prepare,
        lambda _session_id: unavailable(basis),
    )
