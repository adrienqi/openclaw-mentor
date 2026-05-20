from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import anthropic

from memory.repository import MemoryRepository

logger = logging.getLogger(__name__)

MODEL = "claude-3-haiku-20240307"
MAX_TOKENS = 1024

PERSONA_PATH = Path("/app/config/profile.json")

TOOLS = [
    {
        "name": "memory_create",
        "description": "Create a new memory item (goal, plan, reminder, or fact).",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["goal", "plan", "reminder", "fact"]},
                "title": {"type": "string"},
                "body": {"type": "string", "default": ""},
                "due_at": {"type": "string", "description": "ISO datetime for reminders, e.g. 2025-06-01T09:00:00"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["type", "title"],
        },
    },
    {
        "name": "memory_list",
        "description": "List active memory items, optionally filtered by type or tag.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["goal", "plan", "reminder", "fact"]},
                "tag": {"type": "string"},
            },
        },
    },
    {
        "name": "memory_update",
        "description": "Update an existing memory item by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "done", "cancelled"]},
                "due_at": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "memory_complete",
        "description": "Mark a memory item as done.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
]


def _load_persona() -> str:
    if PERSONA_PATH.exists():
        data = json.loads(PERSONA_PATH.read_text())
        base = data.get("persona", "")
        kb = data.get("mentor_knowledge_base", [])
        if kb:
            base += "\n\nKnowledge base:\n" + "\n".join(f"- {item}" for item in kb)
        return base
    return "You are a concise, senior mentor."


def _build_system_prompt(repo: MemoryRepository) -> str:
    persona = _load_persona()
    memory_ctx = repo.context_summary(max_items=20)
    return f"{persona}\n\n---\nCurrent state:\n{memory_ctx}"


class LLMClient:
    def __init__(self, repo: MemoryRepository):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.repo = repo

    async def chat(self, user_message: str) -> str:
        """Send user message, handle tool use loops, return final text."""
        system = _build_system_prompt(self.repo)
        messages = [{"role": "user", "content": user_message}]

        for _ in range(5):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self._execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                return "\n".join(text_parts) or "(no response)"

        return "(max tool iterations reached)"

    def _execute_tool(self, name: str, inputs: dict[str, Any]) -> str:
        try:
            if name == "memory_create":
                item = self.repo.create(
                    type=inputs["type"],
                    title=inputs["title"],
                    body=inputs.get("body", ""),
                    due_at=inputs.get("due_at"),
                    timezone=self.repo.get_setting("user_timezone"),
                    tags=inputs.get("tags"),
                )
                return f"Created {item.type} #{item.id}: {item.title}"

            elif name == "memory_list":
                items = self.repo.list_active(
                    type=inputs.get("type"), tag=inputs.get("tag")
                )
                if not items:
                    return "No active items found."
                return "\n".join(i.summary() for i in items)

            elif name == "memory_update":
                item_id = inputs.pop("id")
                item = self.repo.update(item_id, **inputs)
                if not item:
                    return f"Item #{item_id} not found."
                return f"Updated #{item.id}: {item.title} ({item.status})"

            elif name == "memory_complete":
                item = self.repo.update_status(inputs["id"], "done")
                if not item:
                    return f"Item #{inputs['id']} not found."
                return f"Marked #{item.id} as done."

            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            logger.exception("Tool execution error")
            return f"Error: {e}"
