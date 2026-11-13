"""Persistencia en SQLite: alertas y anuncios ya vistos."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    platforms TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '',
    min_price REAL,
    max_price REAL,
    wallapop_category_id INTEGER,
    wallapop_shipping INTEGER NOT NULL DEFAULT 1,
    radius_km INTEGER,
    vinted_catalog_ids TEXT NOT NULL DEFAULT '',
    vinted_brand_ids TEXT NOT NULL DEFAULT '',
    vinted_condition_ids TEXT NOT NULL DEFAULT '',
    exclude_words TEXT NOT NULL DEFAULT '',
    strict_keywords INTEGER NOT NULL DEFAULT 1,
    interval_seconds INTEGER NOT NULL,
    notify_existing INTEGER NOT NULL DEFAULT 0,
    notify_price_changes INTEGER NOT NULL DEFAULT 1,
    seeded INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_checked_at TEXT
);

CREATE TABLE IF NOT EXISTS seen_items (
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    item_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_price REAL,
    PRIMARY KEY (alert_id, source, item_id)
);

CREATE INDEX IF NOT EXISTS idx_seen_first_seen ON seen_items(first_seen_at);

CREATE TABLE IF NOT EXISTS user_locations (
    chat_id INTEGER PRIMARY KEY,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    updated_at TEXT NOT NULL
);
"""

LIST_FIELDS = {
    "platforms",
    "vinted_catalog_ids",
    "vinted_brand_ids",
    "vinted_condition_ids",
}

UPDATABLE_FIELDS = {
    "name",
    "platforms",
    "keywords",
    "min_price",
    "max_price",
    "wallapop_category_id",
    "wallapop_shipping",
    "radius_km",
    "vinted_catalog_ids",
    "vinted_brand_ids",
    "vinted_condition_ids",
    "exclude_words",
    "strict_keywords",
    "interval_seconds",
    "notify_existing",
    "notify_price_changes",
    "seeded",
    "active",
    "last_checked_at",
}


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _csv_ints(raw: str | None) -> list[int]:
    if not raw:
        return []
    result: list[int] = []
    for chunk in str(raw).split(","):
        chunk = chunk.strip()
        if chunk:
            result.append(int(chunk))
    return result


def _csv_strings(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [chunk.strip() for chunk in str(raw).split(",") if chunk.strip()]


@dataclass
class Alert:
    id: int
    chat_id: int
    name: str
    platforms: list[str]
    keywords: str
    min_price: float | None
    max_price: float | None
    wallapop_category_id: int | None
    wallapop_shipping: bool
    vinted_catalog_ids: list[int]
    vinted_brand_ids: list[int]
    vinted_condition_ids: list[int]
    exclude_words: str
    strict_keywords: bool
    interval_seconds: int
    notify_existing: bool
    notify_price_changes: bool
    seeded: bool
    active: bool
    created_at: str
    last_checked_at: str | None
    radius_km: int | None = None
    # Origen del chat, resuelto al leer la alerta (no es una columna).
    origin_latitude: float | None = None
    origin_longitude: float | None = None


@dataclass
class NewAlert:
    chat_id: int
    name: str
    platforms: list[str]
    keywords: str
    min_price: float | None = None
    max_price: float | None = None
    wallapop_category_id: int | None = None
    wallapop_shipping: bool = True
    radius_km: int | None = None
    vinted_catalog_ids: list[int] = field(default_factory=list)
    vinted_brand_ids: list[int] = field(default_factory=list)
    vinted_condition_ids: list[int] = field(default_factory=list)
    exclude_words: str = ""
    strict_keywords: bool = True
    interval_seconds: int = 90
    notify_existing: bool = False
    notify_price_changes: bool = True


def _optional(row: aiosqlite.Row, key: str, default: Any = None) -> Any:
    """Lee una columna que puede no estar en la consulta."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _row_to_alert(row: aiosqlite.Row) -> Alert:
    return Alert(
        id=row["id"],
        chat_id=row["chat_id"],
        name=row["name"],
        platforms=_csv_strings(row["platforms"]),
        keywords=row["keywords"],
        min_price=row["min_price"],
        max_price=row["max_price"],
        wallapop_category_id=row["wallapop_category_id"],
        wallapop_shipping=bool(row["wallapop_shipping"]),
        vinted_catalog_ids=_csv_ints(row["vinted_catalog_ids"]),
        vinted_brand_ids=_csv_ints(row["vinted_brand_ids"]),
        vinted_condition_ids=_csv_ints(row["vinted_condition_ids"]),
        exclude_words=row["exclude_words"],
        strict_keywords=bool(row["strict_keywords"]),
        interval_seconds=row["interval_seconds"],
        notify_existing=bool(row["notify_existing"]),
        notify_price_changes=bool(row["notify_price_changes"]),
        seeded=bool(row["seeded"]),
        active=bool(row["active"]),
        created_at=row["created_at"],
        last_checked_at=row["last_checked_at"],
        radius_km=_optional(row, "radius_km"),
        origin_latitude=_optional(row, "origin_latitude"),
        origin_longitude=_optional(row, "origin_longitude"),
    )


class Database:
    """Capa de acceso a datos asíncrona."""

    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("La base de datos no está conectada")
        return self._conn

    async def connect(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.executescript(SCHEMA)
        await self._migrate()
        await self._conn.commit()

    async def _migrate(self) -> None:
        """Actualiza el esquema de bases de datos creadas por versiones previas."""
        async with self.conn.execute("PRAGMA table_info(alerts)") as cursor:
            columns = {row["name"] for row in await cursor.fetchall()}

        if "wallapop_shipping" not in columns:
            await self.conn.execute(
                "ALTER TABLE alerts ADD COLUMN wallapop_shipping"
                " INTEGER NOT NULL DEFAULT 1"
            )
        if "seeded" not in columns:
            await self.conn.execute(
                "ALTER TABLE alerts ADD COLUMN seeded INTEGER NOT NULL DEFAULT 0"
            )
        if "notify_price_changes" not in columns:
            await self.conn.execute(
                "ALTER TABLE alerts ADD COLUMN notify_price_changes"
                " INTEGER NOT NULL DEFAULT 1"
            )
        if "strict_keywords" not in columns:
            await self.conn.execute(
                "ALTER TABLE alerts ADD COLUMN strict_keywords"
                " INTEGER NOT NULL DEFAULT 1"
            )

        dropped_coordinates = False
        for obsolete in ("latitude", "longitude"):
            if obsolete in columns:
                try:
                    await self.conn.execute(
                        f"ALTER TABLE alerts DROP COLUMN {obsolete}"
                    )
                    dropped_coordinates = True
                except aiosqlite.Error:
                    logger.warning(
                        "No se pudo eliminar la columna obsoleta %s", obsolete
                    )

        if "radius_km" not in columns:
            await self.conn.execute(
                "ALTER TABLE alerts ADD COLUMN radius_km INTEGER"
            )
        elif dropped_coordinates:
            # El radio antiguo apuntaba a coordenadas que ya no existen.
            await self.conn.execute("UPDATE alerts SET radius_km = NULL")

        async with self.conn.execute("PRAGMA table_info(seen_items)") as cursor:
            seen_columns = {row["name"] for row in await cursor.fetchall()}
        if "last_price" not in seen_columns:
            await self.conn.execute(
                "ALTER TABLE seen_items ADD COLUMN last_price REAL"
            )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ----------------------------- alertas ------------------------------ #

    async def create_alert(self, new: NewAlert) -> Alert:
        cursor = await self.conn.execute(
            """
            INSERT INTO alerts (
                chat_id, name, platforms, keywords, min_price, max_price,
                wallapop_category_id, wallapop_shipping, radius_km,
                vinted_catalog_ids, vinted_brand_ids, vinted_condition_ids,
                exclude_words, strict_keywords, interval_seconds,
                notify_existing, notify_price_changes, seeded, active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?)
            """,
            (
                new.chat_id,
                new.name,
                ",".join(new.platforms),
                new.keywords,
                new.min_price,
                new.max_price,
                new.wallapop_category_id,
                int(new.wallapop_shipping),
                new.radius_km,
                ",".join(str(v) for v in new.vinted_catalog_ids),
                ",".join(str(v) for v in new.vinted_brand_ids),
                ",".join(str(v) for v in new.vinted_condition_ids),
                new.exclude_words,
                int(new.strict_keywords),
                new.interval_seconds,
                int(new.notify_existing),
                int(new.notify_price_changes),
                utcnow_iso(),
            ),
        )
        await self.conn.commit()
        alert = await self.get_alert(int(cursor.lastrowid or 0))
        if alert is None:  # pragma: no cover - no debería ocurrir
            raise RuntimeError("No se pudo crear la alerta")
        return alert

    async def get_alert(self, alert_id: int) -> Alert | None:
        async with self.conn.execute(
            """
            SELECT a.*, l.latitude AS origin_latitude,
                   l.longitude AS origin_longitude
            FROM alerts a
            LEFT JOIN user_locations l ON l.chat_id = a.chat_id
            WHERE a.id = ?
            """,
            (alert_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_alert(row) if row is not None else None

    async def list_alerts(
        self, chat_id: int | None = None, active_only: bool = False
    ) -> list[Alert]:
        clauses: list[str] = []
        params: list[Any] = []
        if chat_id is not None:
            clauses.append("a.chat_id = ?")
            params.append(chat_id)
        if active_only:
            clauses.append("a.active = 1")
        query = (
            "SELECT a.*, l.latitude AS origin_latitude,"
            " l.longitude AS origin_longitude"
            " FROM alerts a"
            " LEFT JOIN user_locations l ON l.chat_id = a.chat_id"
        )
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY a.id"
        async with self.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_alert(row) for row in rows]

    async def update_alert(self, alert_id: int, **fields: Any) -> Alert | None:
        cleaned: dict[str, Any] = {}
        for key, value in fields.items():
            if key not in UPDATABLE_FIELDS:
                raise ValueError(f"Campo no editable: {key}")
            if key in LIST_FIELDS:
                value = ",".join(str(item) for item in value)
            elif isinstance(value, bool):
                value = int(value)
            cleaned[key] = value
        if not cleaned:
            return await self.get_alert(alert_id)
        assignments = ", ".join(f"{key} = ?" for key in cleaned)
        values = list(cleaned.values()) + [alert_id]
        await self.conn.execute(
            f"UPDATE alerts SET {assignments} WHERE id = ?", values
        )
        await self.conn.commit()
        return await self.get_alert(alert_id)

    async def delete_alert(self, alert_id: int) -> bool:
        cursor = await self.conn.execute(
            "DELETE FROM alerts WHERE id = ?", (alert_id,)
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def mark_checked(self, alert_id: int) -> None:
        await self.conn.execute(
            "UPDATE alerts SET last_checked_at = ? WHERE id = ?",
            (utcnow_iso(), alert_id),
        )
        await self.conn.commit()

    # ------------------------- ubicación del chat ------------------------- #

    async def get_location(
        self, chat_id: int
    ) -> tuple[float, float] | None:
        """Origen (latitud, longitud) guardado para un chat."""
        async with self.conn.execute(
            "SELECT latitude, longitude FROM user_locations WHERE chat_id = ?",
            (chat_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return float(row["latitude"]), float(row["longitude"])

    async def set_location(
        self, chat_id: int, latitude: float, longitude: float
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO user_locations (chat_id, latitude, longitude, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                updated_at = excluded.updated_at
            """,
            (chat_id, latitude, longitude, utcnow_iso()),
        )
        await self.conn.commit()

    async def delete_location(self, chat_id: int) -> bool:
        cursor = await self.conn.execute(
            "DELETE FROM user_locations WHERE chat_id = ?", (chat_id,)
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    # -------------------------- anuncios vistos ------------------------- #

    async def is_seen(self, alert_id: int, source: str, item_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM seen_items WHERE alert_id = ? AND source = ? AND item_id = ?",
            (alert_id, source, item_id),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def mark_seen(
        self,
        alert_id: int,
        source: str,
        item_id: str,
        price: float | None = None,
    ) -> None:
        await self.mark_seen_many(
            alert_id, source, [item_id], {item_id: price}
        )

    async def mark_seen_many(
        self,
        alert_id: int,
        source: str,
        item_ids: list[str],
        prices: dict[str, float | None] | None = None,
    ) -> None:
        if not item_ids:
            return
        now = utcnow_iso()
        prices = prices or {}
        await self.conn.executemany(
            "INSERT OR IGNORE INTO seen_items"
            " (alert_id, source, item_id, first_seen_at, last_price)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (alert_id, source, item_id, now, prices.get(item_id))
                for item_id in item_ids
            ],
        )
        await self.conn.commit()

    async def get_seen_prices(
        self, alert_id: int, source: str, item_ids: list[str]
    ) -> dict[str, float | None]:
        """Precio guardado de los anuncios vistos indicados (si existen)."""
        result: dict[str, float | None] = {}
        for start in range(0, len(item_ids), 500):
            chunk = item_ids[start : start + 500]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            async with self.conn.execute(
                "SELECT item_id, last_price FROM seen_items"
                f" WHERE alert_id = ? AND source = ?"
                f" AND item_id IN ({placeholders})",
                (alert_id, source, *chunk),
            ) as cursor:
                async for row in cursor:
                    result[row["item_id"]] = row["last_price"]
        return result

    async def update_seen_prices(
        self,
        alert_id: int,
        source: str,
        prices: dict[str, float | None],
    ) -> None:
        """Actualiza el último precio conocido de anuncios ya vistos."""
        if not prices:
            return
        await self.conn.executemany(
            "UPDATE seen_items SET last_price = ?"
            " WHERE alert_id = ? AND source = ? AND item_id = ?",
            [
                (price, alert_id, source, item_id)
                for item_id, price in prices.items()
            ],
        )
        await self.conn.commit()

    async def seen_count(self, alert_id: int) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM seen_items WHERE alert_id = ?", (alert_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def purge_seen(self, days: int) -> int:
        threshold = (
            datetime.now(UTC) - timedelta(days=days)
        ).isoformat(timespec="seconds")
        cursor = await self.conn.execute(
            "DELETE FROM seen_items WHERE first_seen_at < ?", (threshold,)
        )
        await self.conn.commit()
        return cursor.rowcount

    async def stats(self) -> dict[str, int]:
        async with self.conn.execute("SELECT COUNT(*) FROM alerts") as cursor:
            row = await cursor.fetchone()
        total_alerts = int(row[0]) if row else 0
        async with self.conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE active = 1"
        ) as cursor:
            row = await cursor.fetchone()
        active_alerts = int(row[0]) if row else 0
        async with self.conn.execute("SELECT COUNT(*) FROM seen_items") as cursor:
            row = await cursor.fetchone()
        seen_items = int(row[0]) if row else 0
        return {
            "alerts": total_alerts,
            "active_alerts": active_alerts,
            "seen_items": seen_items,
        }
