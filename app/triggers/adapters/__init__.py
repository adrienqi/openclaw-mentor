from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from triggers.router import TriggerRouter

_router_instance: TriggerRouter | None = None


def set_router_instance(router: TriggerRouter) -> None:
    global _router_instance
    _router_instance = router


def get_router_instance() -> TriggerRouter | None:
    return _router_instance
