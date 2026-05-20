from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .db import get_db
from .models import MemoryItem


class MemoryRepository:
    def __init__(self):
        self._db: sqlite3.Connection | None = None

    @property
    def db(self) -> sqlite3.Connection:
        if self._db is None:
            self._db = get_db()
        return self._db

    def create(
        self,
        type: str,
        title: str,
        body: str = "",
        due_at: Optional[str] = None,
        timezone: Optional[str] = None,
        priority: int = 0,
        source: str = "telegram",
        tags: list[str] | None = None,
    ) -> MemoryItem:
        cur = self.db.execute(
            """INSERT INTO memory_items (type, title, body, due_at, timezone, priority, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (type, title, body, due_at, timezone, priority, source),
        )
        item_id = cur.lastrowid
        if tags:
            self._set_tags(item_id, tags)
        self.db.commit()
        return self.get(item_id)

    def get(self, item_id: int) -> Optional[MemoryItem]:
        row = self.db.execute("SELECT * FROM memory_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return None
        tags = self._get_tags(item_id)
        return MemoryItem.from_row(row, tags)

    def list_active(self, type: Optional[str] = None, tag: Optional[str] = None, limit: int = 50) -> list[MemoryItem]:
        query = "SELECT mi.* FROM memory_items mi"
        params: list = []
        conditions = ["mi.status = 'active'"]

        if tag:
            query += " JOIN memory_item_tags mt ON mt.item_id = mi.id JOIN tags t ON t.id = mt.tag_id"
            conditions.append("t.name = ?")
            params.append(tag)
        if type:
            conditions.append("mi.type = ?")
            params.append(type)

        query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY mi.priority DESC, mi.created_at DESC LIMIT ?"
        params.append(limit)

        rows = self.db.execute(query, params).fetchall()
        return [MemoryItem.from_row(r, self._get_tags(r["id"])) for r in rows]

    def update_status(self, item_id: int, status: str) -> Optional[MemoryItem]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.db.execute(
            "UPDATE memory_items SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, item_id),
        )
        self.db.commit()
        return self.get(item_id)

    def update(self, item_id: int, **fields) -> Optional[MemoryItem]:
        allowed = {"title", "body", "due_at", "timezone", "priority", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get(item_id)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        updates["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        self.db.execute(
            f"UPDATE memory_items SET {set_clause} WHERE id = ?",
            (*updates.values(), item_id),
        )
        if "tags" in fields:
            self._set_tags(item_id, fields["tags"])
        self.db.commit()
        return self.get(item_id)

    def snooze(self, item_id: int, new_due: str) -> Optional[MemoryItem]:
        return self.update(item_id, due_at=new_due, status="active")

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        self.db.commit()

    def list_items(
        self,
        type: Optional[str] = None,
        tag: Optional[str] = None,
        status: str = "active",
        limit: int = 50,
    ) -> list[MemoryItem]:
        query = "SELECT mi.* FROM memory_items mi"
        params: list = []
        conditions = ["mi.status = ?"]
        params.append(status)

        if tag:
            query += " JOIN memory_item_tags mt ON mt.item_id = mi.id JOIN tags t ON t.id = mt.tag_id"
            conditions.append("t.name = ?")
            params.append(tag)
        if type:
            conditions.append("mi.type = ?")
            params.append(type)

        query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY mi.priority DESC, mi.created_at DESC LIMIT ?"
        params.append(limit)

        rows = self.db.execute(query, params).fetchall()
        return [MemoryItem.from_row(r, self._get_tags(r["id"])) for r in rows]

    def list_upcoming_reminders(self, limit: int = 10) -> list[MemoryItem]:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = self.db.execute(
            """SELECT * FROM memory_items
               WHERE type = 'reminder' AND status = 'active' AND due_at IS NOT NULL AND due_at > ?
               ORDER BY due_at ASC LIMIT ?""",
            (now_iso, limit),
        ).fetchall()
        return [MemoryItem.from_row(r, self._get_tags(r["id"])) for r in rows]

    def count_overdue(self) -> int:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = self.db.execute(
            """SELECT COUNT(*) as cnt FROM memory_items
               WHERE type = 'reminder' AND status = 'active' AND due_at IS NOT NULL AND due_at <= ?""",
            (now_iso,),
        ).fetchone()
        return row["cnt"] if row else 0

    def counts_by_type(self) -> dict[str, int]:
        rows = self.db.execute(
            "SELECT type, COUNT(*) as cnt FROM memory_items WHERE status = 'active' GROUP BY type"
        ).fetchall()
        return {r["type"]: r["cnt"] for r in rows}

    def context_summary(self, max_items: int = 20) -> str:
        items = self.list_active(limit=max_items)
        if not items:
            return "No active memory items."
        lines = [item.summary() for item in items]
        return "Active memory:\n" + "\n".join(lines)

    def _get_tags(self, item_id: int) -> list[str]:
        rows = self.db.execute(
            "SELECT t.name FROM tags t JOIN memory_item_tags mt ON mt.tag_id = t.id WHERE mt.item_id = ?",
            (item_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def _set_tags(self, item_id: int, tags: list[str]) -> None:
        self.db.execute("DELETE FROM memory_item_tags WHERE item_id = ?", (item_id,))
        for tag_name in tags:
            self.db.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
            tag_id = self.db.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()["id"]
            self.db.execute("INSERT INTO memory_item_tags (item_id, tag_id) VALUES (?, ?)", (item_id, tag_id))
