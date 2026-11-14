"""Tests de formato de fechas y duraciones."""

from __future__ import annotations

from datetime import timedelta, timezone

from bot.handlers import format_age, format_local_time


def test_format_local_time_convierte_desde_utc():
    madrid = timezone(timedelta(hours=1))

    assert (
        format_local_time("2026-11-14T17:16:00+00:00", madrid)
        == "14/11/2026 18:16:00"
    )
    assert (
        format_local_time("2026-11-14T17:16:00", madrid)
        == "14/11/2026 18:16:00"
    )


def test_format_local_time_valores_especiales():
    assert format_local_time(None) == "nunca"
    assert format_local_time("no-es-una-fecha") == "no-es-una-fecha"


def test_format_age():
    assert format_age(0) == "0s"
    assert format_age(45) == "45s"
    assert format_age(120) == "2m"
    assert format_age(3600) == "1h"
    assert format_age(3900) == "1h 5m"
    assert format_age(90000) == "1d 1h"


def make_alert(**overrides):
    from db import Alert

    values = {
        "id": 1,
        "chat_id": 1,
        "name": "prueba",
        "platforms": ["wallapop"],
        "keywords": "iphone",
        "min_price": None,
        "max_price": None,
        "wallapop_category_id": None,
        "wallapop_shipping": True,
        "vinted_catalog_ids": [],
        "vinted_brand_ids": [],
        "vinted_condition_ids": [],
        "exclude_words": "",
        "strict_keywords": False,
        "interval_seconds": 60,
        "notify_existing": False,
        "seeded": True,
        "active": True,
        "created_at": "2026-01-01T00:00:00+00:00",
        "last_checked_at": None,
    }
    values.update(overrides)
    return Alert(**values)


def test_format_alert_muestra_error_del_ultimo_intento():
    from bot.handlers import format_alert

    alert = make_alert(
        last_checked_at="2026-11-14T17:16:00+00:00",
        last_check_ok=False,
        last_check_error="sin red",
    )

    text = format_alert(alert)

    assert "último intento" in text
    assert "falló: sin red" in text


def test_format_alert_muestra_comprobacion_correcta():
    from bot.handlers import format_alert

    alert = make_alert(
        last_checked_at="2026-11-14T17:16:00+00:00",
        last_check_ok=True,
    )

    text = format_alert(alert)

    assert "última comprobación correcta" in text
    assert "falló" not in text
