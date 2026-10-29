from unittest.mock import MagicMock
from fastapi import status


def test_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["name"] == "TaskPulse"
    assert "/docs" in data["docs"]


def test_health_quick(client):
    res = client.get("/health")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"status": "ok"}


def test_health_detailed_healthy(client):
    res = client.get("/api/v1/health")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert data["redis"] == "connected"


def test_health_detailed_redis_down(client, monkeypatch):
    from app.api.v1 import health
    monkeypatch.setattr(health, "check_redis_health", lambda: False)

    res = client.get("/api/v1/health")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "degraded"
    assert data["redis"] == "unreachable"
    assert data["database"] == "connected"


def test_health_detailed_db_down(client, monkeypatch):
    mock_db = MagicMock()
    mock_db.execute.side_effect = Exception("DB connection timeout")

    from app.api.deps import get_db
    from app.main import app
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        res = client.get("/api/v1/health")
        assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = res.json()
        assert data["database"] == "unreachable"
    finally:
        app.dependency_overrides.clear()
