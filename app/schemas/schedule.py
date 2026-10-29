from datetime import datetime
from typing import Any
from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    job_type: str = Field(...)
    payload: dict[str, Any] = Field(default_factory=dict)
    cron_expression: str | None = Field(default=None)
    interval_seconds: int | None = Field(default=None, ge=5)

    @model_validator(mode="after")
    def validate_cadence(self) -> "ScheduleCreate":
        has_cron = bool(self.cron_expression and self.cron_expression.strip())
        has_interval = self.interval_seconds is not None

        if not has_cron and not has_interval:
            raise ValueError("Must provide either 'cron_expression' or 'interval_seconds'")
        if has_cron and has_interval:
            raise ValueError("Provide either 'cron_expression' or 'interval_seconds', not both")

        if has_cron:
            expr = self.cron_expression.strip()
            if not croniter.is_valid(expr):
                raise ValueError(f"Invalid cron expression: '{expr}'")
            self.cron_expression = expr

        return self


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    job_type: str | None = None
    payload: dict[str, Any] | None = None
    cron_expression: str | None = None
    interval_seconds: int | None = Field(default=None, ge=5)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_update(self) -> "ScheduleUpdate":
        if self.cron_expression is not None:
            expr = self.cron_expression.strip()
            if not croniter.is_valid(expr):
                raise ValueError(f"Invalid cron expression: '{expr}'")
            self.cron_expression = expr
        return self


class ScheduleResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str | None
    job_type: str
    payload: dict[str, Any]
    cron_expression: str | None
    interval_seconds: int | None
    is_active: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    total_runs: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
