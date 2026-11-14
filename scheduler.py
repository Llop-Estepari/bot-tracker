"""Bucle de comprobación de alertas y envío de avisos."""

from __future__ import annotations

import asyncio
import html
import logging
import random
import time
from datetime import datetime, timedelta
from datetime import time as dt_time
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from filters import matches
from sources.base import BlockedError, Listing, RateLimitError, SourceError
from updates import fetch_remote_version, is_newer
from version import __version__

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
VERSION_RETRY_SECONDS = 3600
VERSION_CHECK_TIMEOUT = 30
VERSION_LOOP_SECONDS = 60
CHECK_TIMEOUT_SECONDS = 180
LAST_VERSION_CHECK_KEY = "last_version_check"


def next_midnight(now: datetime) -> datetime:
    """Próxima medianoche local a partir de ``now``."""
    local = now.astimezone()
    tomorrow = local.date() + timedelta(days=1)
    return datetime.combine(tomorrow, dt_time.min, tzinfo=local.tzinfo)


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
        self._next_version_check: datetime | None = None
        self._last_cycle_at: float | None = None
        self._cycle_alerts = 0
        self._cycle_count = 0

    # ----------------------------- ciclo -------------------------------- #

    async def run(self) -> None:
        logger.info("Scheduler iniciado")
        version_task = asyncio.create_task(
            self._version_loop(), name="version-check"
        )
        try:
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
                    self._next_run[alert.id] = now + self._jittered_interval(
                        alert
                    )
                    started = time.monotonic()
                    try:
                        await asyncio.wait_for(
                            self.check_alert(alert),
                            timeout=CHECK_TIMEOUT_SECONDS,
                        )
                    except TimeoutError:
                        logger.warning(
                            "Alerta #%s tardó más de %ss; se omite en este"
                            " ciclo",
                            alert.id,
                            CHECK_TIMEOUT_SECONDS,
                        )
                        await self._mark_failed_check(
                            alert.id, f"timeout {CHECK_TIMEOUT_SECONDS}s"
                        )
                    except Exception:  # pragma: no cover - protección
                        logger.exception(
                            "Error comprobando la alerta #%s", alert.id
                        )
                        await self._mark_failed_check(
                            alert.id, "error interno"
                        )
                    else:
                        elapsed = time.monotonic() - started
                        if elapsed > 10:
                            logger.info(
                                "Alerta #%s comprobada en %.1fs",
                                alert.id,
                                elapsed,
                            )
                    await asyncio.sleep(SECONDS_BETWEEN_ALERTS)

                self._last_cycle_at = time.time()
                self._cycle_alerts = len(alerts)
                self._cycle_count += 1

                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=IDLE_SECONDS
                    )
                except TimeoutError:
                    pass
        finally:
            version_task.cancel()
            try:
                await version_task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler detenido")

    async def _mark_failed_check(self, alert_id: int, error: str) -> None:
        try:
            await self._db.mark_checked(alert_id, ok=False, error=error)
        except Exception:  # pragma: no cover - la BD no debe cortar el bucle
            logger.exception(
                "No se pudo guardar el estado de la alerta #%s", alert_id
            )

    async def _version_loop(self) -> None:
        """Comprueba versiones sin bloquear el bucle de alertas."""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._maybe_check_version(),
                    timeout=VERSION_CHECK_TIMEOUT,
                )
            except TimeoutError:
                logger.warning(
                    "La comprobación de versión tardó más de %ss;"
                    " se reintentará",
                    VERSION_CHECK_TIMEOUT,
                )
                self._next_version_check = (
                    datetime.now().astimezone()
                    + timedelta(seconds=VERSION_RETRY_SECONDS)
                )
            except Exception:  # pragma: no cover - protección del bucle
                logger.exception("Error comprobando actualizaciones")
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=VERSION_LOOP_SECONDS
                )
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, object]:
        now = time.monotonic()
        cooldowns = {
            platform: int(until - now) + 1
            for platform, until in self._cooldown_until.items()
            if until > now
        }
        last_cycle = None
        if self._last_cycle_at is not None:
            last_cycle = int(time.time() - self._last_cycle_at)
        return {
            "uptime_seconds": int(time.time() - self._started_at),
            "cooldowns": cooldowns,
            "last_cycle_seconds_ago": last_cycle,
            "cycle_alerts": self._cycle_alerts,
            "cycle_count": self._cycle_count,
        }

    # --------------------------- comprobación --------------------------- #

    async def _maybe_check_version(
        self, now: datetime | None = None
    ) -> bool:
        """Comprueba novedades una vez al día y avisa a los administradores."""
        moment = now or datetime.now().astimezone()

        if self._next_version_check is None:
            last = await self._db.get_state(LAST_VERSION_CHECK_KEY)
            if last == moment.date().isoformat():
                self._next_version_check = next_midnight(moment)
                return False
            self._next_version_check = moment

        if moment < self._next_version_check:
            return False

        try:
            remote = await asyncio.to_thread(fetch_remote_version)
        except (OSError, ValueError) as exc:
            logger.warning("No se pudo comprobar la versión: %s", exc)
            self._next_version_check = moment + timedelta(
                seconds=VERSION_RETRY_SECONDS
            )
            return False

        self._next_version_check = next_midnight(moment)
        await self._db.set_state(
            LAST_VERSION_CHECK_KEY, moment.date().isoformat()
        )

        if not is_newer(remote, __version__):
            return False

        text = (
            "🆕 <b>Actualización disponible</b>\n"
            f"Instalada: <code>v{__version__}</code>\n"
            f"Nueva: <code>v{remote}</code>\n\n"
            "Usa /actualizar para instalarla."
        )
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔄 Actualizar ahora", callback_data="upd:yes"
                    )
                ]
            ]
        )
        for chat_id in sorted(self._settings.effective_admin_chat_ids):
            try:
                await self._notifier.send_text(
                    chat_id, text, reply_markup=markup
                )
            except Exception:
                logger.exception(
                    "No se pudo avisar de la actualización al chat %s",
                    chat_id,
                )
        return True

    async def check_alert(self, alert: Alert) -> int:
        """Comprueba una alerta y devuelve cuántos avisos se enviaron."""
        first_pass = not alert.seeded
        seeded_any = False
        errors: list[str] = []

        sent = 0
        for platform in alert.platforms:
            source = self._sources.get(platform)
            if source is None:
                errors.append(f"{platform}: fuente desconocida")
                logger.warning(
                    "Fuente desconocida %r en la alerta #%s", platform, alert.id
                )
                continue

            remaining = self._cooldown_remaining(platform)
            if remaining > 0:
                errors.append(f"{platform}: enfriando ({int(remaining)}s)")
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
                errors.append(f"{platform}: límite de peticiones")
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
                errors.append(f"{platform}: bloqueado")
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
                errors.append(f"{platform}: {exc}")
                logger.warning("Alerta #%s (%s): %s", alert.id, platform, exc)
                continue

            seeded_any = True
            candidates = [
                listing for listing in listings if matches(listing, alert)
            ]
            if not candidates:
                continue

            seen_prices = await self._db.get_seen_prices(
                alert.id, platform, [item.item_id for item in candidates]
            )

            new_items: list[Listing] = []
            price_changes: list[tuple[Listing, float]] = []
            silent_updates: dict[str, float | None] = {}

            for listing in candidates:
                if listing.item_id not in seen_prices:
                    new_items.append(listing)
                    continue
                old_price = seen_prices[listing.item_id]
                if old_price is None:
                    # Registro anterior a los avisos de precio: se rellena en
                    # silencio para no avisar de un cambio ficticio.
                    silent_updates[listing.item_id] = listing.price
                elif (
                    (not first_pass or alert.notify_existing)
                    and listing.price is not None
                    and abs(listing.price - old_price) > 0.001
                ):
                    price_changes.append((listing, old_price))
                elif listing.price != old_price:
                    silent_updates[listing.item_id] = listing.price

            if first_pass and not alert.notify_existing:
                await self._db.update_seen_prices(
                    alert.id, platform, silent_updates
                )
                if new_items:
                    await self._db.mark_seen_many(
                        alert.id,
                        platform,
                        [item.item_id for item in new_items],
                        {item.item_id: item.price for item in new_items},
                    )
                    logger.info(
                        "Alerta #%s (%s): %d anuncios iniciales registrados"
                        " sin avisar",
                        alert.id,
                        platform,
                        len(new_items),
                    )
                continue

            await self._db.update_seen_prices(
                alert.id, platform, silent_updates
            )

            budget = self._settings.max_notifications_per_check
            overflow_changes: list[tuple[Listing, float]] = []
            for index, (listing, old_price) in enumerate(price_changes):
                if budget <= 0:
                    overflow_changes = price_changes[index:]
                    break
                listing = await self._enrich(source, listing)
                try:
                    await self._notifier.send_price_change(
                        alert, listing, old_price
                    )
                except Exception:
                    logger.exception(
                        "No se pudo avisar del cambio de precio del"
                        " anuncio %s (%s)",
                        listing.item_id,
                        platform,
                    )
                    continue
                await self._db.update_seen_prices(
                    alert.id, platform, {listing.item_id: listing.price}
                )
                sent += 1
                budget -= 1
                await asyncio.sleep(SECONDS_BETWEEN_MESSAGES)

            if overflow_changes:
                await self._db.update_seen_prices(
                    alert.id,
                    platform,
                    {
                        listing.item_id: listing.price
                        for listing, _ in overflow_changes
                    },
                )
                await self._notifier.send_text(
                    alert.chat_id,
                    f"🔔 <b>{html.escape(alert.name)}</b>:"
                    f" {len(overflow_changes)} cambios de precio más."
                    f" Escribe /probar {alert.id} para verlos.",
                )

            to_send = new_items[:budget]
            for listing in to_send:
                listing = await self._enrich(source, listing)
                try:
                    await self._notifier.send_listing(alert, listing)
                except Exception:
                    logger.exception(
                        "No se pudo avisar del anuncio %s (%s)",
                        listing.item_id,
                        platform,
                    )
                    continue
                await self._db.mark_seen(
                    alert.id, platform, listing.item_id, listing.price
                )
                sent += 1
                await asyncio.sleep(SECONDS_BETWEEN_MESSAGES)

            overflow = new_items[len(to_send) :]
            if overflow:
                await self._notifier.send_text(
                    alert.chat_id,
                    f"🔔 <b>{html.escape(alert.name)}</b>: {len(overflow)}"
                    f" anuncios más desde la última comprobación."
                    f" Escribe /probar {alert.id} para verlos.",
                )
                await self._db.mark_seen_many(
                    alert.id,
                    platform,
                    [item.item_id for item in overflow],
                    {item.item_id: item.price for item in overflow},
                )

        if first_pass and seeded_any:
            await self._db.update_alert(alert.id, seeded=True)
        await self._db.mark_checked(
            alert.id,
            ok=not errors,
            error="; ".join(errors) if errors else None,
        )
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

    async def _enrich(self, source: Source, listing: Listing) -> Listing:
        """Completa datos del vendedor; un fallo nunca bloquea el aviso."""
        enrich = getattr(source, "enrich", None)
        if enrich is None:
            return listing
        try:
            return await enrich(listing)
        except Exception:  # noqa: BLE001 - fail-open deliberado
            logger.warning(
                "No se pudo completar el vendedor del anuncio %s (%s)",
                listing.item_id,
                listing.source,
            )
            return listing

    def _jittered_interval(self, alert: Alert) -> float:
        return alert.interval_seconds + random.uniform(
            0.0, min(15.0, alert.interval_seconds * 0.2)
        )

    def _cooldown_remaining(self, platform: str) -> float:
        until = self._cooldown_until.get(platform, 0.0)
        return until - time.monotonic()
