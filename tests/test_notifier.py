"""Tests de formato de los avisos de Telegram."""

from __future__ import annotations

from notifier import build_caption, build_price_change_caption
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
