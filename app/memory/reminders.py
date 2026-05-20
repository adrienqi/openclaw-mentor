from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .db import get_db
from .models import MemoryItem


def get_due_reminders(user_tz: str = "America/New_York") -> list[MemoryItem]:
    """Return active reminders whose due_at is in the past (wall-clock aware)."""
    db = get_db()
    now_utc = datetime.now(timezone.utc)

    rows = db.execute(
        """SELECT * FROM memory_items
           WHERE type = 'reminder' AND status = 'active' AND due_at IS NOT NULL
           ORDER BY due_at ASC"""
    ).fetchall()

    due = []
    for row in rows:
        due_str = row["due_at"]
        item_tz = row["timezone"] or user_tz
        try:
            dt = datetime.fromisoformat(due_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo(item_tz))
            if dt <= now_utc:
                tags = _get_tags(db, row["id"])
                due.append(MemoryItem.from_row(row, tags))
        except (ValueError, KeyError):
            continue
    return due


def mark_fired(item_id: int) -> None:
    """Mark a reminder as done after it fires."""
    db = get_db()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "UPDATE memory_items SET status = 'done', updated_at = ? WHERE id = ?",
        (now, item_id),
    )
    db.commit()


def _get_tags(db, item_id: int) -> list[str]:
    rows = db.execute(
        "SELECT t.name FROM tags t JOIN memory_item_tags mt ON mt.tag_id = t.id WHERE mt.item_id = ?",
        (item_id,),
    ).fetchall()
    return [r["name"] for r in rows]
