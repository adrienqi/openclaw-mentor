from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .areas import resolve_area_codes

CONFIG_PATH = Path("/app/config/streeteasy.yaml")


@dataclass
class SearchConfig:
    areas: list[str | int]
    price_min: int | None = None
    price_max: int | None = None
    bedrooms_min: int | None = None
    bedrooms_max: int | None = None
    bathrooms_min: float | None = None
    no_fee_only: bool = False
    pets_allowed: bool | None = None
    amenities: list[str] = field(default_factory=list)
    optional_amenities: list[str] = field(default_factory=list)
    per_page: int = 50
    page: int = 1
    sort_attribute: str = "RECOMMENDED"
    sort_direction: str = "DESCENDING"


@dataclass
class MatchConfig:
    move_in_by: str | None = None
    exclude_furnished: bool = False
    require_amenities_match: bool = False


@dataclass
class OutreachConfig:
    applicant_name: str = ""
    applicant_email: str = ""
    applicant_phone: str = ""
    move_in_dates: list[str] = field(default_factory=lambda: ["2026-08-01", "2026-08-15"])
    income_note: str = ""
    custom_intro: str = ""
    tour_request: bool = True


@dataclass
class StreetEasySettings:
    enabled: bool = False
    poll_interval_minutes: int = 15
    outreach_mode: str = "draft"  # notify | draft | email
    search: SearchConfig = field(default_factory=lambda: SearchConfig(areas=["WILLIAMSBURG"]))
    match: MatchConfig = field(default_factory=MatchConfig)
    outreach: OutreachConfig = field(default_factory=OutreachConfig)

    def build_search_input(self) -> dict[str, Any]:
        filters: dict[str, Any] = {"areas": resolve_area_codes(self.search.areas)}
        if self.search.price_min is not None or self.search.price_max is not None:
            filters["price"] = {
                "lowerBound": self.search.price_min,
                "upperBound": self.search.price_max,
            }
        if self.search.bedrooms_min is not None or self.search.bedrooms_max is not None:
            filters["bedrooms"] = {
                "lowerBound": self.search.bedrooms_min,
                "upperBound": self.search.bedrooms_max,
            }
        if self.search.bathrooms_min is not None:
            filters["bathrooms"] = {"lowerBound": self.search.bathrooms_min, "upperBound": None}
        # no_fee_only is applied in matcher.post-filter (API filter support varies)
        if self.search.pets_allowed is not None:
            filters["petsAllowed"] = self.search.pets_allowed
        if self.search.amenities:
            filters["amenities"] = self.search.amenities
        if self.search.optional_amenities:
            filters["optionalAmenities"] = self.search.optional_amenities

        return {
            "filters": filters,
            "sorting": {
                "attribute": self.search.sort_attribute,
                "direction": self.search.sort_direction,
            },
            "perPage": self.search.per_page,
            "page": self.search.page,
            "adStrategy": "NONE",
        }


def load_streeteasy_config(path: Path | None = None) -> StreetEasySettings:
    path = path or CONFIG_PATH
    if not path.exists():
        return StreetEasySettings(enabled=False)

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    search_raw = raw.get("search", {})
    match_raw = raw.get("match", {})
    outreach_raw = raw.get("outreach", {})

    search = SearchConfig(
        areas=search_raw.get("areas", ["WILLIAMSBURG"]),
        price_min=search_raw.get("price_min"),
        price_max=search_raw.get("price_max"),
        bedrooms_min=search_raw.get("bedrooms_min"),
        bedrooms_max=search_raw.get("bedrooms_max"),
        bathrooms_min=search_raw.get("bathrooms_min"),
        no_fee_only=bool(search_raw.get("no_fee_only", False)),
        pets_allowed=search_raw.get("pets_allowed"),
        amenities=list(search_raw.get("amenities") or []),
        optional_amenities=list(search_raw.get("optional_amenities") or []),
        per_page=int(search_raw.get("per_page", 50)),
        page=int(search_raw.get("page", 1)),
        sort_attribute=str(search_raw.get("sort_attribute", "RECOMMENDED")),
        sort_direction=str(search_raw.get("sort_direction", "DESCENDING")),
    )
    match = MatchConfig(
        move_in_by=match_raw.get("move_in_by"),
        exclude_furnished=bool(match_raw.get("exclude_furnished", False)),
        require_amenities_match=bool(match_raw.get("require_amenities_match", False)),
    )
    outreach = OutreachConfig(
        applicant_name=str(outreach_raw.get("applicant_name") or os.environ.get("STREETEASY_APPLICANT_NAME", "")),
        applicant_email=str(outreach_raw.get("applicant_email") or os.environ.get("STREETEASY_APPLICANT_EMAIL", "")),
        applicant_phone=str(outreach_raw.get("applicant_phone") or os.environ.get("STREETEASY_APPLICANT_PHONE", "")),
        move_in_dates=list(outreach_raw.get("move_in_dates") or ["2026-08-01", "2026-08-15"]),
        income_note=str(outreach_raw.get("income_note", "")),
        custom_intro=str(outreach_raw.get("custom_intro", "")),
        tour_request=bool(outreach_raw.get("tour_request", True)),
    )

    enabled = bool(raw.get("enabled", False))
    if os.environ.get("STREETEASY_ENABLED", "").lower() in ("1", "true", "yes"):
        enabled = True

    return StreetEasySettings(
        enabled=enabled,
        poll_interval_minutes=int(raw.get("poll_interval_minutes", 15)),
        outreach_mode=str(raw.get("outreach_mode", "draft")).lower(),
        search=search,
        match=match,
        outreach=outreach,
    )
