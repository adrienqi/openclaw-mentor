from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from llm_client import LLMClient
from memory.repository import MemoryRepository
from streeteasy.service import StreetEasyService

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, chat_id: str, repo: MemoryRepository, llm: LLMClient):
        self.token = token
        self.chat_id = int(chat_id)
        self.repo = repo
        self.llm = llm
        self.app: Application | None = None

    def _authorized(self, update: Update) -> bool:
        return update.effective_chat and update.effective_chat.id == self.chat_id

    async def cmd_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        text = " ".join(context.args) if context.args else ""
        if not text:
            await update.message.reply_text("Usage: /add <type> <title>\nTypes: goal, plan, reminder, fact")
            return
        parts = text.split(maxsplit=1)
        item_type = parts[0].lower() if parts[0].lower() in ("goal", "plan", "reminder", "fact") else "fact"
        title = parts[1] if len(parts) > 1 else parts[0]
        if item_type == parts[0].lower() and len(parts) == 1:
            title = text
            item_type = "fact"
        item = self.repo.create(type=item_type, title=title, source="telegram")
        await update.message.reply_text(f"Created {item.type} #{item.id}: {item.title}")

    async def cmd_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        type_filter = context.args[0] if context.args else None
        if type_filter and type_filter.startswith("--tag="):
            items = self.repo.list_active(tag=type_filter.split("=", 1)[1])
        elif type_filter in ("goal", "plan", "reminder", "fact"):
            items = self.repo.list_active(type=type_filter)
        else:
            items = self.repo.list_active()
        if not items:
            await update.message.reply_text("No active items.")
            return
        text = "\n".join(i.summary() for i in items[:25])
        await update.message.reply_text(text)

    async def cmd_show(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /show <id>")
            return
        try:
            item = self.repo.get(int(context.args[0]))
        except ValueError:
            await update.message.reply_text("Invalid ID.")
            return
        if not item:
            await update.message.reply_text("Not found.")
            return
        lines = [
            f"#{item.id} [{item.type}] {item.title}",
            f"Status: {item.status}",
        ]
        if item.body:
            lines.append(f"Body: {item.body}")
        if item.due_at:
            lines.append(f"Due: {item.due_at.isoformat()}")
        if item.tags:
            lines.append(f"Tags: {', '.join(item.tags)}")
        await update.message.reply_text("\n".join(lines))

    async def cmd_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /done <id>")
            return
        try:
            item = self.repo.update_status(int(context.args[0]), "done")
        except ValueError:
            await update.message.reply_text("Invalid ID.")
            return
        if item:
            await update.message.reply_text(f"Marked #{item.id} as done.")
        else:
            await update.message.reply_text("Not found.")

    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /cancel <id>")
            return
        try:
            item = self.repo.update_status(int(context.args[0]), "cancelled")
        except ValueError:
            await update.message.reply_text("Invalid ID.")
            return
        if item:
            await update.message.reply_text(f"Cancelled #{item.id}.")
        else:
            await update.message.reply_text("Not found.")

    async def cmd_snooze(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /snooze <id> <new_due_iso>")
            return
        try:
            item = self.repo.snooze(int(context.args[0]), context.args[1])
        except (ValueError, Exception) as e:
            await update.message.reply_text(f"Error: {e}")
            return
        if item:
            await update.message.reply_text(f"Snoozed #{item.id} to {item.due_at}")
        else:
            await update.message.reply_text("Not found.")

    async def cmd_timezone(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        if not context.args:
            tz = self.repo.get_setting("user_timezone", "America/New_York")
            await update.message.reply_text(f"Current timezone: {tz}")
            return
        self.repo.set_setting("user_timezone", context.args[0])
        await update.message.reply_text(f"Timezone set to {context.args[0]}")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        summary = self.repo.context_summary(max_items=10)
        await update.message.reply_text(summary)

    async def cmd_streeteasy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        svc = StreetEasyService(self.repo)
        if context.args and context.args[0].lower() == "poll":
            await update.message.reply_text("Running StreetEasy poll now…")
            from triggers.reactions import send_message

            stats = await svc.poll_once(
                send_telegram=send_message,
                llm_handler=self.llm.chat,
            )
            await update.message.reply_text(f"Poll done: {stats}")
            return
        await update.message.reply_text(svc.status_text())

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        text = update.message.text or ""

        # Quick-capture prefixes
        quick = self._try_quick_capture(text)
        if quick:
            await update.message.reply_text(quick)
            return

        # Free-form -> LLM with tools
        response = await self.llm.chat(text)
        await update.message.reply_text(response)

    def _try_quick_capture(self, text: str) -> str | None:
        patterns = [
            (r"^goal:\s*(.+)", "goal"),
            (r"^remind:\s*(.+)", "reminder"),
            (r"^fact:\s*(.+)", "fact"),
            (r"^plan:\s*(.+)", "plan"),
            (r"^remember:\s*(.+)", "fact"),
        ]
        for pattern, item_type in patterns:
            m = re.match(pattern, text, re.IGNORECASE)
            if m:
                title = m.group(1).strip()
                item = self.repo.create(type=item_type, title=title, source="telegram")
                return f"Saved {item.type} #{item.id}: {item.title}"
        return None

    def build_app(self) -> Application:
        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(CommandHandler("add", self.cmd_add))
        self.app.add_handler(CommandHandler("list", self.cmd_list))
        self.app.add_handler(CommandHandler("show", self.cmd_show))
        self.app.add_handler(CommandHandler("done", self.cmd_done))
        self.app.add_handler(CommandHandler("cancel", self.cmd_cancel))
        self.app.add_handler(CommandHandler("snooze", self.cmd_snooze))
        self.app.add_handler(CommandHandler("timezone", self.cmd_timezone))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("streeteasy", self.cmd_streeteasy))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        return self.app
