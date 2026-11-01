from fastapi import APIRouter, Request

from app.deps import ClockDep, DbDep, UserDep
from app.models import Error, FixAvailable, Incident, IncidentCreate, SubmissionCreate
from app.request_log import LOG_FIELDS
from app.services import incidents as svc

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


def _logged(request: Request, incident: Incident) -> Incident:
    """Add the overdue-deadline count to this request's log line (CLAUDE.md §8)."""
    deadlines = incident.deadlines
    stages = (deadlines.early_warning, deadlines.vulnerability_notification, deadlines.final_report)
    setattr(
        request.state, LOG_FIELDS, {"overdue_deadlines": sum(d.status == "overdue" for d in stages)}
    )
    return incident


@router.post("", status_code=201, response_model=Incident, responses={400: {"model": Error}})
def create_incident(
    request: Request, body: IncidentCreate, user_id: UserDep, db: DbDep, clock: ClockDep
) -> Incident:
    with db.transaction() as conn:
        return _logged(request, svc.create(conn, clock, user_id, body))


@router.get("/{incidentId}", response_model=Incident, responses={404: {"model": Error}})
def get_incident(request: Request, incidentId: str, db: DbDep, clock: ClockDep) -> Incident:
    conn = db.connect()
    try:
        return _logged(request, svc.to_incident(conn, svc.get_row(conn, incidentId), clock))
    finally:
        conn.close()


@router.patch(
    "/{incidentId}",
    response_model=Incident,
    responses={400: {"model": Error}, 404: {"model": Error}},
)
def record_fix(
    request: Request,
    incidentId: str,
    body: FixAvailable,
    user_id: UserDep,
    db: DbDep,
    clock: ClockDep,
) -> Incident:
    with db.transaction() as conn:
        return _logged(request, svc.record_fix(conn, clock, user_id, incidentId, body))


@router.post(
    "/{incidentId}/submissions",
    status_code=201,
    response_model=Incident,
    responses={400: {"model": Error}, 404: {"model": Error}, 409: {"model": Error}},
)
def record_submission(
    request: Request,
    incidentId: str,
    body: SubmissionCreate,
    user_id: UserDep,
    db: DbDep,
    clock: ClockDep,
) -> Incident:
    with db.transaction() as conn:
        return _logged(request, svc.record_submission(conn, clock, user_id, incidentId, body))
