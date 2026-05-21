from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from memory.repository import MemoryRepository
from triggers.reactions import send_message

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.environ.get(name)
    value = default
    if raw is not None:
        try:
            value = int(raw.strip())
        except ValueError:
            logger.warning("Invalid integer for %s=%r; using default=%d", name, raw, default)
            value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _in_active_window(hour: int, start_hour: int, end_hour: int) -> bool:
    # Inclusive start, exclusive end. Supports overnight windows (e.g. 22 -> 6).
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def _compose_nudge(repo: MemoryRepository, max_plans: int) -> str | None:
    goals = repo.list_active(type="goal", limit=1)
    plans = repo.list_active(type="plan", limit=max_plans)

    if not goals and not plans:
        return None

    lines: list[str] = ["Focus check-in:"]
    if goals:
        lines.append(f"Goal: {goals[0].title}")
    if plans:
        lines.append("Next:")
        for idx, plan in enumerate(plans, start=1):
            lines.append(f"{idx}) {plan.title}")
    lines.append("Reply with one next action.")
    return "\n".join(lines)


async def focus_nudge_loop(repo: MemoryRepository) -> None:
    enabled = _env_bool("FOCUS_NUDGE_ENABLED", False)
    interval_minutes = _env_int("FOCUS_NUDGE_INTERVAL_MINUTES", 120, minimum=10, maximum=24 * 60)
    start_hour = _env_int("FOCUS_NUDGE_START_HOUR", 8, minimum=0, maximum=23)
    end_hour = _env_int("FOCUS_NUDGE_END_HOUR", 22, minimum=0, maximum=23)
    max_plans = _env_int("FOCUS_NUDGE_MAX_PLANS", 2, minimum=1, maximum=5)

    logger.info(
        "Focus nudge adapter %s (interval=%dm window=%02d-%02d max_plans=%d)",
        "enabled" if enabled else "disabled",
        interval_minutes,
        start_hour,
        end_hour,
        max_plans,
    )

    if not enabled:
        return

    while True:
        try:
            tz_name = repo.get_setting("user_timezone", os.environ.get("USER_TIMEZONE", "America/New_York"))
            now_local = datetime.now(ZoneInfo(tz_name))
            if _in_active_window(now_local.hour, start_hour, end_hour):
                message = _compose_nudge(repo, max_plans=max_plans)
                if message:
                    await send_message(message)
        except Exception:
            logger.exception("Focus nudge loop error")

        await asyncio.sleep(interval_minutes * 60)
