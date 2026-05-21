from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("/app/data/mentor.sqlite")
CURRENT_VERSION = 2

_conn: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def init_db() -> None:
    db = get_db()
    version = db.execute("PRAGMA user_version").fetchone()[0]

    if version < 1:
        logger.info("Applying migration v1: base schema")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS memory_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK(type IN ('goal', 'plan', 'reminder', 'fact')),
                title TEXT NOT NULL,
                body TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'done', 'cancelled', 'snoozed')),
                priority INTEGER DEFAULT 0,
                due_at TEXT,
                timezone TEXT,
                source TEXT DEFAULT 'telegram',
                telegram_message_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS memory_item_tags (
                item_id INTEGER NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (item_id, tag_id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT OR IGNORE INTO settings (key, value) VALUES ('user_timezone', 'America/New_York');

            PRAGMA user_version = 1;
        """)
        db.commit()
        version = 1

    if version < 2:
        logger.info("Applying migration v2: streeteasy_listings")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS streeteasy_listings (
                listing_id TEXT PRIMARY KEY,
                street TEXT NOT NULL DEFAULT '',
                unit TEXT NOT NULL DEFAULT '',
                price INTEGER,
                url TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                outreach_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(outreach_status IN ('pending', 'notified', 'drafted', 'emailed',
                        'email_failed', 'draft_no_email', 'skipped')),
                outreach_at TEXT,
                memory_item_id INTEGER REFERENCES memory_items(id),
                raw_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_streeteasy_outreach ON streeteasy_listings(outreach_status);
            PRAGMA user_version = 2;
        """)
        db.commit()

    logger.info("Database at version %d (current: %d)", db.execute("PRAGMA user_version").fetchone()[0], CURRENT_VERSION)
