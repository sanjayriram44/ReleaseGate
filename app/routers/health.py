from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.deps import DbDep
from app.services.vulnerability_source import current_mode

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request, db: DbDep) -> JSONResponse:
    """Our own endpoint (not in the shared contract): is the database writable, and which
    commit is running?"""
    commit = request.app.state.settings.commit
    try:
        with db.transaction() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _health_probe (x INTEGER)")
            conn.execute("INSERT INTO _health_probe VALUES (1)")
            raise _Rollback
    except _Rollback:
        conn = db.connect()
        try:
            mode = current_mode(conn)
        finally:
            conn.close()
        return JSONResponse({"status": "ok", "commit": commit, "source_mode": mode})
    except Exception as exc:
        return JSONResponse(
            {"status": "unavailable", "commit": commit, "detail": str(exc)}, status_code=503
        )


class _Rollback(Exception):
    """Raised to roll the probe write back."""
