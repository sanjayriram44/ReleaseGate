"""PUT .../report-data/{stage} and GET .../reports/{stage} (REQ-07, REQ-08; CLAUDE.md §6.3,
§6.4). Built on the proposed answers to P5-Q1..Q6 (docs/decisions.md, provisional)."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Path, Request
from starlette.concurrency import run_in_threadpool

from app.clock import Clock
from app.db import Database
from app.deps import ClockDep, DbDep, UserDep
from app.errors import ApiError, is_json_media_type
from app.models import Error, GeneratedReport
from app.services import report_store
from app.services.incidents import get_row
from app.services.reports import STAGE_FIELDS, build_report, check_stage, validate_report_data

router = APIRouter(prefix="/api/v1/incidents", tags=["reports"])

# Checked in the handler, not by FastAPI, so an unknown incident is 404 before a bad stage is 400
# (P5-Q5); the published schema is still the contract's ReportStage enum.
StagePath = Annotated[str, Path(json_schema_extra={"enum": list(STAGE_FIELDS)})]

_REPORT_DATA_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ReportData"}}},
    }
}


@router.put(
    "/{incidentId}/report-data/{stage}",
    response_model=GeneratedReport,
    response_model_exclude_unset=True,
    responses={400: {"model": Error}, 404: {"model": Error}},
    openapi_extra=_REPORT_DATA_BODY,
)
async def put_report_data(
    incidentId: str,
    stage: StagePath,
    request: Request,
    user_id: UserDep,
    db: DbDep,
    clock: ClockDep,
) -> GeneratedReport:
    raw = await request.body()
    content_type = request.headers.get("content-type")
    return await run_in_threadpool(_store, incidentId, stage, raw, content_type, user_id, db, clock)


def _parse(raw: bytes, content_type: str | None) -> Any:
    if not is_json_media_type(content_type):
        raise ApiError(400, "INVALID_REQUEST", "Content-Type must be application/json")
    try:
        return json.loads(raw)
    except ValueError as exc:  # also UnicodeDecodeError
        raise ApiError(400, "INVALID_REQUEST", "request body is not valid JSON") from exc


def _store(
    incident_id: str,
    stage: str,
    raw: bytes,
    content_type: str | None,
    user_id: str,
    db: Database,
    clock: Clock,
) -> GeneratedReport:
    # 404, then the stage, then the body: validate fully before writing anything.
    conn = db.connect()
    try:
        get_row(conn, incident_id)
    finally:
        conn.close()
    checked = check_stage(stage)
    data = validate_report_data(checked, _parse(raw, content_type))
    with db.transaction() as tx:
        get_row(tx, incident_id)
        report_store.store(tx, clock, user_id, incident_id, checked, data)
    return build_report(incident_id, checked, data, clock.now())


@router.get(
    "/{incidentId}/reports/{stage}",
    response_model=GeneratedReport,
    response_model_exclude_unset=True,
    responses={400: {"model": Error}, 404: {"model": Error}},
)
def get_report(incidentId: str, stage: StagePath, db: DbDep, clock: ClockDep) -> GeneratedReport:
    """Computed on every read from the stored data and the clock; stores and audits nothing."""
    conn = db.connect()
    try:
        get_row(conn, incidentId)
        checked = check_stage(stage)
        return build_report(
            incidentId, checked, report_store.load(conn, incidentId, checked), clock.now()
        )
    finally:
        conn.close()
