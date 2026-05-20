from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.dashboard import router as dashboard_router
from llm_client import LLMClient
from memory.db import init_db
from memory.repository import MemoryRepository
from telegram_handler import TelegramHandler
from triggers import TriggerRouter
from triggers.adapters import set_router_instance
from triggers.adapters.ha_location import router as ha_router
from triggers.adapters.schedule import schedule_loop
from triggers.reactions import ask_llm, configure, digest, notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_fastapi_app() -> FastAPI:
    app = FastAPI(title="Mentor Core", docs_url=None, redoc_url=None)
    app.include_router(ha_router)
    app.include_router(dashboard_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


async def run_telegram(handler: TelegramHandler) -> None:
    app = handler.build_app()
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram polling started")
        try:
            await asyncio.Event().wait()
        finally:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()


async def run_webhook_server(fastapi_app: FastAPI) -> None:
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    logger.info("Webhook server starting on :8000")
    await server.serve()


async def main() -> None:
    init_db()

    repo = MemoryRepository()
    llm = LLMClient(repo)

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    tg_handler = TelegramHandler(token, chat_id, repo, llm)
    tg_app = tg_handler.build_app()

    trigger_router = TriggerRouter(dedupe_seconds=10.0)
    trigger_router.load_rules("/app/config/triggers.yaml")
    trigger_router.register_reaction("notify", notify)
    trigger_router.register_reaction("ask_llm", ask_llm)
    trigger_router.register_reaction("digest", digest)
    set_router_instance(trigger_router)

    async def llm_handler(prompt: str) -> str:
        return await llm.chat(prompt)

    configure(tg_app.bot, chat_id, llm_handler)

    fastapi_app = create_fastapi_app()

    async with tg_app:
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram polling started")

        tasks = [
            asyncio.create_task(run_webhook_server(fastapi_app)),
            asyncio.create_task(schedule_loop(repo)),
        ]

        try:
            await asyncio.gather(*tasks)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutting down...")
        finally:
            for t in tasks:
                t.cancel()
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
