"""Persistencia en SQLite: alertas y anuncios ya vistos."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    platforms TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '',
    min_price REAL,
    max_price REAL,
    latitude REAL,
    longitude REAL,
    radius_km INTEGER,
    wallapop_category_id INTEGER,
    vinted_catalog_ids TEXT NOT NULL DEFAULT '',
    vinted_brand_ids TEXT NOT NULL DEFAULT '',
    vinted_condition_ids TEXT NOT NULL DEFAULT '',
    exclude_words TEXT NOT NULL DEFAULT '',
    strict_keywords INTEGER NOT NULL DEFAULT 1,
    interval_seconds INTEGER NOT NULL,
    notify_existing INTEGER NOT NULL DEFAULT 0,
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
    PRIMARY KEY (alert_id, source, item_id)
);

CREATE INDEX IF NOT EXISTS idx_seen_first_seen ON seen_items(first_seen_at);
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
    "latitude",
    "longitude",
    "radius_km",
    "wallapop_category_id",
    "vinted_catalog_ids",
    "vinted_brand_ids",
    "vinted_condition_ids",
    "exclude_words",
    "strict_keywords",
    "interval_seconds",
    "notify_existing",
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
    latitude: float | None
    longitude: float | None
    radius_km: int | None
    wallapop_category_id: int | None
    vinted_catalog_ids: list[int]
    vinted_brand_ids: list[int]
    vinted_condition_ids: list[int]
    exclude_words: str
    strict_keywords: bool
    interval_seconds: int
    notify_existing: bool
    seeded: bool
    active: bool
    created_at: str
    last_checked_at: str | None


@dataclass
class NewAlert:
    chat_id: int
    name: str
    platforms: list[str]
    keywords: str
    min_price: float | None = None
    max_price: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: int | None = None
    wallapop_category_id: int | None = None
    vinted_catalog_ids: list[int] = field(default_factory=list)
    vinted_brand_ids: list[int] = field(default_factory=list)
    vinted_condition_ids: list[int] = field(default_factory=list)
    exclude_words: str = ""
    strict_keywords: bool = True
    interval_seconds: int = 90
    notify_existing: bool = False


def _row_to_alert(row: aiosqlite.Row) -> Alert:
    return Alert(
        id=row["id"],
        chat_id=row["chat_id"],
        name=row["name"],
        platforms=_csv_strings(row["platforms"]),
        keywords=row["keywords"],
        min_price=row["min_price"],
        max_price=row["max_price"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        radius_km=row["radius_km"],
        wallapop_category_id=row["wallapop_category_id"],
        vinted_catalog_ids=_csv_ints(row["vinted_catalog_ids"]),
        vinted_brand_ids=_csv_ints(row["vinted_brand_ids"]),
        vinted_condition_ids=_csv_ints(row["vinted_condition_ids"]),
        exclude_words=row["exclude_words"],
        strict_keywords=bool(row["strict_keywords"]),
        interval_seconds=row["interval_seconds"],
        notify_existing=bool(row["notify_existing"]),
        seeded=bool(row["seeded"]),
        active=bool(row["active"]),
        created_at=row["created_at"],
        last_checked_at=row["last_checked_at"],
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
        """Añade columnas nuevas a bases de datos creadas por versiones previas."""
        async with self.conn.execute("PRAGMA table_info(alerts)") as cursor:
            columns = {row["name"] for row in await cursor.fetchall()}
        if "strict_keywords" not in columns:
            await self.conn.execute(
                "ALTER TABLE alerts ADD COLUMN strict_keywords INTEGER NOT NULL DEFAULT 0"
            )
        if "seeded" not in columns:
            await self.conn.execute(
                "ALTER TABLE alerts ADD COLUMN seeded INTEGER NOT NULL DEFAULT 0"
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
                latitude, longitude, radius_km, wallapop_category_id,
                vinted_catalog_ids, vinted_brand_ids, vinted_condition_ids,
                exclude_words, strict_keywords, interval_seconds,
                notify_existing, seeded, active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?)
            """,
            (
                new.chat_id,
                new.name,
                ",".join(new.platforms),
                new.keywords,
                new.min_price,
                new.max_price,
                new.latitude,
                new.longitude,
                new.radius_km,
                new.wallapop_category_id,
                ",".join(str(v) for v in new.vinted_catalog_ids),
                ",".join(str(v) for v in new.vinted_brand_ids),
                ",".join(str(v) for v in new.vinted_condition_ids),
                new.exclude_words,
                int(new.strict_keywords),
                new.interval_seconds,
                int(new.notify_existing),
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
            "SELECT * FROM alerts WHERE id = ?", (alert_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_alert(row) if row is not None else None

    async def list_alerts(
        self, chat_id: int | None = None, active_only: bool = False
    ) -> list[Alert]:
        clauses: list[str] = []
        params: list[Any] = []
        if chat_id is not None:
            clauses.append("chat_id = ?")
            params.append(chat_id)
        if active_only:
            clauses.append("active = 1")
        query = "SELECT * FROM alerts"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id"
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

    # -------------------------- anuncios vistos ------------------------- #

    async def is_seen(self, alert_id: int, source: str, item_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM seen_items WHERE alert_id = ? AND source = ? AND item_id = ?",
            (alert_id, source, item_id),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def mark_seen(self, alert_id: int, source: str, item_id: str) -> None:
        await self.mark_seen_many(alert_id, source, [item_id])

    async def mark_seen_many(
        self, alert_id: int, source: str, item_ids: list[str]
    ) -> None:
        if not item_ids:
            return
        now = utcnow_iso()
        await self.conn.executemany(
            "INSERT OR IGNORE INTO seen_items (alert_id, source, item_id, first_seen_at)"
            " VALUES (?, ?, ?, ?)",
            [(alert_id, source, item_id, now) for item_id in item_ids],
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
