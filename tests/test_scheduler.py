"""Tests del scheduler con fuentes y notificador simulados."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

import scheduler as scheduler_module
from config import Settings
from db import Database, NewAlert
from scheduler import Tracker
from sources.base import Listing


def make_settings(**overrides) -> Settings:
    values = {
        "telegram_bot_token": "test",
        "allowed_chat_ids": frozenset({1}),
        "admin_chat_ids": frozenset({1}),
        "database_path": Path("test.db"),
        "default_interval": 90,
        "min_interval": 60,
        "max_notifications_per_check": 15,
        "seen_retention_days": 60,
        "wallapop_base_url": "https://es.wallapop.com",
        "wallapop_api_base": "https://api.wallapop.com",
        "vinted_base_url": "https://www.vinted.es",
        "vinted_locale": "es-ES",
        "request_timeout": 25.0,
        "log_level": "INFO",
    }
    values.update(overrides)
    return Settings(**values)


def make_listing(item_id: str, price: float = 100.0) -> Listing:
    return Listing(
        source="wallapop",
        item_id=item_id,
        title=f"Anuncio {item_id}",
        price=price,
        currency="EUR",
        url=f"https://example.com/{item_id}",
    )


class FakeSource:
    name = "wallapop"

    def __init__(self, listings: list[Listing]) -> None:
        self.listings = listings
        self.calls = 0

    async def search(self, alert) -> list[Listing]:
        self.calls += 1
        return list(self.listings)

    async def close(self) -> None:
        pass


class FakeNotifier:
    def __init__(self) -> None:
        self.listings: list[str] = []
        self.price_changes: list[tuple[str, float, float | None]] = []
        self.texts: list[str] = []
        self.recipients: list[tuple[int, str]] = []
        self.markups: list[object] = []

    async def send_listing(self, alert, listing) -> None:
        self.listings.append(listing.item_id)

    async def send_price_change(self, alert, listing, old_price) -> None:
        self.price_changes.append(
            (listing.item_id, old_price, listing.price)
        )

    async def send_text(self, chat_id, text, reply_markup=None) -> None:
        self.texts.append(text)
        self.recipients.append((chat_id, text))
        self.markups.append(reply_markup)


@pytest.fixture
async def database(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.connect()
    yield db
    await db.close()


@pytest.fixture(autouse=True)
def sin_espera(monkeypatch):
    monkeypatch.setattr(scheduler_module, "SECONDS_BETWEEN_MESSAGES", 0)


async def create_alert(database: Database, **overrides) -> object:
    values = {
        "chat_id": 1,
        "name": "prueba",
        "platforms": ["wallapop"],
        "keywords": "k",
        "strict_keywords": False,
    }
    values.update(overrides)
    return await database.create_alert(NewAlert(**values))


async def test_primer_barrido_registra_sin_avisar(database):
    alert = await create_alert(database)
    source = FakeSource([make_listing("1"), make_listing("2")])
    notifier = FakeNotifier()
    tracker = Tracker(make_settings(), database, {"wallapop": source}, notifier)

    sent = await tracker.check_alert(alert)

    assert sent == 0
    assert notifier.listings == []
    assert await database.seen_count(alert.id) == 2

    source.listings = [make_listing("2"), make_listing("3")]
    sent = await tracker.check_alert(await database.get_alert(alert.id))

    assert sent == 1
    assert notifier.listings == ["3"]


async def test_primer_barrido_vacio_marca_la_alerta_como_sembrada(database):
    alert = await create_alert(database)
    source = FakeSource([])
    notifier = FakeNotifier()
    tracker = Tracker(make_settings(), database, {"wallapop": source}, notifier)

    assert await tracker.check_alert(alert) == 0
    stored = await database.get_alert(alert.id)
    assert stored.seeded is True

    source.listings = [make_listing("nuevo")]
    sent = await tracker.check_alert(stored)

    assert sent == 1
    assert notifier.listings == ["nuevo"]


async def test_notify_existing_avisa_en_el_primer_barrido(database):
    alert = await create_alert(database, notify_existing=True)
    source = FakeSource([make_listing("1")])
    notifier = FakeNotifier()
    tracker = Tracker(make_settings(), database, {"wallapop": source}, notifier)

    sent = await tracker.check_alert(alert)

    assert sent == 1
    assert notifier.listings == ["1"]


async def test_filtra_por_precio_y_exclusiones(database):
    alert = await create_alert(
        database,
        notify_existing=True,
        min_price=100,
        max_price=200,
        exclude_words="roto",
    )
    source = FakeSource(
        [
            make_listing("caro", price=500),
            make_listing("barato", price=50),
            make_listing("roto", price=150),
            make_listing("bueno", price=150),
        ]
    )
    notifier = FakeNotifier()
    tracker = Tracker(make_settings(), database, {"wallapop": source}, notifier)

    sent = await tracker.check_alert(alert)

    assert sent == 1
    assert notifier.listings == ["bueno"]


async def test_limita_avisos_y_resume_el_resto(database):
    alert = await create_alert(database, notify_existing=True)
    source = FakeSource([make_listing(str(i)) for i in range(5)])
    notifier = FakeNotifier()
    settings = make_settings(max_notifications_per_check=2)
    tracker = Tracker(settings, database, {"wallapop": source}, notifier)

    sent = await tracker.check_alert(alert)

    assert sent == 2
    assert notifier.listings == ["0", "1"]
    assert notifier.texts and "3 anuncios más" in notifier.texts[0]
    assert await database.seen_count(alert.id) == 5


async def test_baja_de_precio_avisa(database):
    alert = await create_alert(database)
    source = FakeSource([make_listing("1", price=100)])
    notifier = FakeNotifier()
    tracker = Tracker(make_settings(), database, {"wallapop": source}, notifier)

    await tracker.check_alert(alert)

    source.listings = [make_listing("1", price=80)]
    sent = await tracker.check_alert(await database.get_alert(alert.id))

    assert sent == 1
    assert notifier.listings == []
    assert notifier.price_changes == [("1", 100.0, 80.0)]
    prices = await database.get_seen_prices(alert.id, "wallapop", ["1"])
    assert prices["1"] == 80


async def test_subida_de_precio_avisa(database):
    alert = await create_alert(database)
    source = FakeSource([make_listing("1", price=100)])
    notifier = FakeNotifier()
    tracker = Tracker(make_settings(), database, {"wallapop": source}, notifier)

    await tracker.check_alert(alert)

    source.listings = [make_listing("1", price=120)]
    sent = await tracker.check_alert(await database.get_alert(alert.id))

    assert sent == 1
    assert notifier.price_changes == [("1", 100.0, 120.0)]
    prices = await database.get_seen_prices(alert.id, "wallapop", ["1"])
    assert prices["1"] == 120


async def test_mismo_precio_no_avisa(database):
    alert = await create_alert(database)
    source = FakeSource([make_listing("1", price=100)])
    notifier = FakeNotifier()
    tracker = Tracker(make_settings(), database, {"wallapop": source}, notifier)

    await tracker.check_alert(alert)
    sent = await tracker.check_alert(await database.get_alert(alert.id))

    assert sent == 0
    assert notifier.price_changes == []


async def test_precio_antiguo_sin_dato_se_rellena_sin_avisar(database):
    alert = await create_alert(database)
    await database.mark_seen(alert.id, "wallapop", "1")
    await database.update_alert(alert.id, seeded=True)

    source = FakeSource([make_listing("1", price=100)])
    notifier = FakeNotifier()
    tracker = Tracker(make_settings(), database, {"wallapop": source}, notifier)

    sent = await tracker.check_alert(await database.get_alert(alert.id))

    assert sent == 0
    assert notifier.price_changes == []
    prices = await database.get_seen_prices(alert.id, "wallapop", ["1"])
    assert prices["1"] == 100


async def test_limite_incluye_bajas_y_resume_el_resto(database):
    alert = await create_alert(database)
    source = FakeSource(
        [make_listing("1", price=100), make_listing("2", price=100)]
    )
    notifier = FakeNotifier()
    settings = make_settings(max_notifications_per_check=1)
    tracker = Tracker(settings, database, {"wallapop": source}, notifier)

    await tracker.check_alert(alert)

    source.listings = [
        make_listing("1", price=80),
        make_listing("2", price=70),
    ]
    sent = await tracker.check_alert(await database.get_alert(alert.id))

    assert sent == 1
    assert len(notifier.price_changes) == 1
    assert notifier.texts and "cambios de precio" in notifier.texts[0]
    prices = await database.get_seen_prices(
        alert.id, "wallapop", ["1", "2"]
    )
    assert prices == {"1": 80.0, "2": 70.0}


def test_next_midnight_es_la_siguiente_medianoche():
    now = datetime.now().astimezone().replace(
        hour=22, minute=30, second=0, microsecond=0
    )

    result = scheduler_module.next_midnight(now)

    assert result.hour == 0
    assert result.minute == 0
    assert result.date() == now.date() + timedelta(days=1)


async def test_aviso_diario_de_version(database, monkeypatch):
    notifier = FakeNotifier()
    tracker = Tracker(
        make_settings(admin_chat_ids=frozenset({1, 2})),
        database,
        {},
        notifier,
    )
    monkeypatch.setattr(
        scheduler_module, "fetch_remote_version", lambda: "0.1.999999"
    )
    now = datetime.now().astimezone().replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    assert await tracker._maybe_check_version(now=now) is True
    assert [chat for chat, _ in notifier.recipients] == [1, 2]
    assert "Actualización disponible" in notifier.texts[0]
    button = notifier.markups[0].inline_keyboard[0][0]
    assert button.callback_data == "upd:yes"
    assert (
        await database.get_state(scheduler_module.LAST_VERSION_CHECK_KEY)
        == now.date().isoformat()
    )

    # Mismo día: no repite aunque se reinicie.
    tracker._next_version_check = None
    notifier.texts.clear()
    notifier.recipients.clear()
    assert await tracker._maybe_check_version(now=now) is False
    assert notifier.texts == []

    # Al día siguiente vuelve a avisar.
    next_day = now + timedelta(days=1)
    assert await tracker._maybe_check_version(now=next_day) is True
    assert notifier.texts


async def test_sin_version_nueva_no_avisa(database, monkeypatch):
    notifier = FakeNotifier()
    tracker = Tracker(make_settings(), database, {}, notifier)
    monkeypatch.setattr(
        scheduler_module, "fetch_remote_version", lambda: "0.1.0"
    )
    now = datetime.now().astimezone()

    assert await tracker._maybe_check_version(now=now) is False
    assert notifier.texts == []


async def test_fallo_de_red_reintenta_en_una_hora(database, monkeypatch):
    def boom():
        raise OSError("sin red")

    notifier = FakeNotifier()
    tracker = Tracker(make_settings(), database, {}, notifier)
    monkeypatch.setattr(scheduler_module, "fetch_remote_version", boom)
    now = datetime.now().astimezone()

    assert await tracker._maybe_check_version(now=now) is False
    assert tracker._next_version_check == now + timedelta(
        seconds=scheduler_module.VERSION_RETRY_SECONDS
    )
    assert await database.get_state(
        scheduler_module.LAST_VERSION_CHECK_KEY
    ) is None
