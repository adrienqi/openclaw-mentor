from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from memory.repository import MemoryRepository

router = APIRouter(prefix="/api")

DASHBOARD_PIN = os.environ.get("DASHBOARD_PIN", "")


def verify_pin(x_dashboard_pin: str = Header("", alias="X-Dashboard-Pin")) -> None:
    if not DASHBOARD_PIN:
        raise HTTPException(status_code=503, detail="Dashboard not configured")
    if x_dashboard_pin != DASHBOARD_PIN:
        raise HTTPException(status_code=401, detail="Invalid PIN")


def get_repo() -> MemoryRepository:
    return MemoryRepository()


class MemoryCreate(BaseModel):
    type: str
    title: str
    body: str = ""
    due_at: Optional[str] = None
    tags: Optional[list[str]] = None


class MemoryPatch(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None
    due_at: Optional[str] = None
    priority: Optional[int] = None


def _item_dict(item) -> dict:
    return {
        "id": item.id,
        "type": item.type,
        "title": item.title,
        "body": item.body,
        "status": item.status,
        "priority": item.priority,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "timezone": item.timezone,
        "source": item.source,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "tags": item.tags,
    }


@router.get("/summary")
async def summary(_: None = Depends(verify_pin), repo: MemoryRepository = Depends(get_repo)):
    counts = repo.counts_by_type()
    upcoming = repo.list_upcoming_reminders(limit=5)
    overdue = repo.count_overdue()
    tz = repo.get_setting("user_timezone", os.environ.get("USER_TIMEZONE", "America/New_York"))
    return {
        "counts": counts,
        "upcoming_reminders": [_item_dict(i) for i in upcoming],
        "overdue_count": overdue,
        "timezone": tz,
    }


@router.get("/memory")
async def list_memory(
    type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    status: str = Query("active"),
    _: None = Depends(verify_pin),
    repo: MemoryRepository = Depends(get_repo),
):
    items = repo.list_items(type=type, tag=tag, status=status)
    return {"items": [_item_dict(i) for i in items]}


@router.get("/memory/{item_id}")
async def get_memory(
    item_id: int,
    _: None = Depends(verify_pin),
    repo: MemoryRepository = Depends(get_repo),
):
    item = repo.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return _item_dict(item)


@router.patch("/memory/{item_id}")
async def patch_memory(
    item_id: int,
    patch: MemoryPatch,
    _: None = Depends(verify_pin),
    repo: MemoryRepository = Depends(get_repo),
):
    existing = repo.get(item_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    fields = patch.model_dump(exclude_none=True)
    if not fields:
        return _item_dict(existing)
    updated = repo.update(item_id, **fields)
    return _item_dict(updated)


@router.post("/memory", status_code=201)
async def create_memory(
    body: MemoryCreate,
    _: None = Depends(verify_pin),
    repo: MemoryRepository = Depends(get_repo),
):
    item = repo.create(
        type=body.type,
        title=body.title,
        body=body.body,
        due_at=body.due_at,
        tags=body.tags,
        source="dashboard",
    )
    return _item_dict(item)


@router.get("/triggers/rules")
async def triggers_rules(_: None = Depends(verify_pin)):
    rules_path = Path("/app/config/triggers.yaml")
    if not rules_path.exists():
        return {"rules": []}
    import yaml
    with open(rules_path) as f:
        data = yaml.safe_load(f) or {}
    return {"rules": data.get("rules", [])}


@router.get("/status")
async def status(_: None = Depends(verify_pin), repo: MemoryRepository = Depends(get_repo)):
    last_zone = repo.get_setting("last_zone")
    last_zone_event = repo.get_setting("last_zone_event")
    last_zone_at = repo.get_setting("last_zone_at")
    return {
        "health": "ok",
        "last_zone": last_zone or None,
        "last_zone_event": last_zone_event or None,
        "last_zone_at": last_zone_at or None,
    }
