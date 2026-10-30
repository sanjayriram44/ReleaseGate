from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from app.clock import format_utc, parse_utc
from app.deps import ClockDep, DbDep
from app.models import DateTimeStr

router = APIRouter(prefix="/api/v1/test", tags=["test"])


class ClockBody(BaseModel):
    model_config = ConfigDict(strict=True)

    now: DateTimeStr


class ClockState(BaseModel):
    now: DateTimeStr


@router.post("/reset", status_code=204)
def reset(db: DbDep, clock: ClockDep) -> Response:
    db.reset()
    clock.reset()
    return Response(status_code=204)


@router.put("/clock", response_model=ClockState)
def set_clock(body: ClockBody, clock: ClockDep) -> ClockState:
    dt = parse_utc(body.now)
    clock.set(dt)
    return ClockState(now=format_utc(dt))
