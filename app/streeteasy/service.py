from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from listings.repository import ListingRepository
from memory.repository import MemoryRepository
from triggers.events import TriggerEvent

from .client import StreetEasyClient
from .config import StreetEasySettings, load_streeteasy_config
from .matcher import listing_matches
from .outreach import handle_outreach

logger = logging.getLogger(__name__)


class StreetEasyService:
    def __init__(
        self,
        memory_repo: MemoryRepository,
        listing_repo: ListingRepository | None = None,
        client: StreetEasyClient | None = None,
    ):
        self.memory_repo = memory_repo
        self.listing_repo = listing_repo or ListingRepository()
        self.client = client or StreetEasyClient()
        self.settings = load_streeteasy_config()
        self._last_poll_stats: dict[str, Any] = {}

    def reload_config(self) -> None:
        self.settings = load_streeteasy_config()

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    async def poll_once(
        self,
        send_telegram: Callable[[str], Awaitable[None]],
        llm_handler: Callable[[str], Awaitable[str]] | None = None,
        trigger_router: Any = None,
    ) -> dict[str, Any]:
        self.reload_config()
        if not self.settings.enabled:
            return {"skipped": True, "reason": "disabled"}

        stats = {"scanned": 0, "matched": 0, "new": 0, "notified": 0, "errors": 0}
        try:
            search_input = self.settings.build_search_input()
            result = await self.client.search_rentals(search_input)
            edges = result.get("edges") or []
            stats["scanned"] = len(edges)

            for edge in edges:
                node = edge.get("node")
                if not node:
                    continue
                if not listing_matches(node, self.settings, edge):
                    continue
                stats["matched"] += 1

                listing_id = str(node["id"])
                url = self.client.listing_url(node)
                _record, is_new = self.listing_repo.upsert_seen(listing_id, node, url)
                if not is_new:
                    continue

                stats["new"] += 1
                details = None
                if self.settings.outreach_mode in ("email", "draft"):
                    try:
                        details = await self.client.get_listing_details(listing_id)
                    except Exception:
                        logger.debug("Could not fetch details for %s", listing_id)

                status, telegram_text = await handle_outreach(
                    self.settings,
                    node,
                    url,
                    listing_id,
                    llm_handler=llm_handler,
                    details=details,
                )

                plan = self.memory_repo.create(
                    type="plan",
                    title=f"StreetEasy: {node.get('street', listing_id)}",
                    body=f"{url}\n\nOutreach status: {status}",
                    source="streeteasy",
                    tags=["apartment", "streeteasy"],
                )
                self.listing_repo.mark_outreach(listing_id, status, plan.id)

                await send_telegram(telegram_text)
                stats["notified"] += 1

                if trigger_router:
                    event = TriggerEvent(
                        kind="listing.new",
                        source="streeteasy",
                        entity=listing_id,
                        payload={
                            "title": node.get("street", ""),
                            "url": url,
                            "price": node.get("price"),
                            "status": status,
                        },
                    )
                    await trigger_router.handle(event)

        except Exception:
            logger.exception("StreetEasy poll failed")
            stats["errors"] += 1

        self._last_poll_stats = stats
        logger.info("StreetEasy poll: %s", stats)
        return stats

    def status_text(self) -> str:
        counts = self.listing_repo.count_by_status()
        lines = [
            f"StreetEasy monitor: {'ON' if self.settings.enabled else 'OFF'}",
            f"Poll every {self.settings.poll_interval_minutes} min · mode: {self.settings.outreach_mode}",
            f"Areas: {', '.join(str(a) for a in self.settings.search.areas)}",
            f"Price: {self.settings.search.price_min}-{self.settings.search.price_max}",
            f"Last poll: {self._last_poll_stats}",
            f"Listings tracked: {sum(counts.values())} {counts}",
        ]
        return "\n".join(lines)
