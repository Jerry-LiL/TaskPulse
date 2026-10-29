from fastapi import HTTPException, Request, Response, status
from app.config import settings
from app.core.redis_client import get_redis_client


class RateLimiter:
    def __init__(self, requests_per_minute: int | None = None):
        self.limit = requests_per_minute or settings.RATE_LIMIT_PER_MINUTE

    def __call__(self, request: Request, response: Response):
        if not settings.RATE_LIMIT_ENABLED:
            return

        # Determine identifier: Bearer token or client IP
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            identifier = f"token:{auth_header[7:30]}"
        else:
            client_host = request.client.host if request.client else "127.0.0.1"
            identifier = f"ip:{client_host}"

        key = f"ratelimit:{identifier}"

        try:
            client = get_redis_client()
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            current, ttl = pipe.execute()

            if current == 1 or ttl < 0:
                client.expire(key, 60)
                ttl = 60

            remaining = max(0, self.limit - current)
            response.headers["X-RateLimit-Limit"] = str(self.limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(max(ttl, 1))

            if current > self.limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later.",
                    headers={"Retry-After": str(max(ttl, 1))},
                )
        except HTTPException:
            raise
        except Exception:
            # If Redis is temporarily unreachable, allow request without failing open completely
            pass
