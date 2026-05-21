"""Neighborhood / borough name → StreetEasy area code."""

from __future__ import annotations

# Subset of codes from streeteasy-api; extend as needed.
AREAS: dict[str, int] = {
    "ALL_NYC_AND_NJ": 1,
    "MANHATTAN": 100,
    "BROOKLYN": 300,
    "QUEENS": 400,
    "BRONX": 200,
    "WILLIAMSBURG": 302,
    "GREENPOINT": 301,
    "BUSHWICK": 313,
    "BEDFORD_STUYVESANT": 310,
    "PARK_SLOPE": 319,
    "FORT_GREENE": 304,
    "DOWNTOWN_BROOKLYN": 303,
    "CROWN_HEIGHTS": 325,
    "ASTORIA": 401,
    "LONG_ISLAND_CITY": 402,
    "SUNNYSIDE": 403,
    "EAST_VILLAGE": 117,
    "LOWER_EAST_SIDE": 109,
    "CHELSEA": 115,
    "HELLS_KITCHEN": 152,
    "UPPER_WEST_SIDE": 137,
    "UPPER_EAST_SIDE": 140,
    "HARLEM": 154,
    "CENTRAL_HARLEM": 154,
    "EAST_HARLEM": 155,
}


def resolve_area_codes(names: list[str | int]) -> list[int]:
    codes: list[int] = []
    for name in names:
        if isinstance(name, int):
            codes.append(name)
            continue
        key = str(name).strip().upper().replace(" ", "_").replace("-", "_")
        if key.isdigit():
            codes.append(int(key))
            continue
        if key not in AREAS:
            raise ValueError(f"Unknown area '{name}'. Add to streeteasy/areas.py or use numeric code.")
        codes.append(AREAS[key])
    return codes
