import sqlite3
from typing import Annotated

from fastapi import Depends, Header, Request

from app.clock import Clock
from app.db import Database
from app.errors import ApiError


def get_db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def require_user_id(x_user_id: Annotated[str | None, Header()] = None) -> str:
    # Provisional (docs/decisions.md): a missing/blank header is 400 INVALID_REQUEST.
    if x_user_id is None or not x_user_id.strip():
        raise ApiError(400, "INVALID_REQUEST", "X-User-Id header is required")
    return x_user_id.strip()


DbDep = Annotated[Database, Depends(get_db)]
ClockDep = Annotated[Clock, Depends(get_clock)]
UserDep = Annotated[str, Depends(require_user_id)]
Conn = sqlite3.Connection
