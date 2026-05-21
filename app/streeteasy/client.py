from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from .queries import RENTAL_LISTING_DETAILS_QUERY, SEARCH_RENTALS_QUERY

logger = logging.getLogger(__name__)

API_URL = "https://api-v6.streeteasy.com/"

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    ),
    "Origin": "https://streeteasy.com",
    "Referer": "https://streeteasy.com/",
    "Apollographql-Client-Name": "srp-frontend-service",
    "Apollographql-Client-Version": "version  50bef71ef923e981bdcb7c781851c3bfdb12a0c1",
    "App-Version": "1.0.0",
    "Os": "web",
    "Host": "api-v6.streeteasy.com",
}


class StreetEasyClient:
    def __init__(self, timeout: float = 30.0, proxy: str | None = None):
        import os

        self._timeout = timeout
        self._proxy = proxy or os.environ.get("STREETEASY_HTTP_PROXY") or os.environ.get("HTTPS_PROXY")

    async def request(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"query": query, "variables": variables or {}}
        async with httpx.AsyncClient(timeout=self._timeout, proxy=self._proxy) as client:
            resp = await client.post(API_URL, json=payload, headers=DEFAULT_HEADERS)
            resp.raise_for_status()
            data = resp.json()
        if errors := data.get("errors"):
            messages = "; ".join(e.get("message", str(e)) for e in errors)
            raise RuntimeError(f"StreetEasy GraphQL error: {messages}")
        return data["data"]

    async def search_rentals(self, search_input: dict[str, Any]) -> dict[str, Any]:
        inp = {
            "adStrategy": "NONE",
            "userSearchToken": str(uuid.uuid4()),
            **search_input,
        }
        if "userSearchToken" not in search_input:
            inp["userSearchToken"] = str(uuid.uuid4())
        data = await self.request(SEARCH_RENTALS_QUERY, {"input": inp})
        return data["searchRentals"]

    async def get_listing_details(self, listing_id: str) -> dict[str, Any]:
        return await self.request(RENTAL_LISTING_DETAILS_QUERY, {"listingID": listing_id})

    @staticmethod
    def extract_listings(search_result: dict[str, Any]) -> list[dict[str, Any]]:
        listings: list[dict[str, Any]] = []
        for edge in search_result.get("edges") or []:
            node = edge.get("node")
            if node and node.get("id"):
                listings.append(node)
        return listings

    @staticmethod
    def listing_url(node: dict[str, Any]) -> str:
        path = node.get("urlPath") or ""
        if path.startswith("http"):
            return path
        return f"https://streeteasy.com{path}"
