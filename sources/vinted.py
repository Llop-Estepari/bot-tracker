"""Cliente de la API interna de Vinted (endpoint svc-catalogue)."""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

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

DISPLAY_NAME = "Vinted"
SELLER_CACHE_SECONDS = 24 * 60 * 60

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def build_api_base(base_url: str) -> str:
    """https://www.vinted.es -> https://api.vinted.es"""
    parsed = urlsplit(base_url)
    host = parsed.hostname or "www.vinted.es"
    host = host.removeprefix("www.")
    return f"https://api.{host}"


def parse_search(payload: dict[str, Any], base_url: str) -> list[Listing]:
    """Convierte la respuesta de /svc-catalogue/items en Listings."""
    items = payload.get("items") or []
    base_url = base_url.rstrip("/")

    listings: list[Listing] = []
    for item in items:
        try:
            item_id = str(item["id"])
        except (KeyError, TypeError):
            continue

        price_data = item.get("price") or {}
        price = as_price(price_data.get("amount"))
        currency = price_data.get("currency_code") or "EUR"

        photo = item.get("photo") or {}
        photo_url = photo.get("url") or photo.get("full_size_url")

        path = item.get("url") or ""
        url = path if path.startswith("http") else f"{base_url}{path}"

        user = item.get("user") or {}
        user_id = user.get("id")

        listings.append(
            Listing(
                source="vinted",
                item_id=item_id,
                title=(item.get("title") or "").strip(),
                price=price,
                currency=currency,
                url=url,
                photo_url=photo_url,
                seller=user.get("login"),
                seller_id=str(user_id) if user_id not in (None, "") else None,
            )
        )
    return listings


def parse_seller_user(payload: dict[str, Any]) -> tuple[str | None, float | None]:
    """Devuelve (login, nota sobre 5) del vendedor de Vinted."""
    user = payload.get("user") or payload
    login = user.get("login")
    name = str(login).strip() if login else None
    feedback_count = int(user.get("feedback_count") or 0)
    reputation = user.get("feedback_reputation")
    rating: float | None = None
    if feedback_count > 0 and isinstance(reputation, (int, float)):
        rating = round(float(reputation) * 5, 1)
    return name, rating


class VintedSource:
    name = "vinted"

    def __init__(
        self,
        base_url: str,
        locale: str = "es-ES",
        timeout: float = 25.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_base = build_api_base(self._base_url)
        self._locale = locale
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        self._session_ready = False
        self._api_headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.6",
            "Platform": "web",
            "x-next-app": "marketplace-web",
            "Locale": locale,
            "Origin": self._base_url,
            "Referer": f"{self._base_url}/",
        }
        self._seller_cache: dict[
            str, tuple[str | None, float | None, float]
        ] = {}

    def _has_token(self) -> bool:
        return any(
            cookie.name == "access_token_web"
            for cookie in self._client.cookies.jar
        )

    async def _ensure_session(self, force: bool = False) -> None:
        """Vinted exige cookies de sesión; se obtienen visitando la web."""
        if not force and self._session_ready and self._has_token():
            return
        if force:
            self._client.cookies.clear()
        try:
            response = await self._client.get(self._base_url)
        except httpx.HTTPError as exc:
            raise SourceError(f"Error de red al abrir Vinted: {exc}") from exc
        if response.status_code >= 400:
            raise SourceError(
                f"Vinted respondió HTTP {response.status_code} al abrir la web"
            )
        self._session_ready = True
        if not self._has_token():
            logger.warning(
                "Vinted no entregó access_token_web; se intentará igualmente"
            )

    async def search(self, alert: Alert) -> list[Listing]:
        await self._ensure_session()

        params: dict[str, Any] = {
            "search_text": alert.keywords,
            "page": 1,
            "per_page": 24,
            "order": "newest_first",
        }
        if alert.min_price is not None:
            params["price_from"] = alert.min_price
        if alert.max_price is not None:
            params["price_to"] = alert.max_price
        if alert.vinted_catalog_ids:
            params["attribute_ids[catalog]"] = ",".join(
                str(v) for v in alert.vinted_catalog_ids
            )
        if alert.vinted_brand_ids:
            params["attribute_ids[brand]"] = ",".join(
                str(v) for v in alert.vinted_brand_ids
            )
        if alert.vinted_condition_ids:
            params["attribute_ids[status]"] = ",".join(
                str(v) for v in alert.vinted_condition_ids
            )

        for attempt in (1, 2):
            try:
                response = await self._client.get(
                    f"{self._api_base}/svc-catalogue/items",
                    params=params,
                    headers=self._api_headers,
                )
            except httpx.HTTPError as exc:
                raise SourceError(f"Error de red en Vinted: {exc}") from exc

            if response.status_code in (401, 403):
                if attempt == 1:
                    logger.info("Sesión de Vinted caducada; renovando cookies")
                    await self._ensure_session(force=True)
                    continue
                raise BlockedError(
                    "Vinted bloqueó la petición (401/403) tras renovar la sesión."
                )
            if response.status_code == 429:
                raise RateLimitError("Vinted está limitando las peticiones (429)")
            if response.status_code != 200:
                raise SourceError(
                    f"Vinted respondió HTTP {response.status_code}"
                )
            break

        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceError("Vinted devolvió una respuesta no JSON") from exc
        if not isinstance(payload, dict) or "items" not in payload:
            raise SourceError("Formato inesperado en la respuesta de Vinted")

        return parse_search(payload, self._base_url)

    async def enrich(self, listing: Listing) -> Listing:
        """Completa el nombre y la valoración del vendedor (caché 24 h)."""
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
            await self._ensure_session()
            for attempt in (1, 2):
                response = await self._client.get(
                    f"{self._base_url}/api/v2/users/{user_id}",
                    headers=self._api_headers,
                )
                if response.status_code in (401, 403) and attempt == 1:
                    await self._ensure_session(force=True)
                    continue
                break
            if response.status_code == 200:
                name, rating = parse_seller_user(response.json())
        except (httpx.HTTPError, SourceError, ValueError):
            logger.warning(
                "No se pudo obtener el vendedor %s de Vinted", user_id
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

    async def close(self) -> None:
        await self._client.aclose()
