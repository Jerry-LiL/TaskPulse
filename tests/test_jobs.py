from fastapi import status
from app.models.job import Job, JobStatus


def test_create_job_http_request(client, auth_headers):
    response = client.post(
        "/api/v1/jobs",
        headers=auth_headers,
        json={
            "job_type": "http_request",
            "payload": {"url": "https://api.example.com/data", "method": "GET"},
            "priority": 1,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["job_type"] == "http_request"
    assert data["status"] == "queued"
    assert data["priority"] == 1
    assert data["payload"]["url"] == "https://api.example.com/data"
    assert "id" in data


def test_create_job_data_processing(client, auth_headers):
    response = client.post(
        "/api/v1/jobs",
        headers=auth_headers,
        json={
            "job_type": "data_processing",
            "payload": {"action": "sum", "data": [10, 20, 30]},
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["job_type"] == "data_processing"
    assert data["status"] == "queued"


def test_create_job_invalid_type(client, auth_headers):
    response = client.post(
        "/api/v1/jobs",
        headers=auth_headers,
        json={
            "job_type": "unsupported_type",
            "payload": {},
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_job_missing_url_for_http(client, auth_headers):
    response = client.post(
        "/api/v1/jobs",
        headers=auth_headers,
        json={
            "job_type": "http_request",
            "payload": {"method": "GET"},
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_list_jobs_empty(client, auth_headers):
    response = client.get("/api/v1/jobs", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_jobs_with_filtering_and_pagination(client, auth_headers, db_session, test_user):
    for i in range(5):
        j = Job(
            user_id=test_user.id,
            job_type="notification" if i % 2 == 0 else "data_processing",
            status=JobStatus.QUEUED.value if i < 3 else JobStatus.SUCCEEDED.value,
            payload={"i": i},
        )
        db_session.add(j)
    db_session.commit()

    # Total list
    res = client.get("/api/v1/jobs", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["total"] == 5

    # Filter by status
    res = client.get("/api/v1/jobs?status=succeeded", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["total"] == 2

    # Filter by job_type
    res = client.get("/api/v1/jobs?job_type=notification", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["total"] == 3

    # Pagination
    res = client.get("/api/v1/jobs?limit=2&offset=0", headers=auth_headers)
    assert len(res.json()["items"]) == 2


def test_get_job_by_id(client, auth_headers, db_session, test_user):
    job = Job(
        user_id=test_user.id,
        job_type="sleep",
        status=JobStatus.QUEUED.value,
        payload={"seconds": 1},
    )
    db_session.add(job)
    db_session.commit()

    res = client.get(f"/api/v1/jobs/{job.id}", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["id"] == job.id
    assert res.json()["job_type"] == "sleep"


def test_get_job_not_found(client, auth_headers):
    res = client.get("/api/v1/jobs/nonexistent-id", headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_get_job_other_user_forbidden(client, auth_headers, auth_headers2, db_session, test_user2):
    # Job owned by user 2
    job = Job(
        user_id=test_user2.id,
        job_type="sleep",
        status=JobStatus.QUEUED.value,
        payload={"seconds": 1},
    )
    db_session.add(job)
    db_session.commit()

    # User 1 tries to access it
    res = client.get(f"/api/v1/jobs/{job.id}", headers=auth_headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_cancel_queued_job(client, auth_headers, db_session, test_user):
    job = Job(
        user_id=test_user.id,
        job_type="sleep",
        status=JobStatus.QUEUED.value,
        payload={"seconds": 5},
    )
    db_session.add(job)
    db_session.commit()

    res = client.post(f"/api/v1/jobs/{job.id}/cancel", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "cancelled"
    assert res.json()["completed_at"] is not None


def test_cancel_already_finished_job(client, auth_headers, db_session, test_user):
    job = Job(
        user_id=test_user.id,
        job_type="sleep",
        status=JobStatus.SUCCEEDED.value,
        payload={"seconds": 1},
    )
    db_session.add(job)
    db_session.commit()

    res = client.post(f"/api/v1/jobs/{job.id}/cancel", headers=auth_headers)
    assert res.status_code == status.HTTP_400_BAD_REQUEST


def test_cancel_job_not_found(client, auth_headers):
    res = client.post("/api/v1/jobs/missing-job-id/cancel", headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_cancel_other_user_job_forbidden(client, auth_headers, db_session, test_user2):
    job = Job(
        user_id=test_user2.id,
        job_type="sleep",
        status=JobStatus.QUEUED.value,
        payload={"seconds": 1},
    )
    db_session.add(job)
    db_session.commit()

    res = client.post(f"/api/v1/jobs/{job.id}/cancel", headers=auth_headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_retry_failed_job(client, auth_headers, db_session, test_user):
    job = Job(
        user_id=test_user.id,
        job_type="data_processing",
        status=JobStatus.FAILED.value,
        error="Calculation failed",
        payload={"action": "sum", "data": [1, 2]},
    )
    db_session.add(job)
    db_session.commit()

    res = client.post(f"/api/v1/jobs/{job.id}/retry", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "queued"
    assert data["error"] is None
    assert data["retries"] == 0


def test_retry_job_not_found(client, auth_headers):
    res = client.post("/api/v1/jobs/missing-job/retry", headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_retry_job_other_user_forbidden(client, auth_headers, db_session, test_user2):
    job = Job(
        user_id=test_user2.id,
        job_type="data_processing",
        status=JobStatus.FAILED.value,
        payload={"action": "sum"},
    )
    db_session.add(job)
    db_session.commit()

    res = client.post(f"/api/v1/jobs/{job.id}/retry", headers=auth_headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_retry_active_job_rejected(client, auth_headers, db_session, test_user):
    job = Job(
        user_id=test_user.id,
        job_type="data_processing",
        status=JobStatus.QUEUED.value,
        payload={"action": "sum", "data": [1, 2]},
    )
    db_session.add(job)
    db_session.commit()

    res = client.post(f"/api/v1/jobs/{job.id}/retry", headers=auth_headers)
    assert res.status_code == status.HTTP_400_BAD_REQUEST


def test_delete_job_success(client, auth_headers, db_session, test_user):
    job = Job(
        user_id=test_user.id,
        job_type="sleep",
        status=JobStatus.SUCCEEDED.value,
        payload={"seconds": 1},
    )
    db_session.add(job)
    db_session.commit()

    res = client.delete(f"/api/v1/jobs/{job.id}", headers=auth_headers)
    assert res.status_code == status.HTTP_204_NO_CONTENT

    # Verify deleted
    assert db_session.query(Job).filter(Job.id == job.id).first() is None


def test_delete_job_not_found(client, auth_headers):
    res = client.delete("/api/v1/jobs/unknown-id", headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_delete_job_other_user_forbidden(client, auth_headers, db_session, test_user2):
    job = Job(
        user_id=test_user2.id,
        job_type="sleep",
        status=JobStatus.SUCCEEDED.value,
        payload={"seconds": 1},
    )
    db_session.add(job)
    db_session.commit()

    res = client.delete(f"/api/v1/jobs/{job.id}", headers=auth_headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN
