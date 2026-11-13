"""Comandos y asistentes del bot de Telegram."""

from __future__ import annotations

import html
import logging
import warnings
from typing import TYPE_CHECKING, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

from db import Alert, Database, NewAlert
from filters import format_price, parse_price, parse_price_range
from notifier import Notifier
from version import __release_date__, __version__

if TYPE_CHECKING:
    from config import Settings
    from scheduler import Tracker

logger = logging.getLogger(__name__)

PLATFORM_LABELS = {"wallapop": "Wallapop", "vinted": "Vinted"}

HELP_TEXT = """🤖 <b>Tracker de Wallapop y Vinted</b>

Creo búsquedas con filtros y te aviso por aquí cada vez que aparece un anuncio nuevo.

<b>Búsquedas</b>
/nuevo — crear una búsqueda paso a paso
/lista — ver todas tus búsquedas
/ver &lt;id&gt; — detalle de una búsqueda
/probar &lt;id&gt; — ver resultados ahora sin guardar nada
/editar &lt;id&gt; &lt;campo&gt; &lt;valor&gt; — modificar una búsqueda
/avanzado &lt;id&gt; clave=valor — categorías, marcas y estado
/pausar &lt;id&gt; · /reanudar &lt;id&gt; · /borrar &lt;id&gt;

<b>Campos de /editar</b>
<code>nombre</code>, <code>palabras</code>, <code>min</code>, <code>max</code>,
<code>intervalo</code>, <code>excluir</code>, <code>plataformas</code>,
<code>envio</code>, <code>estricto</code>, <code>precios</code>

El <b>modo estricto</b> (activado por defecto) descarta anuncios cuyo título
no contenga ninguna palabra clave. Desactívalo con
<code>/editar 3 estricto off</code>.

El <b>filtro de envío</b> de Wallapop está activado por defecto: solo se
avisan anuncios con envío disponible. Desactívalo con
<code>/editar 3 envio off</code>.

Los <b>términos excluidos</b> son opcionales: <code>/editar 3 excluir -</code>
los borra.

Las <b>bajadas de precio</b> de anuncios ya vistos se avisan por defecto.
Desactívalas con <code>/editar 3 precios off</code>.

<b>Ejemplos</b>
<code>/editar 3 min 100</code>
<code>/editar 3 envio off</code>
<code>/editar 3 estricto off</code>
<code>/editar 3 plataformas ambas</code>
<code>/avanzado 3 vinted_brand=53,417</code>

Cuando recibas un aviso, el botón «Silenciar búsqueda» pausa esa alerta.

/estado — estado del bot
/ayuda — este mensaje

<i>Las plataformas no ofrecen API oficial: el bot usa sus endpoints internos con un ritmo bajo y puede dejar de funcionar si cambian.</i>"""

(
    WIZ_NAME,
    WIZ_PLATFORMS,
    WIZ_KEYWORDS,
    WIZ_PRICE,
    WIZ_EXCLUDE,
    WIZ_INTERVAL,
    WIZ_NOTIFY,
) = range(7)


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #


def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


def _tracker(context: ContextTypes.DEFAULT_TYPE) -> Tracker:
    return context.application.bot_data["tracker"]


def _settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data["settings"]


def _notifier(context: ContextTypes.DEFAULT_TYPE) -> Notifier:
    return context.application.bot_data["notifier"]


async def enforce_auth(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Bloquea cualquier interacción de chats que no estén en la whitelist."""
    settings = _settings(context)
    chat = update.effective_chat
    if chat is None:
        return
    if chat.id in settings.allowed_chat_ids:
        return

    logger.warning(
        "Acceso denegado al chat %s (@%s)",
        chat.id,
        chat.username or chat.full_name or "?",
    )
    if update.callback_query is not None:
        await update.callback_query.answer("Sin permiso", show_alert=True)
    elif update.effective_message is not None:
        await update.effective_message.reply_text(
            "⛔ No tienes acceso a este bot.\n\n"
            f"Tu chat_id es <code>{chat.id}</code>.\n"
            "Añádelo a <code>ALLOWED_CHAT_IDS</code> en el .env y reinicia el bot.",
            parse_mode="HTML",
        )
    raise ApplicationHandlerStop


def format_alert(alert: Alert) -> str:
    platforms = " + ".join(
        PLATFORM_LABELS.get(platform, platform) for platform in alert.platforms
    )
    lines = [f"<b>#{alert.id} · {html.escape(alert.name)}</b>"]
    lines.append(f"🏪 <i>{platforms}</i>")
    if alert.keywords:
        lines.append(f"🔎 <code>{html.escape(alert.keywords)}</code>")
    if alert.min_price is not None or alert.max_price is not None:
        minimum = (
            format_price(alert.min_price)
            if alert.min_price is not None
            else "sin mínimo"
        )
        maximum = (
            format_price(alert.max_price)
            if alert.max_price is not None
            else "sin máximo"
        )
        lines.append(f"💶 <b>{minimum} – {maximum}</b>")
    if "wallapop" in alert.platforms:
        shipping = (
            "📦 <i>solo con envío</i>"
            if alert.wallapop_shipping
            else "📦 <i>envío indiferente</i>"
        )
        lines.append(shipping)
    if alert.exclude_words:
        lines.append(f"🚫 <i>excluye: {html.escape(alert.exclude_words)}</i>")

    extra: list[str] = []
    if alert.wallapop_category_id:
        extra.append(f"cat. Wallapop {alert.wallapop_category_id}")
    if alert.vinted_catalog_ids:
        extra.append(
            "cat. Vinted " + ",".join(str(v) for v in alert.vinted_catalog_ids)
        )
    if alert.vinted_brand_ids:
        extra.append(
            "marcas " + ",".join(str(v) for v in alert.vinted_brand_ids)
        )
    if alert.vinted_condition_ids:
        extra.append(
            "estado " + ",".join(str(v) for v in alert.vinted_condition_ids)
        )
    if extra:
        lines.append("🎛 <i>" + " · ".join(extra) + "</i>")

    status = "🟢 <b>activa</b>" if alert.active else "⏸ <b>pausada</b>"
    strict = " · 🎯 estricto" if alert.strict_keywords else ""
    price_alerts = (
        "📉 <i>precio</i>"
        if alert.notify_price_changes
        else "📉 <i>precio off</i>"
    )
    lines.append(
        f"⏱ <i>cada {alert.interval_seconds}s</i> · {status}{strict} ·"
        f" {price_alerts}"
    )
    lines.append(
        "👁 <i>última comprobación: "
        + html.escape(alert.last_checked_at or "nunca")
        + "</i>"
    )
    return "\n".join(lines)


def split_message(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = block
    if current:
        chunks.append(current)
    return chunks


async def send_long(update: Update, text: str) -> None:
    message = update.effective_message
    if message is None:
        return
    for chunk in split_message(text):
        await message.reply_text(
            chunk, parse_mode="HTML", disable_web_page_preview=True
        )


async def fetch_owned_alert(
    update: Update, context: ContextTypes.DEFAULT_TYPE, raw_id: str
) -> Alert | None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return None
    try:
        alert_id = int(raw_id)
    except (TypeError, ValueError):
        await message.reply_text(
            "Indica un número de búsqueda válido. Mira /lista."
        )
        return None
    alert = await _db(context).get_alert(alert_id)
    if alert is None or alert.chat_id != chat.id:
        await message.reply_text(f"No encontré la búsqueda #{alert_id}.")
        return None
    return alert


def format_uptime(seconds: int) -> str:
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def parse_toggle(value: str) -> bool:
    normalized = value.lower()
    if normalized in {"on", "si", "sí", "true", "1", "activar"}:
        return True
    if normalized in {"off", "no", "false", "0", "desactivar"}:
        return False
    raise ValueError("usa on u off")


# --------------------------------------------------------------------------- #
# Comandos básicos
# --------------------------------------------------------------------------- #


async def help_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await send_long(update, f"{HELP_TEXT}\n\n<i>v{__version__}</i>")


async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    alerts = await _db(context).list_alerts(chat_id=chat.id)
    if not alerts:
        await update.effective_message.reply_text(
            "Todavía no tienes búsquedas. Crea la primera con /nuevo."
        )
        return
    body = "\n\n".join(format_alert(alert) for alert in alerts)
    await send_long(update, f"🔎 <b>Tus búsquedas ({len(alerts)})</b>\n\n{body}")


async def view_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Uso: /ver <id>")
        return
    alert = await fetch_owned_alert(update, context, context.args[0])
    if alert is not None:
        await send_long(update, format_alert(alert))


async def pause_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Uso: /pausar <id>")
        return
    alert = await fetch_owned_alert(update, context, context.args[0])
    if alert is None:
        return
    await _db(context).update_alert(alert.id, active=False)
    await update.effective_message.reply_text(
        f"⏸ Búsqueda #{alert.id} pausada. /reanudar {alert.id} para activarla."
    )


async def resume_alert(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not context.args:
        await update.effective_message.reply_text("Uso: /reanudar <id>")
        return
    alert = await fetch_owned_alert(update, context, context.args[0])
    if alert is None:
        return
    await _db(context).update_alert(alert.id, active=True)
    await update.effective_message.reply_text(
        f"▶️ Búsqueda #{alert.id} reactivada."
    )


async def delete_alert(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not context.args:
        await update.effective_message.reply_text("Uso: /borrar <id>")
        return
    alert = await fetch_owned_alert(update, context, context.args[0])
    if alert is None:
        return
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🗑 Sí, borrar", callback_data=f"del:{alert.id}:yes"
                ),
                InlineKeyboardButton(
                    "Cancelar", callback_data=f"del:{alert.id}:no"
                ),
            ]
        ]
    )
    await update.effective_message.reply_text(
        f"¿Seguro que quieres borrar la búsqueda #{alert.id} "
        f"(<b>{html.escape(alert.name)}</b>)?",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


def format_status(stats: dict[str, int], status: dict[str, object]) -> str:
    lines = [
        "🤖 <b>Estado del bot</b>",
        (
            f"🧩 <b>Versión:</b> <code>v{__version__}</code> ·"
            f" <i>{__release_date__}</i>"
        ),
        (
            f"⏳ <b>Activo:</b>"
            f" <i>{format_uptime(int(status['uptime_seconds']))}</i>"
        ),
        (
            f"🔎 <b>Búsquedas:</b> {stats['active_alerts']} activas de"
            f" {stats['alerts']}"
        ),
        f"👁 <b>Anuncios:</b> {stats['seen_items']} registrados",
    ]
    cooldowns = status.get("cooldowns") or {}
    if cooldowns:
        text = ", ".join(
            f"{PLATFORM_LABELS.get(platform, platform)} {int(seconds)}s"
            for platform, seconds in dict(cooldowns).items()
        )
        lines.append(f"🚧 <b>Enfriando:</b> <i>{text}</i>")
    return "\n".join(lines)


async def status_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    stats = await _db(context).stats()
    status = _tracker(context).status()
    await send_long(update, format_status(stats, status))


# --------------------------------------------------------------------------- #
# /probar
# --------------------------------------------------------------------------- #


async def test_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Uso: /probar <id>")
        return
    alert = await fetch_owned_alert(update, context, context.args[0])
    if alert is None:
        return

    await update.effective_message.reply_text("🔎 Consultando ahora mismo…")
    results = await _tracker(context).preview(alert)

    lines: list[str] = [f"🧪 <b>Prueba de #{alert.id}</b>"]
    for platform, listings, error in results:
        label = PLATFORM_LABELS.get(platform, platform)
        if error:
            lines.append(f"⚠️ <b>{label}</b>: {html.escape(error)}")
            continue
        if not listings:
            lines.append(f"· <b>{label}</b>: sin resultados ahora mismo")
            continue
        lines.append(f"<b>{label}</b>")
        for listing in listings:
            price = format_price(listing.price) if listing.price is not None else "?"
            lines.append(
                f"• <a href=\"{html.escape(listing.url, quote=True)}\">"
                f"{html.escape(listing.title)}</a> — <b>{price}</b>"
            )
    await send_long(update, "\n".join(lines))


# --------------------------------------------------------------------------- #
# /editar
# --------------------------------------------------------------------------- #


async def edit_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if len(args) < 3:
        await send_long(
            update,
            "Uso: <code>/editar &lt;id&gt; &lt;campo&gt; &lt;valor&gt;</code>\n\n"
            "Campos: nombre, palabras, min, max, intervalo, excluir,"
            " plataformas, estricto, precios, envio.\n"
            "Ej.: <code>/editar 3 min 100</code> · "
            "<code>/editar 3 estricto off</code>",
        )
        return

    alert = await fetch_owned_alert(update, context, args[0])
    if alert is None:
        return

    field = args[1].lower()
    value = " ".join(args[2:]).strip()
    settings = _settings(context)
    db = _db(context)

    try:
        if field == "nombre":
            await db.update_alert(alert.id, name=value[:80])
        elif field == "palabras":
            if not value:
                raise ValueError("las palabras clave no pueden estar vacías")
            await db.update_alert(alert.id, keywords=value)
        elif field in {"min", "max"}:
            price = None if value in {"-", ""} else parse_price(value)
            if field == "min":
                await db.update_alert(alert.id, min_price=price)
            else:
                await db.update_alert(alert.id, max_price=price)
        elif field == "intervalo":
            try:
                interval = int(value)
            except ValueError as exc:
                raise ValueError(
                    "el intervalo debe ser un número de segundos"
                ) from exc
            interval = max(interval, settings.min_interval)
            if interval > 3600:
                raise ValueError("el intervalo máximo es 3600 segundos")
            await db.update_alert(alert.id, interval_seconds=interval)
        elif field in {"excluir", "excluidas"}:
            exclude = "" if value in {"-", ""} else value
            await db.update_alert(alert.id, exclude_words=exclude)
        elif field in {"plataformas", "plataforma"}:
            raw = value.lower()
            if raw in {"ambas", "ambos", "both", "wallapop,vinted", "vinted,wallapop"}:
                platforms = ["wallapop", "vinted"]
            elif raw in {"wallapop", "vinted"}:
                platforms = [raw]
            else:
                raise ValueError("usa wallapop, vinted o ambas")
            await db.update_alert(alert.id, platforms=platforms)
        elif field in {"estricto", "strict"}:
            await db.update_alert(
                alert.id, strict_keywords=parse_toggle(value)
            )
        elif field in {"precios", "bajadas", "precio_bajadas"}:
            await db.update_alert(
                alert.id, notify_price_changes=parse_toggle(value)
            )
        elif field in {"envio", "envío", "shipping"}:
            await db.update_alert(
                alert.id, wallapop_shipping=parse_toggle(value)
            )
        else:
            raise ValueError(f"campo desconocido: {field}")
    except ValueError as exc:
        await update.effective_message.reply_text(f"⚠️ {exc}")
        return

    updated = await db.get_alert(alert.id)
    if updated is not None:
        await send_long(update, f"✅ Actualizada\n\n{format_alert(updated)}")


# --------------------------------------------------------------------------- #
# /avanzado
# --------------------------------------------------------------------------- #

ADVANCED_KEYS = {
    "wallapop_category": ("wallapop_category_id", "int"),
    "vinted_catalog": ("vinted_catalog_ids", "ids"),
    "vinted_brand": ("vinted_brand_ids", "ids"),
    "vinted_condition": ("vinted_condition_ids", "ids"),
}

ADVANCED_HELP = (
    "Uso: <code>/avanzado &lt;id&gt; clave=valor</code>\n\n"
    "Claves disponibles:\n"
    "· <code>wallapop_category=ID</code>\n"
    "· <code>vinted_catalog=ID</code>\n"
    "· <code>vinted_brand=ID,ID</code>\n"
    "· <code>vinted_condition=ID</code>\n\n"
    "Los IDs se leen en la URL de la web: por ejemplo, una categoría de"
    " Vinted aparece como <code>?catalog[]=1904</code>.\n"
    "Usa <code>-</code> para borrar un filtro.\n\n"
    "Ej.: <code>/avanzado 3 vinted_brand=53,417</code>"
)


async def advanced_alert(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    args = context.args or []
    if len(args) < 2 or any("=" not in pair for pair in args[1:]):
        await send_long(update, ADVANCED_HELP)
        return

    alert = await fetch_owned_alert(update, context, args[0])
    if alert is None:
        return

    updates: dict[str, Any] = {}
    try:
        for pair in args[1:]:
            key, raw_value = pair.split("=", 1)
            key = key.strip().lower()
            raw_value = raw_value.strip()
            if key not in ADVANCED_KEYS:
                raise ValueError(
                    f"clave desconocida: {key}. Válidas: "
                    + ", ".join(ADVANCED_KEYS)
                )
            column, kind = ADVANCED_KEYS[key]
            if raw_value in {"-", ""}:
                updates[column] = None if kind == "int" else []
            elif kind == "int":
                updates[column] = int(raw_value)
            else:
                updates[column] = [int(part) for part in raw_value.split(",") if part.strip()]
    except ValueError as exc:
        await update.effective_message.reply_text(
            f"⚠️ {html.escape(str(exc))}\n\n{ADVANCED_HELP}",
            parse_mode="HTML",
        )
        return

    updated = await _db(context).update_alert(alert.id, **updates)
    if updated is not None:
        await send_long(update, f"✅ Filtros actualizados\n\n{format_alert(updated)}")


# --------------------------------------------------------------------------- #
# Asistente /nuevo
# --------------------------------------------------------------------------- #


def _wizard(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    return context.user_data.setdefault("wizard", {})


async def start_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["wizard"] = {}
    await update.effective_message.reply_text(
        "🆕 <b>Nueva búsqueda</b> (1/7)\n\n"
        "¿Cómo la llamamos? Ej: <i>PS5 barata</i>\n\n"
        "<i>Escribe /cancelar para salir.</i>",
        parse_mode="HTML",
    )
    return WIZ_NAME


async def new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = (update.effective_message.text or "").strip()[:80]
    if not name:
        await update.effective_message.reply_text("Necesito un nombre.")
        return WIZ_NAME
    _wizard(context)["name"] = name
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Wallapop", callback_data="wizpf:wallapop")],
            [InlineKeyboardButton("Vinted", callback_data="wizpf:vinted")],
            [InlineKeyboardButton("Ambas", callback_data="wizpf:both")],
        ]
    )
    await update.effective_message.reply_text(
        "(2/7) ¿Dónde buscamos?", reply_markup=keyboard
    )
    return WIZ_PLATFORMS


async def new_platforms(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    assert query is not None
    await query.answer()
    choice = query.data.split(":", 1)[1]
    mapping = {
        "wallapop": ["wallapop"],
        "vinted": ["vinted"],
        "both": ["wallapop", "vinted"],
    }
    platforms = mapping.get(choice)
    if platforms is None:
        return WIZ_PLATFORMS
    _wizard(context)["platforms"] = platforms
    label = " + ".join(PLATFORM_LABELS[p] for p in platforms)
    await query.edit_message_text(
        f"🏪 Plataformas: <b>{label}</b>\n\n"
        "(3/7) ¿Qué palabras clave busco? Ej: <i>playstation 5</i>",
        parse_mode="HTML",
        reply_markup=None,
    )
    return WIZ_KEYWORDS


async def new_keywords(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    keywords = (update.effective_message.text or "").strip()
    if not keywords:
        await update.effective_message.reply_text(
            "Necesito al menos una palabra clave."
        )
        return WIZ_KEYWORDS
    _wizard(context)["keywords"] = keywords
    await update.effective_message.reply_text(
        "(4/7) Precio: <code>mín-máx</code>.\n\n"
        "Ejemplos: <code>100-400</code>, <code>100-</code> (solo mínimo),"
        " <code>-400</code> (solo máximo), <code>-</code> (sin filtro).",
        parse_mode="HTML",
    )
    return WIZ_PRICE


async def new_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.effective_message.text or ""
    try:
        minimum, maximum = parse_price_range(text)
    except ValueError as exc:
        await update.effective_message.reply_text(f"⚠️ {exc}")
        return WIZ_PRICE
    wizard = _wizard(context)
    wizard["min_price"] = minimum
    wizard["max_price"] = maximum

    await update.effective_message.reply_text(
        "(5/7) Palabras o frases que deben excluirse, separadas por comas."
        " Ej: <code>roto, para piezas, bisagras</code>.\n"
        "Escribe <code>-</code> si no quieres excluir nada.",
        parse_mode="HTML",
    )
    return WIZ_EXCLUDE


async def new_exclude(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = (update.effective_message.text or "").strip()
    wizard = _wizard(context)
    wizard["exclude_words"] = "" if text == "-" else text
    settings = _settings(context)
    await update.effective_message.reply_text(
        "(6/7) ¿Cada cuántos segundos reviso?"
        f" Mínimo {settings.min_interval}, por defecto"
        f" {settings.default_interval}. Escribe <code>-</code> para el"
        " valor por defecto.",
        parse_mode="HTML",
    )
    return WIZ_INTERVAL


async def new_interval(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    settings = _settings(context)
    text = (update.effective_message.text or "").strip()
    if text in {"-", ""}:
        interval = settings.default_interval
    else:
        try:
            interval = int(text)
        except ValueError:
            await update.effective_message.reply_text(
                "Escribe un número de segundos o <code>-</code>.",
                parse_mode="HTML",
            )
            return WIZ_INTERVAL
        interval = max(interval, settings.min_interval)
        if interval > 3600:
            await update.effective_message.reply_text(
                "El máximo son 3600 segundos (1 hora)."
            )
            return WIZ_INTERVAL
    _wizard(context)["interval_seconds"] = interval

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔔 Sí, avisar de los ya publicados",
                    callback_data="wiznotify:yes",
                )
            ],
            [
                InlineKeyboardButton(
                    "🤫 No, solo anuncios nuevos", callback_data="wiznotify:no"
                )
            ],
        ]
    )
    await update.effective_message.reply_text(
        "(7/7) ¿Quieres que avise también de los anuncios que ya existen?"
        "\n\nLo normal es <b>No</b>: solo te llegarán los que se publiquen"
        " a partir de ahora.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    return WIZ_NOTIFY


async def new_notify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query is not None
    await query.answer()
    notify_existing = query.data.split(":", 1)[1] == "yes"
    wizard = _wizard(context)

    try:
        new = NewAlert(
            chat_id=update.effective_chat.id,
            name=wizard["name"],
            platforms=wizard["platforms"],
            keywords=wizard["keywords"],
            min_price=wizard.get("min_price"),
            max_price=wizard.get("max_price"),
            exclude_words=wizard.get("exclude_words", ""),
            interval_seconds=wizard["interval_seconds"],
            notify_existing=notify_existing,
        )
    except KeyError:
        await query.edit_message_text(
            "Se perdió el estado del asistente. Empieza de nuevo con /nuevo."
        )
        context.user_data.pop("wizard", None)
        return ConversationHandler.END

    alert = await _db(context).create_alert(new)
    await query.edit_message_text(
        f"✅ Búsqueda #{alert.id} creada. La primera comprobación llegará en"
        " unos segundos.",
        reply_markup=None,
    )
    await send_long(
        update,
        format_alert(alert)
        + "\n\n"
        + (
            "Te avisaré de los anuncios nuevos. Si quieres ver qué hay ahora,"
            f" usa /probar {alert.id}."
            if not notify_existing
            else "También te avisaré de los anuncios ya publicados en la"
            " primera pasada."
        )
        + (
            f"\n\n🎯 Modo estricto activado: descarto anuncios cuyo título no"
            f" contenga ninguna palabra clave. Desactívalo con"
            f" /editar {alert.id} estricto off."
            if alert.strict_keywords
            else ""
        )
        + (
            f"\n\n📦 Solo avisaré anuncios de Wallapop con envío disponible."
            f" Desactívalo con /editar {alert.id} envio off."
            if "wallapop" in alert.platforms
            else ""
        )
        + (
            f"\n\n📉 Si un anuncio que ya te he avisado baja de precio, te"
            f" avisaré también. Desactívalo con"
            f" /editar {alert.id} precios off."
        ),
    )
    context.user_data.pop("wizard", None)
    return ConversationHandler.END


async def cancel_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("wizard", None)
    await update.effective_message.reply_text("Creación cancelada.")
    return ConversationHandler.END


# --------------------------------------------------------------------------- #
# Callbacks de avisos y borrado
# --------------------------------------------------------------------------- #


async def mute_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    assert query is not None
    chat = update.effective_chat
    if chat is None:
        return
    try:
        alert_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer()
        return

    alert = await _db(context).get_alert(alert_id)
    if alert is None or alert.chat_id != chat.id:
        await query.answer("Esa búsqueda ya no existe", show_alert=True)
        return

    await _db(context).update_alert(alert.id, active=False)
    await query.answer("Búsqueda silenciada")
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass
    await _notifier(context).send_text(
        chat.id,
        f"🔕 Búsqueda <b>#{alert.id}</b> ({html.escape(alert.name)}) pausada."
        f" Usa /reanudar {alert.id} para volver a activarla.",
    )


async def delete_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    assert query is not None
    chat = update.effective_chat
    if chat is None:
        return
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer()
        return
    try:
        alert_id = int(parts[1])
    except ValueError:
        await query.answer()
        return
    action = parts[2]

    alert = await _db(context).get_alert(alert_id)
    if alert is None or alert.chat_id != chat.id:
        await query.answer("Esa búsqueda ya no existe", show_alert=True)
        return

    if action == "yes":
        await _db(context).delete_alert(alert_id)
        await query.answer("Búsqueda eliminada")
        await query.edit_message_text(
            f"🗑 Búsqueda #{alert_id} eliminada.", reply_markup=None
        )
    else:
        await query.answer("Cancelado")
        await query.edit_message_text(
            "Operación cancelada.", reply_markup=None
        )


# --------------------------------------------------------------------------- #
# Registro
# --------------------------------------------------------------------------- #


def build_new_conversation() -> ConversationHandler:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"If 'per_message=False'.*",
            category=PTBUserWarning,
        )
        return _build_conversation()


def _build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("nuevo", start_new)],
        states={
            WIZ_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_name)],
            WIZ_PLATFORMS: [CallbackQueryHandler(new_platforms, pattern=r"^wizpf:")],
            WIZ_KEYWORDS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, new_keywords)
            ],
            WIZ_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_price)],
            WIZ_EXCLUDE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, new_exclude)
            ],
            WIZ_INTERVAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, new_interval)
            ],
            WIZ_NOTIFY: [CallbackQueryHandler(new_notify, pattern=r"^wiznotify:")],
        },
        fallbacks=[CommandHandler("cancelar", cancel_new)],
        allow_reentry=True,
        conversation_timeout=600,
    )


def register_handlers(app: Application, settings: Settings) -> None:
    app.add_handler(TypeHandler(Update, enforce_auth), group=-1)
    app.add_handler(build_new_conversation())
    app.add_handler(CommandHandler(["start", "ayuda", "help"], help_command))
    app.add_handler(CommandHandler("lista", list_alerts))
    app.add_handler(CommandHandler("ver", view_alert))
    app.add_handler(CommandHandler("probar", test_alert))
    app.add_handler(CommandHandler("editar", edit_alert))
    app.add_handler(CommandHandler("avanzado", advanced_alert))
    app.add_handler(CommandHandler("pausar", pause_alert))
    app.add_handler(CommandHandler("reanudar", resume_alert))
    app.add_handler(CommandHandler("borrar", delete_alert))
    app.add_handler(CommandHandler("estado", status_command))
    app.add_handler(CallbackQueryHandler(mute_callback, pattern=r"^mute:"))
    app.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del:"))
    app.add_handler(CommandHandler("cancelar", cancel_new))
