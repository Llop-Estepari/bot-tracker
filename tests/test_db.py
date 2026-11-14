"""Tests de persistencia con SQLite."""

from __future__ import annotations

import sqlite3

import pytest

from db import Database, NewAlert

OLD_SCHEMA = """
CREATE TABLE alerts (
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
    notify_price_changes INTEGER NOT NULL DEFAULT 1,
    seeded INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_checked_at TEXT
);

CREATE TABLE seen_items (
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    item_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (alert_id, source, item_id)
);
"""


@pytest.fixture
async def database(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.connect()
    yield db
    await db.close()


def make_new_alert(**overrides) -> NewAlert:
    values = {
        "chat_id": 123,
        "name": "prueba",
        "platforms": ["wallapop", "vinted"],
        "keywords": "bicicleta",
        "min_price": 50,
        "max_price": 300,
        "exclude_words": "roto",
        "interval_seconds": 90,
    }
    values.update(overrides)
    return NewAlert(**values)


async def test_crear_y_leer_alerta(database):
    alert = await database.create_alert(make_new_alert())

    assert alert.id > 0
    assert alert.chat_id == 123
    assert alert.platforms == ["wallapop", "vinted"]
    assert alert.min_price == 50
    assert alert.active is True
    assert alert.notify_existing is False
    assert alert.wallapop_shipping is True
    assert alert.strict_keywords is True
    assert alert.radius_km is None

    fetched = await database.get_alert(alert.id)
    assert fetched is not None
    assert fetched.name == "prueba"
    assert fetched.last_checked_at is None


async def test_actualizar_listas_y_booleanos(database):
    alert = await database.create_alert(make_new_alert())

    updated = await database.update_alert(
        alert.id,
        platforms=["vinted"],
        vinted_brand_ids=[53, 417],
        wallapop_shipping=False,
        strict_keywords=False,
        active=False,
    )

    assert updated is not None
    assert updated.platforms == ["vinted"]
    assert updated.vinted_brand_ids == [53, 417]
    assert updated.wallapop_shipping is False
    assert updated.strict_keywords is False
    assert updated.active is False


async def test_listar_filtra_por_chat_y_activas(database):
    first = await database.create_alert(make_new_alert(chat_id=1))
    await database.create_alert(make_new_alert(chat_id=2))
    await database.update_alert(first.id, active=False)

    assert len(await database.list_alerts()) == 2
    assert len(await database.list_alerts(chat_id=1)) == 1
    assert await database.list_alerts(chat_id=1, active_only=True) == []


async def test_deduplicacion_de_anuncios(database):
    alert = await database.create_alert(make_new_alert())

    assert await database.is_seen(alert.id, "vinted", "42") is False
    await database.mark_seen(alert.id, "vinted", "42")
    await database.mark_seen(alert.id, "vinted", "42")
    assert await database.is_seen(alert.id, "vinted", "42") is True
    assert await database.seen_count(alert.id) == 1

    await database.mark_seen_many(alert.id, "vinted", ["1", "2", "3"])
    assert await database.seen_count(alert.id) == 4


async def test_borrar_alerta_elimina_vistos(database):
    alert = await database.create_alert(make_new_alert())
    await database.mark_seen(alert.id, "wallapop", "abc")

    assert await database.delete_alert(alert.id) is True
    assert await database.get_alert(alert.id) is None

    async with database.conn.execute(
        "SELECT COUNT(*) FROM seen_items WHERE alert_id = ?", (alert.id,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row[0] == 0


async def test_guarda_y_actualiza_el_ultimo_precio(database):
    alert = await database.create_alert(make_new_alert())

    await database.mark_seen(alert.id, "wallapop", "1", 100)
    await database.mark_seen(alert.id, "wallapop", "2")

    prices = await database.get_seen_prices(
        alert.id, "wallapop", ["1", "2", "3"]
    )
    assert prices == {"1": 100.0, "2": None}

    await database.update_seen_prices(alert.id, "wallapop", {"1": 80})
    prices = await database.get_seen_prices(alert.id, "wallapop", ["1", "2"])
    assert prices == {"1": 80.0, "2": None}


async def test_migracion_anade_columnas_de_precio(tmp_path):
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.executescript(OLD_SCHEMA)
    connection.close()

    database = Database(path)
    await database.connect()
    try:
        async with database.conn.execute(
            "PRAGMA table_info(alerts)"
        ) as cursor:
            alert_columns = {row["name"] for row in await cursor.fetchall()}
        async with database.conn.execute(
            "PRAGMA table_info(seen_items)"
        ) as cursor:
            seen_columns = {row["name"] for row in await cursor.fetchall()}
        assert "notify_price_changes" not in alert_columns
        assert "wallapop_shipping" in alert_columns
        assert "latitude" not in alert_columns
        assert "longitude" not in alert_columns
        assert "radius_km" in alert_columns
        assert "strict_keywords" in alert_columns
        assert "last_price" in seen_columns
    finally:
        await database.close()


async def test_radio_por_defecto_es_sin_limite(database):
    alert = await database.create_alert(make_new_alert())

    assert alert.radius_km is None
    updated = await database.update_alert(alert.id, radius_km=25)
    assert updated is not None
    assert updated.radius_km == 25

    cleared = await database.update_alert(alert.id, radius_km=None)
    assert cleared is not None
    assert cleared.radius_km is None


async def test_ubicacion_del_chat(database):
    assert await database.get_location(123) is None

    await database.set_location(123, 41.3874, 2.1686)
    assert await database.get_location(123) == (41.3874, 2.1686)

    await database.set_location(123, 40.4168, -3.7038)
    assert await database.get_location(123) == (40.4168, -3.7038)

    assert await database.delete_location(123) is True
    assert await database.get_location(123) is None
    assert await database.delete_location(123) is False


async def test_la_alerta_hereda_el_origen_del_chat(database):
    await database.set_location(123, 41.3874, 2.1686)
    alert = await database.create_alert(make_new_alert(chat_id=123))

    assert alert.origin_latitude == 41.3874
    assert alert.origin_longitude == 2.1686

    fetched = await database.get_alert(alert.id)
    assert fetched is not None
    assert fetched.origin_latitude == 41.3874

    listed = await database.list_alerts(chat_id=123)
    assert listed[0].origin_longitude == 2.1686


async def test_migracion_readd_strict_keywords(tmp_path):
    path = tmp_path / "v120.db"
    database = Database(path)
    await database.connect()
    alert = await database.create_alert(make_new_alert())
    await database.close()

    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE alerts DROP COLUMN strict_keywords")
    connection.commit()
    connection.close()

    database = Database(path)
    await database.connect()
    try:
        fetched = await database.get_alert(alert.id)
        assert fetched is not None
        assert fetched.strict_keywords is True
    finally:
        await database.close()


async def test_estado_interno_clave_valor(database):
    assert await database.get_state("last_version_check") is None

    await database.set_state("last_version_check", "2026-11-14")
    assert await database.get_state("last_version_check") == "2026-11-14"

    await database.set_state("last_version_check", "2026-11-15")
    assert await database.get_state("last_version_check") == "2026-11-15"
