"""Tests de persistencia con SQLite."""

from __future__ import annotations

import pytest

from db import Database, NewAlert


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
        active=False,
    )

    assert updated is not None
    assert updated.platforms == ["vinted"]
    assert updated.vinted_brand_ids == [53, 417]
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
