import json

from fastapi import APIRouter

from app.deps import DbDep
from app.errors import ApiError
from app.models import AuditEvent, AuditLogList, Error

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit"])


@router.get("", response_model=AuditLogList)
def list_events(db: DbDep) -> AuditLogList:
    conn = db.connect()
    try:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
    finally:
        conn.close()
    return AuditLogList(
        events=[
            AuditEvent(
                event_id=r["event_id"],
                timestamp=r["timestamp"],
                user_id=r["user_id"],
                action=r["action"],
                entity_type=r["entity_type"],
                entity_id=r["entity_id"],
                details=json.loads(r["details"]) if r["details"] is not None else None,
            )
            for r in rows
        ]
    )


@router.patch("/{eventId}", status_code=405, responses={405: {"model": Error}})
def patch_event(eventId: str) -> None:
    raise ApiError(405, "AUDIT_IMMUTABLE", "audit log entries cannot be modified")


@router.delete("/{eventId}", status_code=405, responses={405: {"model": Error}})
def delete_event(eventId: str) -> None:
    raise ApiError(405, "AUDIT_IMMUTABLE", "audit log entries cannot be deleted")
