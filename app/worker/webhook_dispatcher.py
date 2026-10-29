from collections.abc import Callable
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any
import httpx
from sqlalchemy.orm import Session

from app.models.webhook import Webhook, WebhookDelivery


def generate_webhook_signature(secret: str, body: str) -> str:
    secret_bytes = secret.encode("utf-8")
    body_bytes = body.encode("utf-8")
    computed = hmac.new(secret_bytes, body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={computed}"


def deliver_webhook_with_retry(
    url: str,
    secret: str,
    event: str,
    payload: dict[str, Any],
    max_retries: int = 3,
    timeout: float = 10.0,
    backoff_factor: float = 2.0,
    client: httpx.Client | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    event_body = {
        "event": event,
        "timestamp": timestamp,
        "payload": payload,
    }
    raw_body = json.dumps(event_body, separators=(",", ":"))
    signature = generate_webhook_signature(secret, raw_body)

    headers = {
        "Content-Type": "application/json",
        "X-TaskPulse-Event": event,
        "X-TaskPulse-Timestamp": timestamp,
        "X-TaskPulse-Signature": signature,
        "User-Agent": "TaskPulse-Webhook/1.0",
    }

    own_client = client is None
    http_client = client or httpx.Client(timeout=timeout)

    last_status_code: int | None = None
    last_response_text: str | None = None
    last_error: str | None = None
    succeeded = False
    total_duration_ms = 0.0
    attempts_made = 0

    try:
        for attempt in range(1, max_retries + 1):
            attempts_made = attempt
            start_time = time.monotonic()
            try:
                resp = http_client.post(url, content=raw_body, headers=headers)
                duration = (time.monotonic() - start_time) * 1000
                total_duration_ms += duration
                last_status_code = resp.status_code
                last_response_text = resp.text[:1000]

                if 200 <= resp.status_code < 300:
                    succeeded = True
                    last_error = None
                    break
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                duration = (time.monotonic() - start_time) * 1000
                total_duration_ms += duration
                last_error = f"{type(exc).__name__}: {str(exc)}"
                last_status_code = None

            if attempt < max_retries:
                delay = backoff_factor ** (attempt - 1)
                sleep_fn(delay)
    finally:
        if own_client:
            http_client.close()

    return {
        "succeeded": succeeded,
        "status_code": last_status_code,
        "response_body": last_response_text,
        "error": last_error,
        "duration_ms": round(total_duration_ms, 2),
        "attempts": attempts_made,
    }


def dispatch_event_to_user_webhooks(
    db: Session,
    user_id: str,
    event: str,
    payload: dict[str, Any],
    job_id: str | None = None,
    client: httpx.Client | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> list[WebhookDelivery]:
    webhooks = (
        db.query(Webhook)
        .filter(Webhook.user_id == user_id, Webhook.is_active == True)
        .all()
    )

    matching = []
    for wh in webhooks:
        types = wh.event_types or []
        if "*" in types or event in types:
            matching.append(wh)

    deliveries = []
    for wh in matching:
        res = deliver_webhook_with_retry(
            url=wh.url,
            secret=wh.secret,
            event=event,
            payload=payload,
            client=client,
            sleep_fn=sleep_fn,
        )

        delivery = WebhookDelivery(
            webhook_id=wh.id,
            job_id=job_id,
            event=event,
            payload=payload,
            status_code=res["status_code"],
            response_body=res["response_body"],
            error=res["error"],
            duration_ms=res["duration_ms"],
            attempt=res["attempts"],
            succeeded=res["succeeded"],
        )
        db.add(delivery)
        deliveries.append(delivery)

    if deliveries:
        db.commit()

    return deliveries
