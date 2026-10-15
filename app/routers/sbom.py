from typing import Any

from fastapi import APIRouter, Request

from app.clock import Clock
from app.db import Database
from app.deps import ClockDep, DbDep, UserDep
from app.models import ComponentList, Error, SbomStored
from app.services import sbom as svc
from app.services.releases import get_row
from app.services.sbom_validation import parse_and_validate

router = APIRouter(prefix="/api/v1/releases", tags=["sbom"])

_SBOM_REQUEST_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"type": "object", "description": "CycloneDX JSON document"}
            }
        },
    }
}


@router.put(
    "/{releaseId}/sbom",
    response_model=SbomStored,
    responses={400: {"model": Error}, 404: {"model": Error}},
    openapi_extra=_SBOM_REQUEST_BODY,
)
async def put_sbom(
    releaseId: str, request: Request, user_id: UserDep, db: DbDep, clock: ClockDep
) -> SbomStored:
    raw = await request.body()
    return _store(releaseId, raw, user_id, db, clock)


def _store(release_id: str, raw: bytes, user_id: str, db: Database, clock: Clock) -> SbomStored:
    # 404 before body validation (provisional, docs/decisions.md).
    conn = db.connect()
    try:
        get_row(conn, release_id)
    finally:
        conn.close()
    components = parse_and_validate(raw)  # validate fully before writing anything
    with db.transaction() as tx:
        count = svc.replace_components(tx, clock, user_id, release_id, components)
    return SbomStored(release_id=release_id, component_count=count)


@router.get(
    "/{releaseId}/components",
    response_model=ComponentList,
    responses={404: {"model": Error}},
)
def get_components(releaseId: str, db: DbDep) -> ComponentList:
    conn = db.connect()
    try:
        get_row(conn, releaseId)
        return ComponentList(release_id=releaseId, components=svc.list_components(conn, releaseId))
    finally:
        conn.close()
