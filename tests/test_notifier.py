"""Tests de formato de los avisos de Telegram."""

from __future__ import annotations

from types import SimpleNamespace

from notifier import _build_markup, build_caption, build_price_change_caption
from sources.base import Listing


def make_listing(**overrides) -> Listing:
    values = {
        "source": "wallapop",
        "item_id": "1",
        "title": "PlayStation 5 <Slim>",
        "price": 300.0,
        "currency": "EUR",
        "url": "https://example.com/item",
        "location": "Madrid",
        "seller": "vendedor",
    }
    values.update(overrides)
    return Listing(**values)


def test_caption_sin_enlace_y_con_estilos():
    caption = build_caption(make_listing())

    assert "https://example.com/item" not in caption
    assert "href" not in caption
    assert "<b>PlayStation 5 &lt;Slim&gt;</b>" in caption
    assert "<i>Wallapop</i>" in caption
    assert "<i>Madrid</i>" in caption
    assert "<i>vendedor</i>" in caption


def test_caption_bajada_de_precio_con_porcentaje():
    caption = build_price_change_caption(make_listing(price=250.0), 300.0)

    assert "<s>300 €</s>" in caption
    assert "<b>250 €</b>" in caption
    assert "-17%" in caption
    assert "https://example.com/item" not in caption


def test_caption_marca_anuncios_fuera_de_espana():
    caption = build_caption(
        make_listing(location="Lisboa (Lisboa)", country_code="PT")
    )

    assert "Portugal" in caption
    assert "fuera de España" in caption
    assert "🇵🇹" in caption


def test_caption_no_marca_espana():
    caption = build_caption(make_listing(country_code="ES"))

    assert "fuera de España" not in caption


def test_caption_muestra_la_distancia_al_origen():
    alert = SimpleNamespace(origin_latitude=41.3874, origin_longitude=2.1686)
    caption = build_caption(
        make_listing(country_code="ES", latitude=41.40, longitude=2.17),
        alert,
    )

    assert "km" in caption
    assert "fuera de España" not in caption


def test_caption_sin_origen_no_muestra_distancia():
    alert = SimpleNamespace(origin_latitude=None, origin_longitude=None)
    caption = build_caption(
        make_listing(country_code="ES", latitude=41.40, longitude=2.17),
        alert,
    )

    assert "km" not in caption


def test_caption_muestra_vendedor_y_estrella():
    caption = build_caption(
        make_listing(seller="A3 A.", seller_rating=5.0)
    )

    assert "👤 <i>A3 A.</i> ⭐ 5,0" in caption
    assert "valoraciones" not in caption


def test_caption_muestra_nota_con_coma():
    caption = build_caption(
        make_listing(seller="djmir", seller_rating=4.9)
    )

    assert "⭐ 4,9" in caption


def test_boton_abrir_incluye_plataforma():
    alert = SimpleNamespace(id=1)
    wallapop = _build_markup(alert, make_listing())
    vinted = _build_markup(
        alert, make_listing(source="vinted", url="https://example.com/v")
    )

    assert wallapop.inline_keyboard[0][0].text == "🔗 Abrir en Wallapop"
    assert vinted.inline_keyboard[0][0].text == "🔗 Abrir en Vinted"
    texts = [
        button.text
        for row in wallapop.inline_keyboard
        for button in row
    ]
    assert all("Silenciar" not in text for text in texts)
