from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine

import yaml

from .events import TriggerEvent

logger = logging.getLogger(__name__)

ReactionFunc = Callable[[TriggerEvent, dict[str, Any]], Coroutine[Any, Any, None]]


@dataclass
class Rule:
    match_kind: str | None = None
    match_entity: str | None = None
    reaction: str = "notify"
    params: dict[str, Any] = field(default_factory=dict)


class TriggerRouter:
    def __init__(self, dedupe_seconds: float = 10.0):
        self._rules: list[Rule] = []
        self._reactions: dict[str, ReactionFunc] = {}
        self._dedupe_seconds = dedupe_seconds
        self._recent: dict[str, float] = {}

    def register_reaction(self, name: str, func: ReactionFunc) -> None:
        self._reactions[name] = func

    def load_rules(self, path: str | Path) -> None:
        path = Path(path)
        if not path.exists():
            logger.warning("triggers.yaml not found at %s, no rules loaded", path)
            return
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        self._rules = []
        for entry in data.get("rules", []):
            match = entry.get("match", {})
            rule = Rule(
                match_kind=match.get("kind"),
                match_entity=match.get("entity"),
                reaction=entry.get("reaction", "notify"),
                params={k: v for k, v in entry.items() if k not in ("match", "reaction")},
            )
            self._rules.append(rule)
        logger.info("Loaded %d trigger rules", len(self._rules))

    async def handle(self, event: TriggerEvent) -> None:
        dedupe_key = f"{event.kind}:{event.entity}"
        now = time.monotonic()
        if dedupe_key in self._recent:
            if now - self._recent[dedupe_key] < self._dedupe_seconds:
                logger.debug("Deduped event %s", dedupe_key)
                return
        self._recent[dedupe_key] = now

        matched = False
        for rule in self._rules:
            if rule.match_kind and rule.match_kind != event.kind:
                continue
            if rule.match_entity and rule.match_entity != event.entity:
                continue
            reaction_func = self._reactions.get(rule.reaction)
            if not reaction_func:
                logger.warning("No reaction registered for '%s'", rule.reaction)
                continue
            matched = True
            try:
                await reaction_func(event, rule.params)
            except Exception:
                logger.exception("Reaction '%s' failed for event %s", rule.reaction, event.kind)

        if not matched:
            logger.debug("No rules matched event kind=%s entity=%s", event.kind, event.entity)
