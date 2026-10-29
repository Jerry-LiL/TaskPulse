from fastapi import status
from app.models.user import User


def test_register_success(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "strongpassword123",
            "full_name": "Alice Smith",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["full_name"] == "Alice Smith"
    assert data["is_active"] is True
    assert "id" in data
    assert "hashed_password" not in data


def test_register_duplicate_email(client, test_user):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": test_user.email,
            "password": "anotherpassword",
            "full_name": "Duplicate User",
        },
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already registered" in response.json()["detail"].lower()


def test_register_invalid_email(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "validpassword123",
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_register_short_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "shortpwd@example.com",
            "password": "123",
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_login_success(client, test_user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "SuperSecret123",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_login_wrong_password(client, test_user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "WrongPassword123",
        },
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "incorrect" in response.json()["detail"].lower()


def test_login_nonexistent_user(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "SomePassword123",
        },
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_login_inactive_user(client, db_session, test_user):
    test_user.is_active = False
    db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "SuperSecret123",
        },
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "inactive" in response.json()["detail"].lower()


def test_get_me_success(client, auth_headers, test_user):
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == test_user.id
    assert data["email"] == test_user.email
    assert data["full_name"] == test_user.full_name


def test_get_me_unauthorized(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_me_invalid_token(client):
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.payload"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
