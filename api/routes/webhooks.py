import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import state
from src.naukri_agent.models.db_schema import Webhook

router = APIRouter(tags=["webhooks"])


class WebhookCreate(BaseModel):
    name: str
    url: str
    secret: str = ""
    events: str = "application.created,application.failed,run.completed"


class WebhookUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    secret: str | None = None
    events: str | None = None
    is_active: bool | None = None


def _compute_signature(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


async def fire_webhook_event(event: str, payload: dict) -> list[dict]:
    """Fire a webhook event to all active webhooks subscribed to this event type.

    Returns a list of delivery results.
    """
    session_factory = await state.db_manager.get_session_factory()
    results = []
    async with session_factory() as session:
        result = await session.execute(
            select(Webhook).where(
                Webhook.is_active == True,
                Webhook.events.contains(event),
            )
        )
        webhooks = result.scalars().all()

    for wh in webhooks:
        body = json.dumps(
            {"event": event, "payload": payload, "timestamp": datetime.now(UTC).isoformat()}
        )
        headers = {"Content-Type": "application/json"}
        if wh.secret:
            headers["X-Webhook-Signature"] = _compute_signature(body, wh.secret)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(wh.url, content=body, headers=headers)
                wh.last_triggered_at = datetime.now(UTC)
                if resp.is_error:
                    wh.failure_count = (wh.failure_count or 0) + 1
                results.append({"webhook_id": wh.id, "name": wh.name, "status": resp.status_code})
        except Exception as e:
            wh.failure_count = (wh.failure_count or 0) + 1
            results.append({"webhook_id": wh.id, "name": wh.name, "error": str(e)})

    async with session_factory() as session:
        for wh in webhooks:
            session.add(wh)
        await session.commit()

    return results


@router.get("/api/webhooks")
async def list_webhooks():
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Webhook).order_by(Webhook.created_at.desc()))
        webhooks = result.scalars().all()
        return {
            "items": [
                {
                    "id": w.id,
                    "name": w.name,
                    "url": w.url,
                    "events": w.events.split(","),
                    "is_active": w.is_active,
                    "failure_count": w.failure_count,
                    "last_triggered_at": (
                        w.last_triggered_at.isoformat() if w.last_triggered_at else None
                    ),
                    "created_at": w.created_at.isoformat() if w.created_at else "",
                }
                for w in webhooks
            ]
        }


@router.post("/api/webhooks")
async def create_webhook(body: WebhookCreate):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        webhook = Webhook(
            name=body.name,
            url=body.url,
            secret=body.secret,
            events=body.events,
        )
        session.add(webhook)
        await session.commit()
        await session.refresh(webhook)

        return {
            "status": "created",
            "webhook": {
                "id": webhook.id,
                "name": webhook.name,
                "url": webhook.url,
                "events": webhook.events.split(","),
                "is_active": webhook.is_active,
            },
        }


@router.put("/api/webhooks/{webhook_id}")
async def update_webhook(webhook_id: int, body: WebhookUpdate):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Webhook).where(Webhook.id == webhook_id))
        wh = result.scalar_one_or_none()
        if not wh:
            raise HTTPException(status_code=404, detail="Webhook not found")

        if body.name is not None:
            wh.name = body.name
        if body.url is not None:
            wh.url = body.url
        if body.secret is not None:
            wh.secret = body.secret
        if body.events is not None:
            wh.events = body.events
        if body.is_active is not None:
            wh.is_active = body.is_active

        await session.commit()

        return {
            "status": "updated",
            "webhook": {
                "id": wh.id,
                "name": wh.name,
                "url": wh.url,
                "events": wh.events.split(","),
                "is_active": wh.is_active,
            },
        }


@router.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: int):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Webhook).where(Webhook.id == webhook_id))
        wh = result.scalar_one_or_none()
        if not wh:
            raise HTTPException(status_code=404, detail="Webhook not found")

        await session.delete(wh)
        await session.commit()

        return {"status": "deleted"}


@router.post("/api/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: int):
    """Send a test payload to a webhook."""
    result = await fire_webhook_event("test", {"message": "This is a test webhook delivery"})
    target = [r for r in result if r.get("webhook_id") == webhook_id]
    if not target:
        raise HTTPException(
            status_code=404, detail="Webhook not found or not active for test event"
        )
    return {"status": "sent", "result": target[0]}
