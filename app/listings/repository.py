from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from memory.db import get_db


@dataclass
class StoredListing:
    listing_id: str
    street: str
    unit: str
    price: int | None
    url: str
    first_seen_at: str
    last_seen_at: str
    outreach_status: str
    outreach_at: str | None
    memory_item_id: int | None
    raw_json: str

    @property
    def is_new(self) -> bool:
        return self.first_seen_at == self.last_seen_at


class ListingRepository:
    def __init__(self):
        self._db: sqlite3.Connection | None = None

    @property
    def db(self) -> sqlite3.Connection:
        if self._db is None:
            self._db = get_db()
        return self._db

    def get(self, listing_id: str) -> Optional[StoredListing]:
        row = self.db.execute(
            "SELECT * FROM streeteasy_listings WHERE listing_id = ?", (listing_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def upsert_seen(self, listing_id: str, node: dict[str, Any], url: str) -> tuple[StoredListing, bool]:
        """Returns (record, is_new)."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        existing = self.get(listing_id)
        raw = json.dumps(node)
        street = node.get("street") or ""
        unit = node.get("unit") or ""
        price = node.get("price")

        if existing:
            self.db.execute(
                """UPDATE streeteasy_listings
                   SET last_seen_at = ?, street = ?, unit = ?, price = ?, url = ?, raw_json = ?
                   WHERE listing_id = ?""",
                (now, street, unit, price, url, raw, listing_id),
            )
            self.db.commit()
            updated = self.get(listing_id)
            assert updated is not None
            return updated, False

        self.db.execute(
            """INSERT INTO streeteasy_listings
               (listing_id, street, unit, price, url, first_seen_at, last_seen_at,
                outreach_status, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (listing_id, street, unit, price, url, now, now, raw),
        )
        self.db.commit()
        return self.get(listing_id), True  # type: ignore[return-value]

    def mark_outreach(self, listing_id: str, status: str, memory_item_id: int | None = None) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.db.execute(
            """UPDATE streeteasy_listings
               SET outreach_status = ?, outreach_at = ?, memory_item_id = COALESCE(?, memory_item_id)
               WHERE listing_id = ?""",
            (status, now, memory_item_id, listing_id),
        )
        self.db.commit()

    def count_by_status(self) -> dict[str, int]:
        rows = self.db.execute(
            "SELECT outreach_status, COUNT(*) AS c FROM streeteasy_listings GROUP BY outreach_status"
        ).fetchall()
        return {r["outreach_status"]: r["c"] for r in rows}

    def _from_row(self, row: sqlite3.Row) -> StoredListing:
        return StoredListing(
            listing_id=row["listing_id"],
            street=row["street"],
            unit=row["unit"],
            price=row["price"],
            url=row["url"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            outreach_status=row["outreach_status"],
            outreach_at=row["outreach_at"],
            memory_item_id=row["memory_item_id"],
            raw_json=row["raw_json"],
        )
