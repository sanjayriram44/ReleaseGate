from typing import Annotated

from fastapi import APIRouter, Path

from app.deps import ClockDep, DbDep
from app.errors import ApiError
from app.models import AffectedReleaseResult, Error
from app.services import matching
from app.services.vulnerability_source import FixtureSource, SourceUnavailable

router = APIRouter(prefix="/api/v1/vulnerabilities", tags=["vulnerabilities"])

CVE_PATTERN = "^CVE-[0-9]{4}-[0-9]+$"


@router.get(
    "/{cveId}/affected-releases",
    response_model=AffectedReleaseResult,
    responses={400: {"model": Error}, 404: {"model": Error}, 503: {"model": Error}},
)
def affected_releases(
    cveId: Annotated[str, Path(pattern=CVE_PATTERN)], db: DbDep, clock: ClockDep
) -> AffectedReleaseResult:
    """Format (400, checked by the path pattern), then reachability (503), then existence
    (404): an outage must never look like an unknown CVE or an empty result. Read-only."""
    conn = db.connect()
    try:
        try:
            affected = FixtureSource(conn).affected_purls(cveId)
        except SourceUnavailable as exc:
            raise ApiError(
                503,
                "VULNERABILITY_SOURCE_UNREACHABLE",
                "Vulnerability information is currently unavailable",
                {"source": "fixture", "reason": str(exc)},
            ) from exc
        if affected is None:
            raise ApiError(404, "CVE_UNKNOWN", f"CVE identifier {cveId} is not known")
        return matching.affected_releases(conn, clock, cveId, affected)
    finally:
        conn.close()
