#!/usr/bin/env python3
"""Punto de entrada del bot tracker de Wallapop y Vinted."""

from __future__ import annotations

import asyncio
import logging
import sys

from telegram.ext import Application

from bot.handlers import register_handlers
from config import Settings
from db import Database
from notifier import Notifier
from scheduler import Tracker
from sources import VintedSource, WallapopSource
from version import __version__

logger = logging.getLogger("bot_tracker")


async def post_init(app: Application) -> None:
    """Prepara base de datos, fuentes y arranca el scheduler."""
    settings: Settings = app.bot_data["settings"]

    db = Database(settings.database_path)
    await db.connect()
    purged = await db.purge_seen(settings.seen_retention_days)
    if purged:
        logger.info(
            "Eliminados %s registros antiguos de anuncios vistos", purged
        )

    sources = {
        "wallapop": WallapopSource(
            api_base=settings.wallapop_api_base,
            web_base=settings.wallapop_base_url,
            timeout=settings.request_timeout,
        ),
        "vinted": VintedSource(
            base_url=settings.vinted_base_url,
            locale=settings.vinted_locale,
            timeout=settings.request_timeout,
        ),
    }
    notifier = Notifier(app.bot)
    tracker = Tracker(settings, db, sources, notifier)

    app.bot_data.update(
        db=db,
        sources=sources,
        notifier=notifier,
        tracker=tracker,
    )
    app.bot_data["tracker_task"] = asyncio.create_task(
        tracker.run(), name="tracker"
    )

    stats = await db.stats()
    logger.info("Bot listo. Búsquedas activas: %s", stats["active_alerts"])


async def post_shutdown(app: Application) -> None:
    """Cierra el scheduler, las fuentes y la base de datos."""
    tracker = app.bot_data.get("tracker")
    if tracker is not None:
        tracker.stop()
    task = app.bot_data.get("tracker_task")
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    for source in app.bot_data.get("sources", {}).values():
        await source.close()
    db = app.bot_data.get("db")
    if db is not None:
        await db.close()
    logger.info("Bot detenido")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(f"Configuración incorrecta: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    logging.getLogger().setLevel(settings.log_level)
    # httpx registra las URLs completas, incluido el token del bot.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if not settings.allowed_chat_ids:
        logger.warning(
            "ALLOWED_CHAT_IDS está vacío: el bot rechazará a todo el mundo y"
            " mostrará el chat_id para que lo añadas al .env."
        )

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings
    register_handlers(app, settings)

    logger.info("Arrancando el bot v%s…", __version__)
    app.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
