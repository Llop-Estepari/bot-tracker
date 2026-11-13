"""Tests de las utilidades geográficas."""

from __future__ import annotations

import pytest

from geo import (
    country_label,
    format_distance,
    haversine_km,
    is_outside_spain,
    listing_distance_km,
    parse_coordinates,
)
from sources.base import Listing


def test_haversine_madrid_barcelona():
    distance = haversine_km(40.4168, -3.7038, 41.3874, 2.1686)

    assert 500 < distance < 510


def test_haversine_mismo_punto():
    assert haversine_km(41.3874, 2.1686, 41.3874, 2.1686) == pytest.approx(0)


def test_pais_fuera_de_espana():
    assert is_outside_spain("PT") is True
    assert is_outside_spain("pt") is True
    assert is_outside_spain("ES") is False
    assert is_outside_spain(None) is False


def test_country_label_con_bandera():
    label = country_label("PT")

    assert "Portugal" in label
    assert label.startswith("🇵🇹")


def test_country_label_desconocido_muestra_codigo():
    assert "JP" in country_label("JP")


@pytest.mark.parametrize(
    ("km", "expected"),
    [
        (0.4, "<1 km"),
        (7.42, "7,4 km"),
        (32.6, "33 km"),
    ],
)
def test_format_distance(km, expected):
    assert format_distance(km) == expected


@pytest.mark.parametrize(
    "raw", ["41.3874, 2.1686", "41.3874 2.1686", "41.3874;2.1686"]
)
def test_parse_coordinates(raw):
    latitude, longitude = parse_coordinates(raw)

    assert latitude == pytest.approx(41.3874)
    assert longitude == pytest.approx(2.1686)


@pytest.mark.parametrize("raw", ["", "41.3874", "91, 2", "41, 181"])
def test_parse_coordinates_invalidas(raw):
    with pytest.raises(ValueError):
        parse_coordinates(raw)


def test_listing_distance_km_sin_datos():
    listing = Listing(
        source="wallapop",
        item_id="1",
        title="x",
        price=1.0,
        currency="EUR",
        url="https://example.com",
    )
    assert listing_distance_km(listing, None) is None
