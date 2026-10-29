from celery import Celery
from app.config import settings

celery_app = Celery(
    "taskpulse",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "check-scheduled-jobs": {
            "task": "app.worker.tasks.check_scheduled_jobs",
            "schedule": 15.0,
        },
    },
)

celery_app.autodiscover_tasks(["app.worker"])
