from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request

from memory.repository import MemoryRepository
from triggers.events import TriggerEvent, TriggerKind

logger = logging.getLogger(__name__)

router = APIRouter()

WEBHOOK_SECRET = os.environ.get("HA_WEBHOOK_SECRET", "")


@router.post("/webhooks/ha/location")
async def ha_location_webhook(request: Request, authorization: str = Header("")):
    expected = f"Bearer {WEBHOOK_SECRET}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.json()
    event_type = body.get("event", "enter")
    zone = body.get("zone", "unknown")

    kind = TriggerKind.LOCATION_ENTER if event_type == "enter" else TriggerKind.LOCATION_EXIT

    trigger_event = TriggerEvent(
        kind=kind.value,
        source="ha",
        entity=zone.lower(),
        payload=body,
    )

    logger.info("HA location event: %s zone=%s", kind.value, zone)

    repo = MemoryRepository()
    repo.set_setting("last_zone", zone.lower())
    repo.set_setting("last_zone_event", event_type)
    repo.set_setting("last_zone_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    from triggers.adapters import get_router_instance
    trigger_router = get_router_instance()
    if trigger_router:
        await trigger_router.handle(trigger_event)

    return {"status": "ok"}
