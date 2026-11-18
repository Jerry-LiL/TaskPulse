# TaskPulse

TaskPulse is a background job scheduling and execution service built with FastAPI, Celery, and Redis. It handles background job dispatching, scheduled recurrence, rate limiting, and webhook notifications with retries.

## Features

- Background task execution with status tracking (queued, running, succeeded, failed, cancelled)
- Built-in handlers for HTTP requests, data processing, mock notifications, and sleep
- Recurring schedules via cron expressions or intervals
- Webhook delivery with HMAC-SHA256 signatures and exponential backoff retries
- Token-based authentication (JWT) and Redis-backed rate limiting

## Quick Start (Docker Compose)

```bash
docker compose up --build
```

API: `http://localhost:8000` | Docs: `http://localhost:8000/docs`

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

In separate terminals (requires Redis):
```bash
celery -A app.core.celery_app.celery_app worker --loglevel=info
celery -A app.core.celery_app.celery_app beat --loglevel=info
```

## Running Tests

Tests use SQLite in-memory tables and FakeRedis:

```bash
pytest
```

## API Endpoints

- `POST /api/v1/auth/register` — Register user
- `POST /api/v1/auth/login` — Get access token
- `GET /api/v1/auth/me` — Current user profile
- `POST /api/v1/jobs` — Enqueue job
- `GET /api/v1/jobs` — List jobs (filter by status, job_type)
- `GET /api/v1/jobs/{id}` — Get job details
- `POST /api/v1/jobs/{id}/cancel` — Cancel job
- `POST /api/v1/jobs/{id}/retry` — Retry failed/cancelled job
- `DELETE /api/v1/jobs/{id}` — Delete job
- `POST /api/v1/schedules` — Create schedule (cron or interval)
- `GET /api/v1/schedules` — List schedules
- `GET /api/v1/schedules/{id}` — Get schedule
- `PATCH /api/v1/schedules/{id}` — Update or pause schedule
- `DELETE /api/v1/schedules/{id}` — Delete schedule
- `POST /api/v1/schedules/{id}/trigger` — Run schedule immediately
- `POST /api/v1/webhooks` — Register webhook endpoint
- `GET /api/v1/webhooks` — List webhooks
- `GET /api/v1/webhooks/{id}` — Get webhook
- `DELETE /api/v1/webhooks/{id}` — Delete webhook
- `POST /api/v1/webhooks/{id}/test` — Send test ping
- `GET /api/v1/webhooks/{id}/deliveries` — List deliveries
- `GET /health` — Health check
- `GET /api/v1/health` — DB and Redis status check

## Example: Enqueue a Job

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "data_processing",
    "payload": {"action": "sum", "data": [10, 20, 30]}
  }'
```

## Webhook Signature Verification

```python
import hmac, hashlib

expected = hmac.new(secret.encode(), raw_body.encode(), hashlib.sha256).hexdigest()
is_valid = hmac.compare_digest(f"sha256={expected}", headers["X-TaskPulse-Signature"])
```

## TODO

- Dead-letter queue for jobs exceeding retry limits
- WebSocket subscriptions for live job status updates
- Workflow DAGs for multi-step task chaining
