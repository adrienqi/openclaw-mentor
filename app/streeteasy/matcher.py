from __future__ import annotations

from datetime import date
from typing import Any

from .config import MatchConfig, StreetEasySettings


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def listing_matches(node: dict[str, Any], settings: StreetEasySettings, edge: dict[str, Any] | None = None) -> bool:
    match_cfg: MatchConfig = settings.match

    if match_cfg.exclude_furnished and node.get("furnished"):
        return False

    if settings.search.no_fee_only and not node.get("noFee"):
        return False

    if match_cfg.require_amenities_match and edge is not None:
        if edge.get("amenitiesMatch") is False:
            return False

    move_in_by = _parse_date(match_cfg.move_in_by)
    available = _parse_date(node.get("availableAt"))
    if move_in_by and available and available > move_in_by:
        return False

    if node.get("offMarketAt"):
        return False

    status = (node.get("status") or "").upper()
    if status and status not in ("ACTIVE", "OPEN", ""):
        return False

    return True


def format_listing_summary(node: dict[str, Any], url: str) -> str:
    beds = node.get("bedroomCount", "?")
    baths = node.get("fullBathroomCount", "?")
    price = node.get("price", "?")
    fee = "no fee" if node.get("noFee") else "fee"
    area = node.get("areaName", "")
    street = node.get("street", "")
    unit = node.get("unit") or ""
    avail = node.get("availableAt") or "unknown"
    unit_part = f" #{unit}" if unit else ""
    return (
        f"{street}{unit_part}, {area}\n"
        f"${price}/mo · {beds}br/{baths}ba · {fee} · avail {avail}\n"
        f"{url}"
    )
