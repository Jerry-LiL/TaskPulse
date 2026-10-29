from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.redis_client import check_redis_health
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def quick_health():
    return {"status": "ok"}


@router.get("/api/v1/health")
def detailed_health(response: Response, db: Session = Depends(get_db)):
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    redis_ok = check_redis_health()

    is_healthy = db_ok and redis_ok
    status_str = "ok" if is_healthy else "degraded"

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": status_str,
        "database": "connected" if db_ok else "unreachable",
        "redis": "connected" if redis_ok else "unreachable",
    }
