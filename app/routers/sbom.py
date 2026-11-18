from typing import Any

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app.clock import Clock
from app.db import Database
from app.deps import ClockDep, DbDep, UserDep
from app.errors import ApiError
from app.models import ComponentList, Error, SbomStored
from app.services import sbom as svc
from app.services.releases import get_row
from app.services.sbom_validation import parse_and_validate

router = APIRouter(prefix="/api/v1/releases", tags=["sbom"])

# The media types an SBOM upload accepts, compared without parameters such as charset (P5-Q9
# proposal; the contract's request body lists application/json). Anything else is a 400.
SBOM_MEDIA_TYPES = frozenset({"application/json", "application/vnd.cyclonedx+json"})
# A request with no Content-Type at all is undecided (P5-Q9 proposes a 400). Until Team 2 answers,
# it is accepted as before.
ALLOW_MISSING_CONTENT_TYPE = True

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
    content_type = request.headers.get("content-type")
    # Validation and SQLite block; keep them off the event loop so other requests still run.
    # BEGIN IMMEDIATE in db.transaction() serialises concurrent writers.
    return await run_in_threadpool(_store, releaseId, raw, content_type, user_id, db, clock)


def check_media_type(content_type: str | None) -> None:
    """400 unless the Content-Type is one of SBOM_MEDIA_TYPES (or missing, while allowed)."""
    if content_type is None and ALLOW_MISSING_CONTENT_TYPE:
        return
    media = (content_type or "").split(";")[0].strip().lower()
    if media not in SBOM_MEDIA_TYPES:
        raise ApiError(400, "INVALID_REQUEST", "Content-Type must be application/json")


def _store(
    release_id: str,
    raw: bytes,
    content_type: str | None,
    user_id: str,
    db: Database,
    clock: Clock,
) -> SbomStored:
    # 404 before body validation (provisional, docs/decisions.md).
    conn = db.connect()
    try:
        get_row(conn, release_id)
    finally:
        conn.close()
    check_media_type(content_type)
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
