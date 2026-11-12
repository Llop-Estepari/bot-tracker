"""Geocodificación de ciudades con Nominatim (OpenStreetMap)."""

from __future__ import annotations

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "bot-tracker/1.0 (alertas personales de anuncios)"


class GeocodeError(RuntimeError):
    """No se pudo resolver la ubicación."""


async def geocode(query: str, timeout: float = 15.0) -> tuple[float, float]:
    """Devuelve (latitud, longitud) para un nombre de lugar."""
    query = query.strip()
    if not query:
        raise GeocodeError("la ubicación está vacía")

    try:
        async with httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(
                NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": 1,
                    "addressdetails": 0,
                },
            )
    except httpx.HTTPError as exc:
        raise GeocodeError(f"error de red al buscar la ubicación: {exc}") from exc

    if response.status_code != 200:
        raise GeocodeError(
            f"el servicio de ubicaciones respondió HTTP {response.status_code}"
        )

    try:
        results = response.json()
    except ValueError as exc:
        raise GeocodeError("respuesta no válida del servicio de ubicaciones") from exc

    if not results:
        raise GeocodeError(f"no encontré la ubicación «{query}»")

    try:
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocodeError("respuesta incompleta del servicio de ubicaciones") from exc
