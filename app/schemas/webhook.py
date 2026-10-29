from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WebhookCreate(BaseModel):
    url: str = Field(..., max_length=500)
    secret: str | None = Field(default=None, max_length=128)
    event_types: list[str] = Field(default_factory=lambda: ["*"])

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        clean = v.strip()
        if not (clean.startswith("http://") or clean.startswith("https://")):
            raise ValueError("Webhook URL must begin with http:// or https://")
        return clean


class WebhookResponse(BaseModel):
    id: str
    user_id: str
    url: str
    secret: str
    event_types: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryResponse(BaseModel):
    id: str
    webhook_id: str
    job_id: str | None
    event: str
    payload: dict[str, Any]
    status_code: int | None
    response_body: str | None
    error: str | None
    duration_ms: float | None
    attempt: int
    succeeded: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
