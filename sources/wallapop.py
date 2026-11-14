"""Cliente de la API interna de Wallapop."""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from sources.base import (
    BlockedError,
    Listing,
    RateLimitError,
    SourceError,
    as_price,
)

if TYPE_CHECKING:
    from db import Alert

logger = logging.getLogger(__name__)

DISPLAY_NAME = "Wallapop"
SELLER_CACHE_SECONDS = 24 * 60 * 60

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def as_float(value: object) -> float | None:
    """Convierte coordenadas de la API (float, int o str) a float."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def parse_seller_user(payload: dict[str, Any]) -> str | None:
    """Nombre público del vendedor (micro_name)."""
    name = payload.get("micro_name")
    return str(name).strip() or None if name else None


def parse_seller_rating(payload: dict[str, Any]) -> float | None:
    """Nota media sobre 5, solo si el vendedor tiene valoraciones."""
    reviews = 0
    for counter in payload.get("counters") or []:
        if counter.get("type") == "reviews":
            reviews = int(counter.get("value") or 0)
            break
    rating = as_float(payload.get("rating_average"))
    if rating is None or reviews <= 0:
        return None
    return round(rating, 1)


def parse_search(payload: dict[str, Any], web_base: str) -> list[Listing]:
    """Convierte la respuesta de /api/v3/search en Listings."""
    section = payload.get("data", {}).get("section") or {}
    items = (section.get("payload") or {}).get("items") or []

    listings: list[Listing] = []
    for item in items:
        try:
            item_id = str(item["id"])
        except (KeyError, TypeError):
            continue
        user_id = item.get("user_id")
        seller_id = str(user_id) if user_id not in (None, "") else None

        price_data = item.get("price") or {}
        price = as_price(price_data.get("amount"))
        currency = price_data.get("currency") or "EUR"

        images = item.get("images") or []
        photo_url = None
        if images:
            urls = images[0].get("urls") or {}
            photo_url = urls.get("medium") or urls.get("big") or urls.get("small")

        location_data = item.get("location") or {}
        city = location_data.get("city")
        region = location_data.get("region")
        if city and region and region != city:
            location = f"{city} ({region})"
        else:
            location = city or region
        country_code = (
            str(location_data.get("country_code") or "").strip().upper() or None
        )
        latitude = as_float(location_data.get("latitude"))
        longitude = as_float(location_data.get("longitude"))

        created_at = None
        timestamp = item.get("created_at")
        if isinstance(timestamp, (int, float)):
            created_at = datetime.fromtimestamp(timestamp / 1000, tz=UTC)

        web_slug = item.get("web_slug") or ""
        url = (
            f"{web_base}/item/{web_slug}"
            if web_slug
            else f"{web_base}/item/{item_id}"
        )

        listings.append(
            Listing(
                source="wallapop",
                item_id=item_id,
                title=(item.get("title") or "").strip(),
                price=price,
                currency=currency,
                url=url,
                photo_url=photo_url,
                location=location,
                description=item.get("description"),
                created_at=created_at,
                country_code=country_code,
                latitude=latitude,
                longitude=longitude,
                seller_id=seller_id,
            )
        )
    return listings


class WallapopSource:
    name = "wallapop"

    def __init__(
        self,
        api_base: str,
        web_base: str,
        timeout: float = 25.0,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._web_base = web_base.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        self._headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "es-ES,es;q=0.9",
            "Origin": self._web_base,
            "Referer": f"{self._web_base}/",
            "X-DeviceOS": "0",
        }
        self._seller_cache: dict[
            str, tuple[str | None, float | None, float]
        ] = {}

    @staticmethod
    def _build_params(alert: Alert) -> dict[str, Any]:
        params: dict[str, Any] = {
            "keywords": alert.keywords,
            "step": 1,
            "source": "keywords",
            "order_by": "newest",
            "limit": 40,
        }
        if alert.min_price is not None:
            params["min_sale_price"] = alert.min_price
        if alert.max_price is not None:
            params["max_sale_price"] = alert.max_price
        if alert.wallapop_category_id:
            params["category_id"] = alert.wallapop_category_id
        if alert.wallapop_shipping:
            params["is_shippable"] = True
        if (
            alert.radius_km is not None
            and alert.origin_latitude is not None
            and alert.origin_longitude is not None
        ):
            params["latitude"] = alert.origin_latitude
            params["longitude"] = alert.origin_longitude
            params["distance_in_km"] = alert.radius_km
        return params

    async def search(self, alert: Alert) -> list[Listing]:
        params = self._build_params(alert)
        try:
            response = await self._client.get(
                f"{self._api_base}/api/v3/search",
                params=params,
                headers=self._headers,
            )
        except httpx.HTTPError as exc:
            raise SourceError(f"Error de red en Wallapop: {exc}") from exc

        return parse_search(self._parse_response(response), self._web_base)

    async def enrich(self, listing: Listing) -> Listing:
        """Completa nombre y valoración del vendedor con caché de 24 h."""
        if not listing.seller_id:
            return listing

        now = time.monotonic()
        cached = self._seller_cache.get(listing.seller_id)
        if cached is not None and now - cached[2] < SELLER_CACHE_SECONDS:
            name, rating, _ = cached
            return replace(
                listing,
                seller=listing.seller if listing.seller else name,
                seller_rating=(
                    listing.seller_rating
                    if listing.seller_rating is not None
                    else rating
                ),
            )

        name: str | None = None
        rating: float | None = None
        user_id = listing.seller_id
        try:
            user_response = await self._client.get(
                f"{self._api_base}/api/v3/users/{user_id}",
                headers=self._headers,
            )
            if user_response.status_code == 200:
                name = parse_seller_user(user_response.json())

            stats_response = await self._client.get(
                f"{self._api_base}/api/v3/users/{user_id}/stats",
                headers=self._headers,
            )
            if stats_response.status_code == 200:
                rating = parse_seller_rating(stats_response.json())
        except (httpx.HTTPError, ValueError):
            logger.warning(
                "No se pudo obtener el vendedor %s de Wallapop", user_id
            )

        self._seller_cache[user_id] = (name, rating, now)
        return replace(
            listing,
            seller=listing.seller if listing.seller else name,
            seller_rating=(
                listing.seller_rating
                if listing.seller_rating is not None
                else rating
            ),
        )

    def _parse_response(self, response: Any) -> dict[str, Any]:
        if response.status_code == 429:
            raise RateLimitError("Wallapop está limitando las peticiones (429)")
        if response.status_code in (401, 403):
            raise BlockedError(
                "Wallapop bloqueó la petición (403). Inténtalo más tarde."
            )
        if response.status_code != 200:
            raise SourceError(f"Wallapop respondió HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceError("Wallapop devolvió una respuesta no JSON") from exc
        if not isinstance(payload, dict):
            raise SourceError("Formato inesperado en la respuesta de Wallapop")
        return payload

    async def close(self) -> None:
        await self._client.aclose()
