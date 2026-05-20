from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TriggerKind(str, Enum):
    LOCATION_ENTER = "location.enter"
    LOCATION_EXIT = "location.exit"
    REMINDER_DUE = "reminder.due"
    CUSTOM = "custom"


@dataclass
class TriggerEvent:
    kind: str
    source: str
    entity: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
