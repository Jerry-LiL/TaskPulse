import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.celery_app import celery_app
from app.core.redis_client import set_redis_client
from app.core.security import create_access_token, hash_password
from app.database import Base
from app.main import app
from app.models.user import User

# Configure Celery to use memory broker in tests
celery_app.conf.update(
    broker_url="memory://",
    result_backend="cache+memory://",
    task_always_eager=False,
)

# In-memory SQLite engine for tests
TEST_DB_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def redis_mock():
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    set_redis_client(fake_redis)
    yield fake_redis
    fake_redis.flushall()
    set_redis_client(None)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session):
    user = User(
        email="developer@taskpulse.io",
        hashed_password=hash_password("SuperSecret123"),
        full_name="Vineet Kumar",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    token = create_access_token(subject=test_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_user2(db_session):
    user = User(
        email="other@taskpulse.io",
        hashed_password=hash_password("OtherPassword123"),
        full_name="Second Developer",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers2(test_user2):
    token = create_access_token(subject=test_user2.id)
    return {"Authorization": f"Bearer {token}"}
