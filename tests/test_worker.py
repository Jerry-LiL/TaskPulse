from unittest.mock import MagicMock, patch
import pytest

from app.models.job import Job, JobStatus
from app.worker.handlers import (
    dispatch_job_handler,
    handle_data_processing,
    handle_http_request,
    handle_notification,
    handle_sleep,
)
from app.worker.tasks import run_job_execution


def test_handler_data_processing_sum():
    res = handle_data_processing({"action": "sum", "data": [1, 2, 3, 4]})
    assert res["result"] == 10
    assert res["count"] == 4


def test_handler_data_processing_average():
    res = handle_data_processing({"action": "average", "data": [10, 20, 30]})
    assert res["result"] == 20.0

    empty_res = handle_data_processing({"action": "average", "data": []})
    assert empty_res["result"] == 0


def test_handler_data_processing_word_count():
    res = handle_data_processing({"action": "word_count", "text": "TaskPulse background worker"})
    assert res["word_count"] == 3


def test_handler_data_processing_sort():
    res = handle_data_processing({"action": "sort", "data": [4, 1, 3, 2], "reverse": True})
    assert res["result"] == [4, 3, 2, 1]


def test_handler_data_processing_invalid_action():
    with pytest.raises(ValueError, match="Unsupported data_processing action"):
        handle_data_processing({"action": "unknown"})


def test_handler_notification():
    res = handle_notification({
        "recipient": "ops@example.com",
        "channel": "slack",
        "message": "Alert payload",
    })
    assert res["status"] == "delivered"
    assert res["channel"] == "slack"
    assert res["recipient"] == "ops@example.com"


def test_handler_sleep():
    res = handle_sleep({"seconds": 0.01})
    assert res["slept_seconds"] == 0.01


def test_handler_http_request_mocked():
    with patch("httpx.Client.request") as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"ok": True}
        mock_req.return_value = mock_resp

        res = handle_http_request({
            "url": "https://example.com/api",
            "method": "POST",
            "body": {"test": 1},
        })
        assert res["status_code"] == 200
        assert res["response"] == {"ok": True}


def test_dispatch_job_handler_unknown():
    with pytest.raises(ValueError, match="Unknown job_type"):
        dispatch_job_handler("invalid_type", {})


def test_run_job_execution_success(db_session, test_user):
    job = Job(
        user_id=test_user.id,
        job_type="data_processing",
        status=JobStatus.QUEUED.value,
        payload={"action": "sum", "data": [5, 15, 25]},
    )
    db_session.add(job)
    db_session.commit()

    finished_job = run_job_execution(db_session, job.id)
    assert finished_job.status == JobStatus.SUCCEEDED.value
    assert finished_job.result["result"] == 45
    assert finished_job.started_at is not None
    assert finished_job.completed_at is not None
    assert finished_job.error is None


def test_run_job_execution_failure_with_retry(db_session, test_user):
    job = Job(
        user_id=test_user.id,
        job_type="data_processing",
        status=JobStatus.QUEUED.value,
        payload={"action": "invalid_action"},
        retries=0,
        max_retries=2,
    )
    db_session.add(job)
    db_session.commit()

    with pytest.raises(ValueError):
        run_job_execution(db_session, job.id)

    db_session.refresh(job)
    assert job.status == JobStatus.QUEUED.value
    assert job.retries == 1


def test_run_job_execution_max_retries_failed(db_session, test_user):
    job = Job(
        user_id=test_user.id,
        job_type="data_processing",
        status=JobStatus.QUEUED.value,
        payload={"action": "invalid_action"},
        retries=2,
        max_retries=2,
    )
    db_session.add(job)
    db_session.commit()

    finished = run_job_execution(db_session, job.id)
    assert finished.status == JobStatus.FAILED.value
    assert "Unsupported data_processing action" in finished.error
    assert finished.completed_at is not None


def test_run_job_execution_cancelled_skipped(db_session, test_user):
    job = Job(
        user_id=test_user.id,
        job_type="data_processing",
        status=JobStatus.CANCELLED.value,
        payload={"action": "sum", "data": [1]},
    )
    db_session.add(job)
    db_session.commit()

    finished = run_job_execution(db_session, job.id)
    assert finished.status == JobStatus.CANCELLED.value
    assert finished.result is None


def test_run_job_execution_not_found(db_session):
    with pytest.raises(ValueError, match="not found"):
        run_job_execution(db_session, "nonexistent-job-id")


def test_celery_execute_job_task(db_session, test_user):
    from app.worker.tasks import execute_job
    job = Job(
        user_id=test_user.id,
        job_type="data_processing",
        status=JobStatus.QUEUED.value,
        payload={"action": "sum", "data": [10, 20]},
    )
    db_session.add(job)
    db_session.commit()

    with patch("app.worker.tasks.SessionLocal", return_value=db_session):
        res = execute_job(job.id)
        assert res["status"] == "succeeded"
        assert res["job_id"] == job.id


def test_celery_check_scheduled_jobs_task(db_session, test_user):
    from app.worker.tasks import check_scheduled_jobs
    with patch("app.worker.tasks.SessionLocal", return_value=db_session):
        res = check_scheduled_jobs()
        assert "triggered_count" in res
