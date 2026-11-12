"""Tests del scheduler con fuentes y notificador simulados."""

from __future__ import annotations

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
        "database_path": Path("test.db"),
        "default_interval": 90,
        "min_interval": 60,
        "max_notifications_per_check": 15,
        "seen_retention_days": 60,
        "wallapop_base_url": "https://es.wallapop.com",
        "wallapop_api_base": "https://api.wallapop.com",
        "wallapop_proxy": None,
        "vinted_base_url": "https://www.vinted.es",
        "vinted_locale": "es-ES",
        "vinted_proxy": None,
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
        self.texts: list[str] = []

    async def send_listing(self, alert, listing) -> None:
        self.listings.append(listing.item_id)

    async def send_text(self, chat_id, text, reply_markup=None) -> None:
        self.texts.append(text)


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
