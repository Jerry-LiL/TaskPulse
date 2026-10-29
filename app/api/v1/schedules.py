from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, rate_limiter
from app.database import get_db
from app.models.job import Job, JobStatus
from app.models.schedule import Schedule
from app.models.user import User
from app.schemas.job import JobResponse
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleResponse,
    ScheduleUpdate,
)
from app.worker.tasks import calculate_next_run, execute_job

router = APIRouter(prefix="/schedules", tags=["schedules"], dependencies=[Depends(rate_limiter)])


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(
    schedule_in: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    next_run = calculate_next_run(
        cron_expression=schedule_in.cron_expression,
        interval_seconds=schedule_in.interval_seconds,
    )

    schedule = Schedule(
        user_id=current_user.id,
        name=schedule_in.name,
        description=schedule_in.description,
        job_type=schedule_in.job_type,
        payload=schedule_in.payload,
        cron_expression=schedule_in.cron_expression,
        interval_seconds=schedule_in.interval_seconds,
        is_active=True,
        next_run_at=next_run,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.get("", response_model=list[ScheduleResponse])
def list_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Schedule)
        .filter(Schedule.user_id == current_user.id)
        .order_by(Schedule.created_at.desc())
        .all()
    )


@router.get("/{schedule_id}", response_model=ScheduleResponse)
def get_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    if schedule.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this schedule",
        )
    return schedule


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(
    schedule_id: str,
    update_in: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    if schedule.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this schedule",
        )

    cadence_changed = False
    if update_in.name is not None:
        schedule.name = update_in.name
    if update_in.description is not None:
        schedule.description = update_in.description
    if update_in.job_type is not None:
        schedule.job_type = update_in.job_type
    if update_in.payload is not None:
        schedule.payload = update_in.payload

    if update_in.cron_expression is not None:
        schedule.cron_expression = update_in.cron_expression
        schedule.interval_seconds = None
        cadence_changed = True
    elif update_in.interval_seconds is not None:
        schedule.interval_seconds = update_in.interval_seconds
        schedule.cron_expression = None
        cadence_changed = True

    if update_in.is_active is not None:
        if update_in.is_active and not schedule.is_active:
            cadence_changed = True
        schedule.is_active = update_in.is_active

    if cadence_changed and schedule.is_active:
        schedule.next_run_at = calculate_next_run(
            cron_expression=schedule.cron_expression,
            interval_seconds=schedule.interval_seconds,
        )
    elif not schedule.is_active:
        schedule.next_run_at = None

    db.commit()
    db.refresh(schedule)
    return schedule


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    if schedule.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this schedule",
        )

    db.delete(schedule)
    db.commit()
    return None


@router.post("/{schedule_id}/trigger", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def trigger_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    if schedule.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to trigger this schedule",
        )

    job = Job(
        user_id=current_user.id,
        schedule_id=schedule.id,
        job_type=schedule.job_type,
        payload=schedule.payload,
        status=JobStatus.QUEUED.value,
    )
    db.add(job)

    schedule.last_run_at = datetime.now(timezone.utc)
    schedule.total_runs += 1

    db.commit()
    db.refresh(job)

    try:
        task = execute_job.delay(job.id)
        job.celery_task_id = task.id
        db.commit()
        db.refresh(job)
    except Exception:
        pass

    return job
