"""Tests de los filtros de cliente."""

from __future__ import annotations

import pytest

from db import Alert
from filters import format_price, matches, normalize, parse_price, parse_price_range
from sources.base import Listing


def make_alert(**overrides) -> Alert:
    values = {
        "id": 1,
        "chat_id": 1,
        "name": "prueba",
        "platforms": ["wallapop"],
        "keywords": "ps5",
        "min_price": None,
        "max_price": None,
        "latitude": None,
        "longitude": None,
        "radius_km": None,
        "wallapop_category_id": None,
        "vinted_catalog_ids": [],
        "vinted_brand_ids": [],
        "vinted_condition_ids": [],
        "exclude_words": "",
        "strict_keywords": False,
        "interval_seconds": 90,
        "notify_existing": False,
        "seeded": False,
        "active": True,
        "created_at": "2026-01-01T00:00:00+00:00",
        "last_checked_at": None,
    }
    values.update(overrides)
    return Alert(**values)


def make_listing(**overrides) -> Listing:
    values = {
        "source": "wallapop",
        "item_id": "1",
        "title": "PlayStation 5",
        "price": 300.0,
        "currency": "EUR",
        "url": "https://example.com/item",
    }
    values.update(overrides)
    return Listing(**values)


def test_normalize_quita_acentos_y_mayusculas():
    assert normalize("  Bicicleta ELÉCTRICA  ") == "bicicleta electrica"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("100", 100.0),
        ("1.234,56 €", 1234.56),
        ("1234.56", 1234.56),
        ("1.234", 1234.0),
        ("12,5", 12.5),
        ("", None),
    ],
)
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("100-400", (100.0, 400.0)),
        ("100 - 400", (100.0, 400.0)),
        ("100-", (100.0, None)),
        ("-400", (None, 400.0)),
        ("100", (None, 100.0)),
        ("-", (None, None)),
        ("", (None, None)),
        ("1.000-2.500", (1000.0, 2500.0)),
    ],
)
def test_parse_price_range(raw, expected):
    assert parse_price_range(raw) == expected


def test_parse_price_range_rechaza_rango_invertido():
    with pytest.raises(ValueError):
        parse_price_range("400-100")


def test_format_price():
    assert format_price(100) == "100 €"
    assert format_price(99.5) == "99,50 €"
    assert format_price(None) == ""


def test_matches_sin_filtros():
    assert matches(make_listing(), make_alert()) is True


def test_matches_precio_minimo_y_maximo():
    alert = make_alert(min_price=100, max_price=200)
    assert matches(make_listing(price=150), alert) is True
    assert matches(make_listing(price=99.99), alert) is False
    assert matches(make_listing(price=200.01), alert) is False


def test_matches_precio_desconocido_con_filtro():
    alert = make_alert(max_price=500)
    assert matches(make_listing(price=None), alert) is False


def test_modo_estricto_exige_palabra_clave_en_el_titulo():
    alert = make_alert(strict_keywords=True, keywords="playstation 5")
    assert matches(make_listing(title="PlayStation 5 Slim"), alert) is True
    assert matches(make_listing(title="Comando personalizado GTA6"), alert) is False
    # Limitación conocida: las siglas solas no coinciden con el nombre completo.
    assert matches(make_listing(title="PS5 digital"), alert) is False


def test_modo_estricto_se_desactiva():
    alert = make_alert(strict_keywords=False, keywords="playstation 5")
    assert matches(make_listing(title="Comando personalizado GTA6"), alert) is True


def test_matches_palabras_excluidas_sin_acentos():
    alert = make_alert(exclude_words="roto, para piezas")
    assert matches(make_listing(title="PS5 impecable"), alert) is True
    assert matches(make_listing(title="PS5 ROTO"), alert) is False
    assert matches(make_listing(title="PS5", description="vendo para piezas"), alert) is False
