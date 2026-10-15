from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.deps import DbDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: DbDep) -> JSONResponse:
    """Our own endpoint (not in the shared contract): is the database writable?"""
    try:
        with db.transaction() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _health_probe (x INTEGER)")
            conn.execute("INSERT INTO _health_probe VALUES (1)")
            raise _Rollback
    except _Rollback:
        return JSONResponse({"status": "ok"})
    except Exception as exc:
        return JSONResponse({"status": "unavailable", "detail": str(exc)}, status_code=503)


class _Rollback(Exception):
    """Raised to roll the probe write back."""
