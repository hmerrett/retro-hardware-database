"""Is it up, and can it reach the database.

Public and content-free on purpose: a deploy's smoke check runs before any
credentials exist, and an uptime monitor should learn nothing from it but up or
down.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
def healthz(db: Session = Depends(get_db)):
    """Liveness plus database reachability, for a deploy's smoke check and any
    uptime monitor. Deliberately public and content-free: it says up or down and
    nothing else, so it needs no login and gives nothing away.

    It touches the database rather than only answering, because a box that is up
    but cannot reach MariaDB serves nothing but errors, and a check that called
    that healthy would let a broken deploy through."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unhealthy"}, status_code=503)
    return {"status": "ok"}
