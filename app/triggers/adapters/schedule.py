from __future__ import annotations

import asyncio
import logging

from memory.reminders import get_due_reminders, mark_fired
from memory.repository import MemoryRepository
from triggers.events import TriggerEvent, TriggerKind

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60


async def schedule_loop(repo: MemoryRepository) -> None:
    """Continuously poll for due reminders and emit trigger events."""
    from triggers.adapters import get_router_instance

    logger.info("Schedule adapter started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            user_tz = repo.get_setting("user_timezone", "America/New_York")
            due_items = get_due_reminders(user_tz)

            router = get_router_instance()
            if router and due_items:
                for item in due_items:
                    event = TriggerEvent(
                        kind=TriggerKind.REMINDER_DUE.value,
                        source="schedule",
                        entity=str(item.id),
                        payload={"title": item.title, "body": item.body, "id": item.id},
                    )
                    await router.handle(event)
                    mark_fired(item.id)
                    logger.info("Fired reminder #%d: %s", item.id, item.title)

        except Exception:
            logger.exception("Schedule adapter error")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
