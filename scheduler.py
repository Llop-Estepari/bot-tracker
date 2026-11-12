"""Bucle de comprobación de alertas y envío de avisos."""

from __future__ import annotations

import asyncio
import html
import logging
import random
import time
from typing import TYPE_CHECKING

from filters import matches
from sources.base import BlockedError, Listing, RateLimitError, SourceError

if TYPE_CHECKING:
    from config import Settings
    from db import Alert, Database
    from notifier import Notifier
    from sources.base import Source

logger = logging.getLogger(__name__)

SECONDS_BETWEEN_ALERTS = 3.0
IDLE_SECONDS = 5.0
SECONDS_BETWEEN_MESSAGES = 0.8
RATE_LIMIT_COOLDOWN = 180
BLOCKED_COOLDOWN = 900


class Tracker:
    """Comprueba las alertas activas de forma periódica."""

    def __init__(
        self,
        settings: Settings,
        db: Database,
        sources: dict[str, Source],
        notifier: Notifier,
    ) -> None:
        self._settings = settings
        self._db = db
        self._sources = sources
        self._notifier = notifier
        self._next_run: dict[int, float] = {}
        self._cooldown_until: dict[str, float] = {}
        self._stop = asyncio.Event()
        self._started_at = time.time()

    # ----------------------------- ciclo -------------------------------- #

    async def run(self) -> None:
        logger.info("Scheduler iniciado")
        while not self._stop.is_set():
            try:
                alerts = await self._db.list_alerts(active_only=True)
            except Exception:  # pragma: no cover - protección del bucle
                logger.exception("No se pudieron cargar las alertas")
                alerts = []

            now = time.monotonic()
            for alert in alerts:
                if self._stop.is_set():
                    break
                if now < self._next_run.get(alert.id, 0.0):
                    continue
                self._next_run[alert.id] = now + self._jittered_interval(alert)
                try:
                    await self.check_alert(alert)
                except Exception:  # pragma: no cover - protección del bucle
                    logger.exception("Error comprobando la alerta #%s", alert.id)
                await asyncio.sleep(SECONDS_BETWEEN_ALERTS)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=IDLE_SECONDS)
            except TimeoutError:
                pass
        logger.info("Scheduler detenido")

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, object]:
        now = time.monotonic()
        cooldowns = {
            platform: int(until - now) + 1
            for platform, until in self._cooldown_until.items()
            if until > now
        }
        return {
            "uptime_seconds": int(time.time() - self._started_at),
            "cooldowns": cooldowns,
        }

    # --------------------------- comprobación --------------------------- #

    async def check_alert(self, alert: Alert) -> int:
        """Comprueba una alerta y devuelve cuántos avisos se enviaron."""
        first_pass = not alert.seeded
        seeded_any = False

        sent = 0
        for platform in alert.platforms:
            source = self._sources.get(platform)
            if source is None:
                logger.warning(
                    "Fuente desconocida %r en la alerta #%s", platform, alert.id
                )
                continue

            remaining = self._cooldown_remaining(platform)
            if remaining > 0:
                logger.info(
                    "Alerta #%s: salto %s por enfriamiento (%ss)",
                    alert.id,
                    platform,
                    int(remaining),
                )
                continue

            try:
                listings = await source.search(alert)
            except RateLimitError as exc:
                self._cooldown_until[platform] = (
                    time.monotonic() + RATE_LIMIT_COOLDOWN
                )
                logger.warning(
                    "Alerta #%s: %s. Enfriando %s durante %ss",
                    alert.id,
                    exc,
                    platform,
                    RATE_LIMIT_COOLDOWN,
                )
                continue
            except BlockedError as exc:
                self._cooldown_until[platform] = (
                    time.monotonic() + BLOCKED_COOLDOWN
                )
                logger.error(
                    "Alerta #%s: %s. Enfriando %s durante %ss",
                    alert.id,
                    exc,
                    platform,
                    BLOCKED_COOLDOWN,
                )
                continue
            except SourceError as exc:
                logger.warning("Alerta #%s (%s): %s", alert.id, platform, exc)
                continue

            seeded_any = True
            candidates = [
                listing for listing in listings if matches(listing, alert)
            ]
            unseen: list[Listing] = []
            for listing in candidates:
                if not await self._db.is_seen(
                    alert.id, platform, listing.item_id
                ):
                    unseen.append(listing)

            if not unseen:
                continue

            if first_pass and not alert.notify_existing:
                await self._db.mark_seen_many(
                    alert.id, platform, [item.item_id for item in unseen]
                )
                logger.info(
                    "Alerta #%s (%s): %d anuncios iniciales registrados sin avisar",
                    alert.id,
                    platform,
                    len(unseen),
                )
                continue

            limit = self._settings.max_notifications_per_check
            to_send = unseen[:limit]
            for listing in to_send:
                try:
                    await self._notifier.send_listing(alert, listing)
                except Exception:
                    logger.exception(
                        "No se pudo avisar del anuncio %s (%s)",
                        listing.item_id,
                        platform,
                    )
                    continue
                await self._db.mark_seen(alert.id, platform, listing.item_id)
                sent += 1
                await asyncio.sleep(SECONDS_BETWEEN_MESSAGES)

            overflow = unseen[limit:]
            if overflow:
                await self._notifier.send_text(
                    alert.chat_id,
                    f"🔔 <b>{html.escape(alert.name)}</b>: {len(overflow)}"
                    f" anuncios más desde la última comprobación."
                    f" Escribe /probar {alert.id} para verlos.",
                )
                await self._db.mark_seen_many(
                    alert.id, platform, [item.item_id for item in overflow]
                )

        if first_pass and seeded_any:
            await self._db.update_alert(alert.id, seeded=True)
        await self._db.mark_checked(alert.id)
        return sent

    async def preview(
        self, alert: Alert, limit: int = 5
    ) -> list[tuple[str, list[Listing], str | None]]:
        """Consulta una alerta sin guardar nada (para /probar)."""
        results: list[tuple[str, list[Listing], str | None]] = []
        for platform in alert.platforms:
            source = self._sources.get(platform)
            if source is None:
                results.append((platform, [], "fuente desconocida"))
                continue
            try:
                listings = await source.search(alert)
            except SourceError as exc:
                results.append((platform, [], str(exc)))
                continue
            filtered = [item for item in listings if matches(item, alert)]
            results.append((platform, filtered[:limit], None))
        return results

    # ----------------------------- ayudas ------------------------------- #

    def _jittered_interval(self, alert: Alert) -> float:
        return alert.interval_seconds + random.uniform(
            0.0, min(15.0, alert.interval_seconds * 0.2)
        )

    def _cooldown_remaining(self, platform: str) -> float:
        until = self._cooldown_until.get(platform, 0.0)
        return until - time.monotonic()
