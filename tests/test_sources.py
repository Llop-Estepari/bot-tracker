"""Tests de parseo de respuestas reales de las plataformas."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

from sources.vinted import build_api_base
from sources.vinted import parse_search as parse_vinted
from sources.wallapop import parse_search as parse_wallapop

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_wallapop_parsea_anuncios():
    listings = parse_wallapop(
        load("wallapop_search.json"), "https://es.wallapop.com"
    )

    assert len(listings) == 2
    first = listings[0]
    assert first.source == "wallapop"
    assert first.item_id
    assert first.title
    assert first.price is not None
    assert first.currency == "EUR"
    assert first.url.startswith("https://es.wallapop.com/item/")
    assert first.photo_url is not None
    assert first.photo_url.startswith("https://")
    assert first.created_at is not None
    assert first.created_at.tzinfo == UTC


def test_vinted_parsea_anuncios():
    listings = parse_vinted(
        load("vinted_search.json"), "https://www.vinted.es"
    )

    assert len(listings) == 2
    first = listings[0]
    assert first.source == "vinted"
    assert first.item_id
    assert first.title
    assert first.price is not None
    assert first.currency == "EUR"
    assert first.url.startswith("https://www.vinted.es/items/")
    assert first.photo_url is not None
    assert first.seller


def test_vinted_construye_api_base():
    assert build_api_base("https://www.vinted.es") == "https://api.vinted.es"
    assert build_api_base("https://vinted.fr") == "https://api.vinted.fr"


def test_wallapop_ignora_items_incompletos():
    payload = {"data": {"section": {"payload": {"items": [{"id": "x", "title": "t"}]}}}}
    listings = parse_wallapop(payload, "https://es.wallapop.com")
    assert len(listings) == 1
    assert listings[0].price is None
    assert listings[0].url == "https://es.wallapop.com/item/x"
