from datetime import datetime, timedelta, timezone
from croniter import croniter
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models.job import Job, JobStatus
from app.models.schedule import Schedule
from app.worker.handlers import dispatch_job_handler
from app.worker.webhook_dispatcher import dispatch_event_to_user_webhooks


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def calculate_next_run(
    cron_expression: str | None = None,
    interval_seconds: int | None = None,
    base_time: datetime | None = None,
) -> datetime | None:
    now = base_time or utcnow()
    if cron_expression:
        itr = croniter(cron_expression, now)
        next_dt = itr.get_next(datetime)
        if next_dt.tzinfo is None:
            next_dt = next_dt.replace(tzinfo=timezone.utc)
        return next_dt
    elif interval_seconds:
        return now + timedelta(seconds=interval_seconds)
    return None


def run_job_execution(db: Session, job_id: str) -> Job:
    """Core job execution logic, usable directly in tests or via Celery."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise ValueError(f"Job {job_id} not found")

    if job.status == JobStatus.CANCELLED.value:
        return job

    job.status = JobStatus.RUNNING.value
    job.started_at = utcnow()
    db.commit()

    # Webhook for running
    try:
        dispatch_event_to_user_webhooks(
            db,
            user_id=job.user_id,
            event="job.running",
            payload={"job_id": job.id, "job_type": job.job_type, "status": job.status},
            job_id=job.id,
        )
    except Exception:
        pass

    try:
        result = dispatch_job_handler(job.job_type, job.payload)
        job.status = JobStatus.SUCCEEDED.value
        job.result = result
        job.error = None
        job.completed_at = utcnow()
        db.commit()

        try:
            dispatch_event_to_user_webhooks(
                db,
                user_id=job.user_id,
                event="job.succeeded",
                payload={
                    "job_id": job.id,
                    "job_type": job.job_type,
                    "status": job.status,
                    "result": result,
                },
                job_id=job.id,
            )
        except Exception:
            pass

    except Exception as exc:
        if job.retries < job.max_retries:
            job.retries += 1
            job.status = JobStatus.QUEUED.value
            db.commit()
            raise exc
        else:
            job.status = JobStatus.FAILED.value
            job.error = str(exc)
            job.completed_at = utcnow()
            db.commit()

            try:
                dispatch_event_to_user_webhooks(
                    db,
                    user_id=job.user_id,
                    event="job.failed",
                    payload={
                        "job_id": job.id,
                        "job_type": job.job_type,
                        "status": job.status,
                        "error": str(exc),
                    },
                    job_id=job.id,
                )
            except Exception:
                pass

    return job


@celery_app.task(bind=True, name="app.worker.tasks.execute_job", max_retries=3)
def execute_job(self, job_id: str):
    db: Session = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job or job.status == JobStatus.CANCELLED.value:
            return {"status": "skipped", "job_id": job_id}

        try:
            job = run_job_execution(db, job_id)
            return {"status": job.status, "job_id": job.id}
        except Exception as exc:
            # Re-enqueue with backoff if not maxed out
            if job.retries < job.max_retries:
                countdown = 2 ** job.retries
                raise self.retry(exc=exc, countdown=countdown)
            return {"status": "failed", "job_id": job_id, "error": str(exc)}
    finally:
        db.close()


def process_due_schedules(db: Session, now: datetime | None = None) -> list[str]:
    """Process due schedules, creating jobs and updating next run times."""
    current_time = now or utcnow()
    due_schedules = (
        db.query(Schedule)
        .filter(
            Schedule.is_active == True,
            Schedule.next_run_at <= current_time,
        )
        .all()
    )

    triggered_job_ids = []
    for sched in due_schedules:
        job = Job(
            user_id=sched.user_id,
            schedule_id=sched.id,
            job_type=sched.job_type,
            payload=sched.payload,
            status=JobStatus.QUEUED.value,
        )
        db.add(job)
        db.flush()

        sched.last_run_at = current_time
        sched.total_runs += 1
        sched.next_run_at = calculate_next_run(
            cron_expression=sched.cron_expression,
            interval_seconds=sched.interval_seconds,
            base_time=current_time,
        )
        triggered_job_ids.append(job.id)

    db.commit()

    # Enqueue in Celery
    for j_id in triggered_job_ids:
        try:
            execute_job.delay(j_id)
        except Exception:
            # In testing or standalone mode without Redis broker running
            pass

    return triggered_job_ids


@celery_app.task(name="app.worker.tasks.check_scheduled_jobs")
def check_scheduled_jobs():
    db: Session = SessionLocal()
    try:
        job_ids = process_due_schedules(db)
        return {"triggered_count": len(job_ids), "job_ids": job_ids}
    finally:
        db.close()
