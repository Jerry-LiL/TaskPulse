import hashlib
import hmac
from unittest.mock import MagicMock, patch
from fastapi import status
import httpx
import pytest

from app.models.webhook import Webhook, WebhookDelivery
from app.worker.webhook_dispatcher import (
    deliver_webhook_with_retry,
    dispatch_event_to_user_webhooks,
    generate_webhook_signature,
)


def test_create_webhook(client, auth_headers):
    response = client.post(
        "/api/v1/webhooks",
        headers=auth_headers,
        json={
            "url": "https://myapp.com/api/tasks/webhook",
            "event_types": ["job.succeeded", "job.failed"],
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["url"] == "https://myapp.com/api/tasks/webhook"
    assert data["event_types"] == ["job.succeeded", "job.failed"]
    assert "secret" in data
    assert data["is_active"] is True


def test_create_webhook_invalid_url(client, auth_headers):
    response = client.post(
        "/api/v1/webhooks",
        headers=auth_headers,
        json={
            "url": "ftp://invalid-url.com",
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_list_webhooks(client, auth_headers, db_session, test_user):
    wh = Webhook(
        user_id=test_user.id,
        url="https://example.com/wh1",
        secret="secret1",
        event_types=["*"],
    )
    db_session.add(wh)
    db_session.commit()

    res = client.get("/api/v1/webhooks", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert len(res.json()) >= 1
    assert res.json()[0]["url"] == "https://example.com/wh1"


def test_get_webhook_by_id(client, auth_headers, db_session, test_user):
    wh = Webhook(
        user_id=test_user.id,
        url="https://example.com/wh2",
        secret="secret2",
        event_types=["job.succeeded"],
    )
    db_session.add(wh)
    db_session.commit()

    res = client.get(f"/api/v1/webhooks/{wh.id}", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["id"] == wh.id


def test_get_webhook_not_found(client, auth_headers):
    res = client.get("/api/v1/webhooks/missing-id", headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_delete_webhook(client, auth_headers, db_session, test_user):
    wh = Webhook(
        user_id=test_user.id,
        url="https://example.com/wh3",
        secret="secret3",
    )
    db_session.add(wh)
    db_session.commit()

    res = client.delete(f"/api/v1/webhooks/{wh.id}", headers=auth_headers)
    assert res.status_code == status.HTTP_204_NO_CONTENT
    assert db_session.query(Webhook).filter(Webhook.id == wh.id).first() is None


def test_webhook_test_event_delivery(client, auth_headers, db_session, test_user):
    wh = Webhook(
        user_id=test_user.id,
        url="https://example.com/test-endpoint",
        secret="test-secret",
    )
    db_session.add(wh)
    db_session.commit()

    with patch("app.api.v1.webhooks.deliver_webhook_with_retry") as mock_deliver:
        mock_deliver.return_value = {
            "succeeded": True,
            "status_code": 200,
            "response_body": "OK",
            "error": None,
            "duration_ms": 12.5,
            "attempts": 1,
        }

        res = client.post(f"/api/v1/webhooks/{wh.id}/test", headers=auth_headers)
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["event"] == "ping"
        assert data["succeeded"] is True
        assert data["status_code"] == 200


def test_webhook_signature_calculation():
    secret = "my-secret-key"
    body = '{"event":"job.succeeded","timestamp":"1600000000","payload":{}}'
    expected_hex = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    sig = generate_webhook_signature(secret, body)
    assert sig == f"sha256={expected_hex}"


def test_webhook_delivery_success_first_try():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"received": true}'
    mock_client.post.return_value = mock_resp

    delays = []
    res = deliver_webhook_with_retry(
        url="https://endpoint.com",
        secret="secret",
        event="job.succeeded",
        payload={"id": "job1"},
        max_retries=3,
        client=mock_client,
        sleep_fn=delays.append,
    )

    assert res["succeeded"] is True
    assert res["status_code"] == 200
    assert res["attempts"] == 1
    assert delays == []


def test_webhook_delivery_retry_exponential_backoff():
    # Fails first 2 times with 500, succeeds on 3rd attempt with 200
    mock_client = MagicMock()
    fail_resp = MagicMock(status_code=500, text="Internal Error")
    succ_resp = MagicMock(status_code=200, text="Success")
    mock_client.post.side_effect = [fail_resp, fail_resp, succ_resp]

    delays = []
    res = deliver_webhook_with_retry(
        url="https://endpoint.com",
        secret="secret",
        event="job.succeeded",
        payload={"id": "job1"},
        max_retries=3,
        backoff_factor=2.0,
        client=mock_client,
        sleep_fn=delays.append,
    )

    assert res["succeeded"] is True
    assert res["status_code"] == 200
    assert res["attempts"] == 3
    # Delays for backoff: attempt 1 -> 2^0 = 1.0, attempt 2 -> 2^1 = 2.0
    assert delays == [1.0, 2.0]


def test_webhook_delivery_exhaust_retries_on_connection_error():
    mock_client = MagicMock()
    mock_client.post.side_effect = httpx.ConnectError("Connection refused")

    delays = []
    res = deliver_webhook_with_retry(
        url="https://endpoint.com",
        secret="secret",
        event="job.failed",
        payload={"id": "job1"},
        max_retries=3,
        backoff_factor=2.0,
        client=mock_client,
        sleep_fn=delays.append,
    )

    assert res["succeeded"] is False
    assert res["status_code"] is None
    assert "ConnectError" in res["error"]
    assert res["attempts"] == 3
    assert delays == [1.0, 2.0]


def test_list_webhook_deliveries(client, auth_headers, db_session, test_user):
    wh = Webhook(
        user_id=test_user.id,
        url="https://example.com/deliveries",
        secret="secret",
    )
    db_session.add(wh)
    db_session.commit()

    deliv = WebhookDelivery(
        webhook_id=wh.id,
        event="job.succeeded",
        payload={"status": "done"},
        status_code=200,
        attempt=1,
        succeeded=True,
    )
    db_session.add(deliv)
    db_session.commit()

    res = client.get(f"/api/v1/webhooks/{wh.id}/deliveries", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert len(res.json()) == 1
    assert res.json()[0]["event"] == "job.succeeded"
    assert res.json()[0]["succeeded"] is True


def test_dispatch_event_to_user_webhooks(db_session, test_user):
    # Active webhook listening to *
    wh = Webhook(
        user_id=test_user.id,
        url="https://example.com/dispatch",
        secret="sec",
        event_types=["*"],
        is_active=True,
    )
    db_session.add(wh)
    db_session.commit()

    mock_client = MagicMock()
    mock_client.post.return_value = MagicMock(status_code=200, text="OK")

    deliveries = dispatch_event_to_user_webhooks(
        db=db_session,
        user_id=test_user.id,
        event="job.succeeded",
        payload={"result": 42},
        client=mock_client,
        sleep_fn=lambda x: None,
    )

    assert len(deliveries) == 1
    assert deliveries[0].succeeded is True
    assert deliveries[0].status_code == 200


def test_delete_webhook_not_found(client, auth_headers):
    res = client.delete("/api/v1/webhooks/missing-wh-id", headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_delete_webhook_other_user_forbidden(client, auth_headers, db_session, test_user2):
    wh = Webhook(
        user_id=test_user2.id,
        url="https://example.com/other",
        secret="sec",
    )
    db_session.add(wh)
    db_session.commit()

    res = client.delete(f"/api/v1/webhooks/{wh.id}", headers=auth_headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_test_webhook_not_found(client, auth_headers):
    res = client.post("/api/v1/webhooks/missing-id/test", headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_test_webhook_other_user_forbidden(client, auth_headers, db_session, test_user2):
    wh = Webhook(
        user_id=test_user2.id,
        url="https://example.com/other-test",
        secret="sec",
    )
    db_session.add(wh)
    db_session.commit()

    res = client.post(f"/api/v1/webhooks/{wh.id}/test", headers=auth_headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_list_webhook_deliveries_not_found(client, auth_headers):
    res = client.get("/api/v1/webhooks/missing-id/deliveries", headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_list_webhook_deliveries_other_user_forbidden(client, auth_headers, db_session, test_user2):
    wh = Webhook(
        user_id=test_user2.id,
        url="https://example.com/delivs-other",
        secret="sec",
    )
    db_session.add(wh)
    db_session.commit()

    res = client.get(f"/api/v1/webhooks/{wh.id}/deliveries", headers=auth_headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN
