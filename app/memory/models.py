from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class MemoryItem:
    id: int
    type: str
    title: str
    body: str
    status: str
    priority: int
    due_at: Optional[datetime]
    timezone: Optional[str]
    source: str
    telegram_message_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    tags: list[str]

    @classmethod
    def from_row(cls, row, tags: list[str] | None = None) -> MemoryItem:
        def parse_dt(val: str | None) -> Optional[datetime]:
            if not val:
                return None
            return datetime.fromisoformat(val.replace("Z", "+00:00"))

        return cls(
            id=row["id"],
            type=row["type"],
            title=row["title"],
            body=row["body"] or "",
            status=row["status"],
            priority=row["priority"] or 0,
            due_at=parse_dt(row["due_at"]),
            timezone=row["timezone"],
            source=row["source"] or "telegram",
            telegram_message_id=row["telegram_message_id"],
            created_at=parse_dt(row["created_at"]) or datetime.min,
            updated_at=parse_dt(row["updated_at"]) or datetime.min,
            tags=tags or [],
        )

    def summary(self) -> str:
        parts = [f"[{self.id}] {self.type}: {self.title}"]
        if self.status != "active":
            parts.append(f"({self.status})")
        if self.due_at:
            parts.append(f"due {self.due_at.strftime('%Y-%m-%d %H:%M')}")
        if self.tags:
            parts.append(f"#{' #'.join(self.tags)}")
        return " ".join(parts)
