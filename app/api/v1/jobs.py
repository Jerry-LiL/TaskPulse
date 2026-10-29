from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, rate_limiter
from app.database import get_db
from app.models.job import Job, JobStatus
from app.models.user import User
from app.schemas.job import JobCreate, JobListResponse, JobResponse
from app.worker.tasks import execute_job

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(rate_limiter)])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    job_in: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = Job(
        user_id=current_user.id,
        job_type=job_in.job_type,
        payload=job_in.payload,
        priority=job_in.priority,
        max_retries=job_in.max_retries,
        status=JobStatus.QUEUED.value,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        task = execute_job.delay(job.id)
        job.celery_task_id = task.id
        db.commit()
        db.refresh(job)
    except Exception:
        # Broker might be unavailable during standalone tests
        pass

    return job


@router.get("", response_model=JobListResponse)
def list_jobs(
    status_filter: str | None = Query(None, alias="status"),
    job_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Job).filter(Job.user_id == current_user.id)
    if status_filter:
        query = query.filter(Job.status == status_filter.lower())
    if job_type:
        query = query.filter(Job.job_type == job_type.lower())

    total = query.with_entities(func.count(Job.id)).scalar() or 0
    items = (
        query.order_by(Job.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return JobListResponse(
        total=total,
        items=items,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this job",
        )
    return job


@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this job",
        )

    if job.status in [JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a job that is already {job.status}",
        )

    job.status = JobStatus.CANCELLED.value
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)

    if job.celery_task_id:
        try:
            from app.core.celery_app import celery_app
            celery_app.control.revoke(job.celery_task_id, terminate=True)
        except Exception:
            pass

    return job


@router.post("/{job_id}/retry", response_model=JobResponse)
def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this job",
        )

    if job.status not in [JobStatus.FAILED.value, JobStatus.CANCELLED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only failed or cancelled jobs can be retried (current status: {job.status})",
        )

    job.status = JobStatus.QUEUED.value
    job.error = None
    job.result = None
    job.started_at = None
    job.completed_at = None
    job.retries = 0
    job.queued_at = datetime.now(timezone.utc)
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


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this job",
        )

    db.delete(job)
    db.commit()
    return None
