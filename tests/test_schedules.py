from datetime import datetime, timedelta, timezone
from fastapi import status
from app.models.job import Job
from app.models.schedule import Schedule
from app.worker.tasks import process_due_schedules


def test_create_cron_schedule(client, auth_headers):
    response = client.post(
        "/api/v1/schedules",
        headers=auth_headers,
        json={
            "name": "Daily Report",
            "description": "Runs daily at midnight",
            "job_type": "data_processing",
            "payload": {"action": "word_count", "text": "TaskPulse rocks"},
            "cron_expression": "0 0 * * *",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "Daily Report"
    assert data["cron_expression"] == "0 0 * * *"
    assert data["next_run_at"] is not None
    assert data["is_active"] is True


def test_create_interval_schedule(client, auth_headers):
    response = client.post(
        "/api/v1/schedules",
        headers=auth_headers,
        json={
            "name": "Ping Service",
            "job_type": "http_request",
            "payload": {"url": "https://example.com/health"},
            "interval_seconds": 60,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "Ping Service"
    assert data["interval_seconds"] == 60
    assert data["next_run_at"] is not None


def test_create_schedule_invalid_cron(client, auth_headers):
    response = client.post(
        "/api/v1/schedules",
        headers=auth_headers,
        json={
            "name": "Bad Cron",
            "job_type": "sleep",
            "cron_expression": "not a valid cron expression",
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_schedule_missing_cadence(client, auth_headers):
    response = client.post(
        "/api/v1/schedules",
        headers=auth_headers,
        json={
            "name": "No Cadence",
            "job_type": "sleep",
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_schedule_both_cadences(client, auth_headers):
    response = client.post(
        "/api/v1/schedules",
        headers=auth_headers,
        json={
            "name": "Conflicting Cadence",
            "job_type": "sleep",
            "cron_expression": "*/5 * * * *",
            "interval_seconds": 60,
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_list_schedules(client, auth_headers, db_session, test_user):
    sched = Schedule(
        user_id=test_user.id,
        name="Hourly Check",
        job_type="sleep",
        cron_expression="0 * * * *",
    )
    db_session.add(sched)
    db_session.commit()

    res = client.get("/api/v1/schedules", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert len(res.json()) >= 1
    assert res.json()[0]["name"] == "Hourly Check"


def test_get_schedule_by_id(client, auth_headers, db_session, test_user):
    sched = Schedule(
        user_id=test_user.id,
        name="Fetch Schedule",
        job_type="sleep",
        interval_seconds=120,
    )
    db_session.add(sched)
    db_session.commit()

    res = client.get(f"/api/v1/schedules/{sched.id}", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["id"] == sched.id


def test_get_schedule_not_found(client, auth_headers):
    res = client.get("/api/v1/schedules/missing-id", headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_get_schedule_other_user_forbidden(client, auth_headers, db_session, test_user2):
    sched = Schedule(
        user_id=test_user2.id,
        name="Private Schedule",
        job_type="sleep",
        interval_seconds=60,
    )
    db_session.add(sched)
    db_session.commit()

    res = client.get(f"/api/v1/schedules/{sched.id}", headers=auth_headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_patch_schedule_toggle_active(client, auth_headers, db_session, test_user):
    sched = Schedule(
        user_id=test_user.id,
        name="Toggle Me",
        job_type="sleep",
        interval_seconds=60,
        is_active=True,
        next_run_at=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    db_session.add(sched)
    db_session.commit()

    # Disable schedule
    res = client.patch(
        f"/api/v1/schedules/{sched.id}",
        headers=auth_headers,
        json={"is_active": False},
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["is_active"] is False
    assert res.json()["next_run_at"] is None

    # Re-enable schedule
    res = client.patch(
        f"/api/v1/schedules/{sched.id}",
        headers=auth_headers,
        json={"is_active": True},
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["is_active"] is True
    assert res.json()["next_run_at"] is not None


def test_patch_schedule_update_cron(client, auth_headers, db_session, test_user):
    sched = Schedule(
        user_id=test_user.id,
        name="Update Cron",
        job_type="sleep",
        cron_expression="0 0 * * *",
    )
    db_session.add(sched)
    db_session.commit()

    res = client.patch(
        f"/api/v1/schedules/{sched.id}",
        headers=auth_headers,
        json={"cron_expression": "*/10 * * * *"},
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["cron_expression"] == "*/10 * * * *"


def test_delete_schedule(client, auth_headers, db_session, test_user):
    sched = Schedule(
        user_id=test_user.id,
        name="Delete Me",
        job_type="sleep",
        interval_seconds=60,
    )
    db_session.add(sched)
    db_session.commit()

    res = client.delete(f"/api/v1/schedules/{sched.id}", headers=auth_headers)
    assert res.status_code == status.HTTP_204_NO_CONTENT
    assert db_session.query(Schedule).filter(Schedule.id == sched.id).first() is None


def test_trigger_schedule_now(client, auth_headers, db_session, test_user):
    sched = Schedule(
        user_id=test_user.id,
        name="Manual Trigger",
        job_type="data_processing",
        payload={"action": "sum", "data": [1, 2]},
        interval_seconds=300,
        total_runs=0,
    )
    db_session.add(sched)
    db_session.commit()

    res = client.post(f"/api/v1/schedules/{sched.id}/trigger", headers=auth_headers)
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert data["job_type"] == "data_processing"
    assert data["schedule_id"] == sched.id

    db_session.refresh(sched)
    assert sched.total_runs == 1
    assert sched.last_run_at is not None


def test_beat_process_due_schedules(db_session, test_user):
    # Schedule due in the past
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    sched = Schedule(
        user_id=test_user.id,
        name="Overdue Schedule",
        job_type="sleep",
        payload={"seconds": 1},
        interval_seconds=60,
        is_active=True,
        next_run_at=past_time,
        total_runs=0,
    )
    db_session.add(sched)
    db_session.commit()

    job_ids = process_due_schedules(db_session)
    assert len(job_ids) == 1

    created_job = db_session.query(Job).filter(Job.id == job_ids[0]).first()
    assert created_job is not None
    assert created_job.schedule_id == sched.id

    db_session.refresh(sched)
    assert sched.total_runs == 1
    next_run = sched.next_run_at
    if next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=timezone.utc)
    assert next_run > datetime.now(timezone.utc)


def test_patch_schedule_not_found(client, auth_headers):
    res = client.patch(
        "/api/v1/schedules/nonexistent-id",
        headers=auth_headers,
        json={"name": "New Name"},
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_patch_schedule_other_user_forbidden(client, auth_headers, db_session, test_user2):
    sched = Schedule(
        user_id=test_user2.id,
        name="User2 Schedule",
        job_type="sleep",
        interval_seconds=60,
    )
    db_session.add(sched)
    db_session.commit()

    res = client.patch(
        f"/api/v1/schedules/{sched.id}",
        headers=auth_headers,
        json={"name": "Hacked Name"},
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_delete_schedule_not_found(client, auth_headers):
    res = client.delete("/api/v1/schedules/missing-id", headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_delete_schedule_other_user_forbidden(client, auth_headers, db_session, test_user2):
    sched = Schedule(
        user_id=test_user2.id,
        name="User2 Sched",
        job_type="sleep",
        interval_seconds=60,
    )
    db_session.add(sched)
    db_session.commit()

    res = client.delete(f"/api/v1/schedules/{sched.id}", headers=auth_headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_trigger_schedule_not_found(client, auth_headers):
    res = client.post("/api/v1/schedules/missing-id/trigger", headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_trigger_schedule_other_user_forbidden(client, auth_headers, db_session, test_user2):
    sched = Schedule(
        user_id=test_user2.id,
        name="User2 Sched",
        job_type="sleep",
        interval_seconds=60,
    )
    db_session.add(sched)
    db_session.commit()

    res = client.post(f"/api/v1/schedules/{sched.id}/trigger", headers=auth_headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN
