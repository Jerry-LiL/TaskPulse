import redis
from app.config import settings

_redis_client = None


def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=3.0,
            socket_connect_timeout=3.0,
        )
    return _redis_client


def set_redis_client(client: redis.Redis | None) -> None:
    global _redis_client
    _redis_client = client


def check_redis_health() -> bool:
    try:
        client = get_redis_client()
        return bool(client.ping())
    except Exception:
        return False
