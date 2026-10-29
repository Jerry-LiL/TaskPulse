from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_JOB_TYPES = {"http_request", "data_processing", "notification", "sleep"}


class JobCreate(BaseModel):
    job_type: str = Field(..., description="Type of job: http_request, data_processing, notification, sleep")
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0, le=10)
    max_retries: int = Field(default=3, ge=0, le=10)

    @field_validator("job_type")
    @classmethod
    def validate_job_type(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_JOB_TYPES:
            raise ValueError(f"job_type must be one of: {', '.join(sorted(ALLOWED_JOB_TYPES))}")
        return clean

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: dict[str, Any], info) -> dict[str, Any]:
        job_type = info.data.get("job_type")
        if job_type == "http_request":
            if "url" not in v or not isinstance(v["url"], str):
                raise ValueError("http_request payload must contain a valid 'url' string")
        return v


class JobResponse(BaseModel):
    id: str
    user_id: str
    schedule_id: str | None
    job_type: str
    status: str
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    priority: int
    retries: int
    max_retries: int
    celery_task_id: str | None
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobListResponse(BaseModel):
    total: int
    items: list[JobResponse]
    limit: int
    offset: int
