from fastapi import APIRouter

from app.deps import ClockDep, DbDep, UserDep
from app.models import Error, FixAvailable, Incident, IncidentCreate, SubmissionCreate
from app.services import incidents as svc

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.post("", status_code=201, response_model=Incident, responses={400: {"model": Error}})
def create_incident(body: IncidentCreate, user_id: UserDep, db: DbDep, clock: ClockDep) -> Incident:
    with db.transaction() as conn:
        return svc.create(conn, clock, user_id, body)


@router.get("/{incidentId}", response_model=Incident, responses={404: {"model": Error}})
def get_incident(incidentId: str, db: DbDep, clock: ClockDep) -> Incident:
    conn = db.connect()
    try:
        return svc.to_incident(conn, svc.get_row(conn, incidentId), clock)
    finally:
        conn.close()


@router.patch(
    "/{incidentId}",
    response_model=Incident,
    responses={400: {"model": Error}, 404: {"model": Error}},
)
def record_fix(
    incidentId: str, body: FixAvailable, user_id: UserDep, db: DbDep, clock: ClockDep
) -> Incident:
    with db.transaction() as conn:
        return svc.record_fix(conn, clock, user_id, incidentId, body)


@router.post(
    "/{incidentId}/submissions",
    status_code=201,
    response_model=Incident,
    responses={400: {"model": Error}, 404: {"model": Error}, 409: {"model": Error}},
)
def record_submission(
    incidentId: str, body: SubmissionCreate, user_id: UserDep, db: DbDep, clock: ClockDep
) -> Incident:
    with db.transaction() as conn:
        return svc.record_submission(conn, clock, user_id, incidentId, body)
