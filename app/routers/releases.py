from fastapi import APIRouter

from app.deps import ClockDep, DbDep, UserDep
from app.models import Error, Release, ReleaseCreate
from app.services import releases as svc

router = APIRouter(prefix="/api/v1/releases", tags=["releases"])


@router.post(
    "",
    status_code=201,
    response_model=Release,
    responses={400: {"model": Error}, 409: {"model": Error}},
)
def register_release(body: ReleaseCreate, user_id: UserDep, db: DbDep, clock: ClockDep) -> Release:
    with db.transaction() as conn:
        return svc.register(conn, clock, user_id, body)


@router.get(
    "/{releaseId}",
    response_model=Release,
    responses={404: {"model": Error}},
)
def get_release(releaseId: str, db: DbDep, clock: ClockDep) -> Release:
    conn = db.connect()
    try:
        return svc.to_release(svc.get_row(conn, releaseId), clock)
    finally:
        conn.close()
