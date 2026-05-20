from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from .events import TriggerEvent

if TYPE_CHECKING:
    from telegram import Bot

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_chat_id: str = ""
_llm_handler: Any = None


def configure(bot: Bot, chat_id: str, llm_handler: Any = None) -> None:
    global _bot, _chat_id, _llm_handler
    _bot = bot
    _chat_id = chat_id
    _llm_handler = llm_handler


async def notify(event: TriggerEvent, params: dict[str, Any]) -> None:
    if not _bot:
        return
    template = params.get("message_template") or params.get("message", "")
    text = template.format(
        kind=event.kind,
        entity=event.entity,
        title=event.payload.get("title", ""),
        **event.payload,
    )
    await _bot.send_message(chat_id=_chat_id, text=text)
    logger.info("Sent notification: %s", text[:80])


async def ask_llm(event: TriggerEvent, params: dict[str, Any]) -> None:
    if not _bot or not _llm_handler:
        return
    prompt = params.get("prompt", f"Trigger event: {event.kind} at {event.entity}")
    response = await _llm_handler(prompt)
    await _bot.send_message(chat_id=_chat_id, text=response)


async def digest(event: TriggerEvent, params: dict[str, Any]) -> None:
    """Pull items from memory and send as digest."""
    if not _bot or not _llm_handler:
        return
    template_name = params.get("template", "today_reminders")
    prompt = f"Generate a brief {template_name} digest based on my current memory items."
    response = await _llm_handler(prompt)
    await _bot.send_message(chat_id=_chat_id, text=response)
