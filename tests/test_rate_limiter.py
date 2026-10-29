from fastapi import APIRouter, Depends, status
from fastapi.testclient import TestClient

from app.api.deps import rate_limiter
from app.config import settings
from app.core.rate_limit import RateLimiter
from app.main import app


def test_rate_limiter_headers(client, auth_headers):
    # Standard request should return rate limit headers
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


def test_rate_limiter_blocks_when_limit_exceeded(client):
    # Create custom router with strict limit of 3 requests
    custom_limiter = RateLimiter(requests_per_minute=3)
    test_router = APIRouter()

    @test_router.get("/limited-test", dependencies=[Depends(custom_limiter)])
    def limited_endpoint():
        return {"status": "ok"}

    app.include_router(test_router)

    with TestClient(app) as test_c:
        # First 3 should succeed
        for i in range(3):
            res = test_c.get("/limited-test")
            assert res.status_code == status.HTTP_200_OK

        # 4th should be blocked with 429
        res = test_c.get("/limited-test")
        assert res.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Retry-After" in res.headers
        assert "Rate limit exceeded" in res.json()["detail"]


def test_rate_limiter_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)

    custom_limiter = RateLimiter(requests_per_minute=1)
    test_router = APIRouter()

    @test_router.get("/disabled-limit-test", dependencies=[Depends(custom_limiter)])
    def no_limit_endpoint():
        return {"status": "ok"}

    app.include_router(test_router)

    with TestClient(app) as test_c:
        for _ in range(5):
            res = test_c.get("/disabled-limit-test")
            assert res.status_code == status.HTTP_200_OK
