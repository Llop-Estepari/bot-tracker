"""Tipos e interfaz comunes de las fuentes de anuncios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from db import Alert


class SourceError(RuntimeError):
    """Error genérico al consultar una plataforma."""


class RateLimitError(SourceError):
    """La plataforma está limitando las peticiones (HTTP 429)."""


class BlockedError(SourceError):
    """La plataforma está bloqueando las peticiones (HTTP 401/403)."""


@dataclass(frozen=True)
class Listing:
    """Anuncio normalizado, independiente de la plataforma."""

    source: str
    item_id: str
    title: str
    price: float | None
    currency: str
    url: str
    photo_url: str | None = None
    location: str | None = None
    seller: str | None = None
    description: str | None = None
    created_at: datetime | None = None


class Source(Protocol):
    """Interfaz que implementan las fuentes de Wallapop y Vinted."""

    name: str

    async def search(self, alert: Alert) -> list[Listing]:
        """Devuelve los anuncios más recientes que encajan con la alerta."""

    async def close(self) -> None:
        """Libera recursos de red."""


def as_price(value: object) -> float | None:
    """Convierte precios de las APIs (float, int o str) a float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(" ", "").replace("€", "")
        if not cleaned:
            return None
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None
