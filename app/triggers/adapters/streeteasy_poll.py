from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from memory.repository import MemoryRepository
from streeteasy.service import StreetEasyService
from triggers.reactions import send_message

logger = logging.getLogger(__name__)


async def streeteasy_poll_loop(
    repo: MemoryRepository,
    llm_handler: Callable[[str], Awaitable[str]] | None = None,
) -> None:
    from triggers.adapters import get_router_instance

    service = StreetEasyService(repo)
    logger.info("StreetEasy poll adapter started")

    while True:
        interval = max(5, service.settings.poll_interval_minutes * 60)
        try:
            if service.enabled:
                router = get_router_instance()
                await service.poll_once(
                    send_telegram=send_message,
                    llm_handler=llm_handler,
                    trigger_router=router,
                )
        except Exception:
            logger.exception("StreetEasy poll loop error")

        service.reload_config()
        interval = max(5, service.settings.poll_interval_minutes * 60)
        await asyncio.sleep(interval)
