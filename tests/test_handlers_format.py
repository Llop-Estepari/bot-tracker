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
