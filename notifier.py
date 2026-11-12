"""Envío de anuncios y mensajes a Telegram."""

from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, TelegramError

from filters import format_price
from sources.vinted import DISPLAY_NAME as VINTED_NAME
from sources.wallapop import DISPLAY_NAME as WALLAPOP_NAME

if TYPE_CHECKING:
    from db import Alert
    from sources.base import Listing

logger = logging.getLogger(__name__)

SOURCE_LABELS = {"wallapop": WALLAPOP_NAME, "vinted": VINTED_NAME}


def build_caption(listing: Listing) -> str:
    title = html.escape(listing.title)[:220]
    lines = [f"🛒 <b>{title}</b>"]
    if listing.price is not None:
        lines.append(f"💶 <b>{format_price(listing.price)}</b>")
    if listing.location:
        lines.append(f"📍 {html.escape(listing.location)}")
    if listing.seller:
        lines.append(f"👤 {html.escape(listing.seller)}")
    source = SOURCE_LABELS.get(listing.source, listing.source.title())
    link = html.escape(listing.url, quote=True)
    lines.append(f"🏪 {source} · <a href=\"{link}\">ver anuncio</a>")
    return "\n".join(lines)


class Notifier:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_listing(self, alert: Alert, listing: Listing) -> None:
        caption = build_caption(listing)
        markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔗 Abrir anuncio", url=listing.url)],
                [
                    InlineKeyboardButton(
                        "🔕 Silenciar búsqueda", callback_data=f"mute:{alert.id}"
                    )
                ],
            ]
        )

        current = listing
        for attempt in (1, 2):
            try:
                if current.photo_url:
                    await self._bot.send_photo(
                        chat_id=alert.chat_id,
                        photo=current.photo_url,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=markup,
                    )
                else:
                    await self._bot.send_message(
                        chat_id=alert.chat_id,
                        text=caption,
                        parse_mode="HTML",
                        reply_markup=markup,
                        disable_web_page_preview=False,
                    )
                return
            except RetryAfter as exc:
                wait = float(exc.retry_after) + 1
                logger.warning("Telegram pide esperar %.0f s", wait)
                await asyncio.sleep(wait)
            except TelegramError as exc:
                logger.warning(
                    "No se pudo enviar el anuncio %s (%s): %s",
                    current.item_id,
                    current.source,
                    exc,
                )
                if attempt == 1 and current.photo_url:
                    current = replace(current, photo_url=None)
                    continue
                raise

        raise TelegramError("No se pudo enviar el anuncio tras varios intentos")

    async def send_text(
        self,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except RetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 1)
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
