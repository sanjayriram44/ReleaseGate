import re
from datetime import UTC, datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from app.clock import format_utc
from app.deps import ClockDep, DbDep
from app.errors import ApiError

router = APIRouter(prefix="/api/v1/test", tags=["test"])

_UTC_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


class ClockBody(BaseModel):
    model_config = ConfigDict(strict=True)

    now: str


class ClockState(BaseModel):
    now: str


@router.post("/reset", status_code=204)
def reset(db: DbDep, clock: ClockDep) -> Response:
    db.reset()
    clock.reset()
    return Response(status_code=204)


@router.put("/clock", response_model=ClockState)
def set_clock(body: ClockBody, clock: ClockDep) -> ClockState:
    if not _UTC_TS.match(body.now):
        raise ApiError(400, "INVALID_REQUEST", "now must be a UTC timestamp ending in Z")
    try:
        dt = datetime.fromisoformat(body.now).astimezone(UTC)
    except ValueError as exc:
        raise ApiError(400, "INVALID_REQUEST", "now is not a valid timestamp") from exc
    clock.set(dt)
    return ClockState(now=format_utc(dt))
