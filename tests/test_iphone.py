"""Tests de la búsqueda de prueba /iphone."""

from __future__ import annotations

from types import SimpleNamespace

from bot.handlers import IPHONE_ALERT_NAME, build_iphone_alert


def test_build_iphone_alert_sin_restricciones():
    alert = build_iphone_alert(123, SimpleNamespace(min_interval=60))

    assert alert.chat_id == 123
    assert alert.name == IPHONE_ALERT_NAME
    assert alert.platforms == ["wallapop", "vinted"]
    assert alert.keywords == "iphone"
    assert alert.min_price is None
    assert alert.max_price is None
    assert alert.wallapop_shipping is False
    assert alert.radius_km is None
    assert alert.exclude_words == ""
    assert alert.strict_keywords is False
    assert alert.interval_seconds == 60
    assert alert.notify_existing is True
