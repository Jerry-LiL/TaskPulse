import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, rate_limiter
from app.database import get_db
from app.models.user import User
from app.models.webhook import Webhook, WebhookDelivery
from app.schemas.webhook import (
    WebhookCreate,
    WebhookDeliveryResponse,
    WebhookResponse,
)
from app.worker.webhook_dispatcher import deliver_webhook_with_retry

router = APIRouter(prefix="/webhooks", tags=["webhooks"], dependencies=[Depends(rate_limiter)])


@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
def create_webhook(
    webhook_in: WebhookCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    secret = webhook_in.secret or secrets.token_hex(24)
    webhook = Webhook(
        user_id=current_user.id,
        url=webhook_in.url,
        secret=secret,
        event_types=webhook_in.event_types,
        is_active=True,
    )
    db.add(webhook)
    db.commit()
    db.refresh(webhook)
    return webhook


@router.get("", response_model=list[WebhookResponse])
def list_webhooks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Webhook)
        .filter(Webhook.user_id == current_user.id)
        .order_by(Webhook.created_at.desc())
        .all()
    )


@router.get("/{webhook_id}", response_model=WebhookResponse)
def get_webhook(
    webhook_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    if webhook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this webhook",
        )
    return webhook


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    if webhook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this webhook",
        )

    db.delete(webhook)
    db.commit()
    return None


@router.post("/{webhook_id}/test", response_model=WebhookDeliveryResponse)
def test_webhook(
    webhook_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    if webhook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this webhook",
        )

    test_payload = {"message": "Test ping event from TaskPulse", "webhook_id": webhook.id}
    res = deliver_webhook_with_retry(
        url=webhook.url,
        secret=webhook.secret,
        event="ping",
        payload=test_payload,
        max_retries=1,
    )

    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        event="ping",
        payload=test_payload,
        status_code=res["status_code"],
        response_body=res["response_body"],
        error=res["error"],
        duration_ms=res["duration_ms"],
        attempt=res["attempts"],
        succeeded=res["succeeded"],
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return delivery


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryResponse])
def list_webhook_deliveries(
    webhook_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    if webhook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this webhook",
        )

    deliveries = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(100)
        .all()
    )
    return deliveries
