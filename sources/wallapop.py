"""Cliente de la API interna de Wallapop.

Usa `httpx` por defecto (verificado: la API responde sin impersonación TLS) y
recurre a `curl_cffi` solo si CloudFront devuelve 403. Así funciona en Termux
sin dependencias nativas y mantiene el fallback en servidores con IP vigilada.
"""

from __future__ import annotations

import logging
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

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _load_async_session():
    """Devuelve AsyncSession de curl_cffi si está instalado; si no, None."""
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        return None
    return AsyncSession


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
            )
        )
    return listings


class WallapopSource:
    name = "wallapop"

    def __init__(
        self,
        api_base: str,
        web_base: str,
        proxy: str | None = None,
        timeout: float = 25.0,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._web_base = web_base.rstrip("/")
        self._proxy = proxy
        self._timeout = timeout
        client_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "follow_redirects": True,
            "headers": {"User-Agent": USER_AGENT},
        }
        if proxy:
            client_kwargs["proxy"] = proxy
        self._client = httpx.AsyncClient(**client_kwargs)
        self._cffi_session = None
        self._headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "es-ES,es;q=0.9",
            "Origin": self._web_base,
            "Referer": f"{self._web_base}/",
            "X-DeviceOS": "0",
        }

    @staticmethod
    def _build_params(alert: Alert) -> dict[str, Any]:
        params: dict[str, Any] = {
            "keywords": alert.keywords,
            "step": 1,
            "source": "keywords",
            "order_by": "newest",
            "limit": 40,
        }
        if alert.latitude is not None and alert.longitude is not None:
            params["latitude"] = alert.latitude
            params["longitude"] = alert.longitude
            if alert.radius_km:
                params["distance_in_km"] = alert.radius_km
        if alert.min_price is not None:
            params["min_sale_price"] = alert.min_price
        if alert.max_price is not None:
            params["max_sale_price"] = alert.max_price
        if alert.wallapop_category_id:
            params["category_id"] = alert.wallapop_category_id
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

        if response.status_code == 403:
            logger.info("Wallapop devolvió 403 con httpx; probando curl_cffi")
            payload = await self._search_with_curl_cffi(params)
        else:
            payload = self._parse_response(response)

        return parse_search(payload, self._web_base)

    async def _search_with_curl_cffi(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        if self._cffi_session is None:
            async_session = _load_async_session()
            if async_session is None:
                raise BlockedError(
                    "Wallapop bloqueó la petición (403) y curl_cffi no está"
                    " instalado. Instálalo con `pip install curl_cffi` o"
                    " configura WALLAPOP_PROXY."
                )
            self._cffi_session = async_session(
                impersonate="chrome", timeout=self._timeout, max_clients=4
            )
        try:
            response = await self._cffi_session.get(
                f"{self._api_base}/api/v3/search",
                params=params,
                headers=self._headers,
                proxy=self._proxy,
            )
        except Exception as exc:
            raise SourceError(f"Error de red en Wallapop: {exc}") from exc
        return self._parse_response(response)

    def _parse_response(self, response: Any) -> dict[str, Any]:
        if response.status_code == 429:
            raise RateLimitError("Wallapop está limitando las peticiones (429)")
        if response.status_code in (401, 403):
            raise BlockedError(
                "Wallapop bloqueó la petición (403). Si el bot corre en un"
                " servidor, configura WALLAPOP_PROXY con un proxy residencial."
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
        if self._cffi_session is not None:
            await self._cffi_session.close()
