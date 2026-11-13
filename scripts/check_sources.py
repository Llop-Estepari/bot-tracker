"""Comprueba que Wallapop y Vinted responden desde esta red.

Uso (desde la raíz del proyecto):
    .venv/bin/python scripts/check_sources.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import Settings
from db import Alert
from sources import VintedSource, WallapopSource


def make_alert() -> Alert:
    return Alert(
        id=0,
        chat_id=0,
        name="check",
        platforms=["wallapop", "vinted"],
        keywords="playstation 5",
        min_price=100,
        max_price=400,
        wallapop_category_id=None,
        wallapop_shipping=True,
        vinted_catalog_ids=[],
        vinted_brand_ids=[],
        vinted_condition_ids=[],
        exclude_words="",
        strict_keywords=True,
        interval_seconds=90,
        notify_existing=False,
        notify_price_changes=True,
        seeded=True,
        active=True,
        created_at="",
        last_checked_at=None,
    )


async def main() -> int:
    settings = Settings.from_env()
    alert = make_alert()
    sources = {
        "wallapop": WallapopSource(
            settings.wallapop_api_base,
            settings.wallapop_base_url,
            settings.request_timeout,
        ),
        "vinted": VintedSource(
            settings.vinted_base_url,
            settings.vinted_locale,
            settings.request_timeout,
        ),
    }

    failures = 0
    for name, source in sources.items():
        try:
            listings = await source.search(alert)
        except Exception as exc:  # noqa: BLE001 - diagnóstico puntual
            failures += 1
            print(f"{name}: ERROR -> {type(exc).__name__}: {exc}")
        else:
            print(f"{name}: OK -> {len(listings)} resultados")
            for listing in listings[:2]:
                print(
                    f"  - {listing.title[:60]} | {listing.price} EUR | {listing.url}"
                )
        finally:
            await source.close()

    print("RESULTADO:", "OK" if failures == 0 else f"{failures} fallo(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
