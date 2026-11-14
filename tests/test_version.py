from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from bot.handlers import format_status
from version import __release_date__, __version__

ROOT = Path(__file__).resolve().parent.parent


def test_version_sigue_el_esquema_build():
    assert re.fullmatch(r"0\.1\.\d+", __version__)


def test_version_coincide_con_build():
    build = (ROOT / "BUILD").read_text(encoding="utf-8").strip()

    assert __version__ == f"0.1.{build}"


def test_fecha_de_release_valida():
    assert date.fromisoformat(__release_date__)


def test_changelog_tiene_la_version_actual():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog


def test_estado_incluye_version_y_fecha():
    text = format_status(
        {"active_alerts": 1, "alerts": 2, "seen_items": 10},
        {"uptime_seconds": 65, "cooldowns": {}},
    )

    assert f"v{__version__}" in text
    assert __release_date__ in text
    assert "1 activas de 2" in text


def test_estado_incluye_enfriamientos():
    text = format_status(
        {"active_alerts": 0, "alerts": 0, "seen_items": 0},
        {"uptime_seconds": 0, "cooldowns": {"vinted": 120}},
    )

    assert "Vinted 120s" in text
