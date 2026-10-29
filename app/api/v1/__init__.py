from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.schedules import router as schedules_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.health import router as health_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(jobs_router)
v1_router.include_router(schedules_router)
v1_router.include_router(webhooks_router)

__all__ = ["v1_router", "health_router"]
