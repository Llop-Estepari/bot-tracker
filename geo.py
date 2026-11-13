"""Utilidades geográficas: distancias, coordenadas y países."""

from __future__ import annotations

import re
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088

SPAIN = "ES"

COUNTRY_NAMES = {
    "ES": "España",
    "PT": "Portugal",
    "IT": "Italia",
    "FR": "Francia",
    "DE": "Alemania",
    "GB": "Reino Unido",
    "IE": "Irlanda",
    "AD": "Andorra",
    "NL": "Países Bajos",
    "BE": "Bélgica",
    "LU": "Luxemburgo",
    "CH": "Suiza",
    "AT": "Austria",
    "PL": "Polonia",
    "SE": "Suecia",
    "DK": "Dinamarca",
    "NO": "Noruega",
    "FI": "Finlandia",
    "GR": "Grecia",
    "CZ": "Chequia",
    "SK": "Eslovaquia",
    "HU": "Hungría",
    "RO": "Rumanía",
    "US": "Estados Unidos",
    "MX": "México",
    "AR": "Argentina",
    "CO": "Colombia",
    "CL": "Chile",
    "BR": "Brasil",
}


def haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Distancia en kilómetros entre dos coordenadas (fórmula haversine)."""
    phi1, phi2 = radians(lat1), radians(lat2)
    delta_phi = radians(lat2 - lat1)
    delta_lambda = radians(lon2 - lon1)
    a = (
        sin(delta_phi / 2) ** 2
        + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(clamp(a)))


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """Limita un valor al intervalo indicado (errores de redondeo)."""
    return max(minimum, min(maximum, value))


def country_flag(code: str | None) -> str:
    """Emoji de bandera a partir del código ISO de dos letras."""
    normalized = (code or "").strip().upper()
    if len(normalized) != 2 or not normalized.isalpha():
        return ""
    return "".join(
        chr(0x1F1E6 + ord(char) - ord("A")) for char in normalized
    )


def country_label(code: str | None) -> str:
    """Nombre legible del país con bandera (o el código si no se conoce)."""
    normalized = (code or "").strip().upper()
    if not normalized:
        return ""
    name = COUNTRY_NAMES.get(normalized, normalized)
    flag = country_flag(normalized)
    return f"{flag} {name}".strip()


def is_outside_spain(code: str | None) -> bool:
    normalized = (code or "").strip().upper()
    return bool(normalized) and normalized != SPAIN


def format_distance(km: float) -> str:
    """Distancia corta y legible: '<1 km', '7,4 km', '32 km'."""
    if km < 1:
        return "<1 km"
    if km < 10:
        return f"{km:.1f} km".replace(".", ",")
    return f"{km:.0f} km"


def listing_distance_km(listing: object, alert: object | None) -> float | None:
    """Distancia entre el anuncio y el origen de la alerta, si se conoce."""
    if alert is None:
        return None
    origin_lat = getattr(alert, "origin_latitude", None)
    origin_lon = getattr(alert, "origin_longitude", None)
    item_lat = getattr(listing, "latitude", None)
    item_lon = getattr(listing, "longitude", None)
    if None in (origin_lat, origin_lon, item_lat, item_lon):
        return None
    return haversine_km(
        float(origin_lat),
        float(origin_lon),
        float(item_lat),
        float(item_lon),
    )


def parse_coordinates(raw: str) -> tuple[float, float]:
    """Interpreta '41.3874, 2.1686' (coma, punto y coma o espacios)."""
    text = (raw or "").strip()
    if ";" in text:
        parts = [part for part in text.split(";") if part.strip()]
    elif "," in text and len(text.split(",")) == 2:
        parts = [part for part in text.split(",") if part.strip()]
    else:
        parts = [part for part in re.split(r"\s+", text) if part]
    if len(parts) != 2:
        raise ValueError(
            "escribe las coordenadas como 41.3874, 2.1686"
            " (usa punto para los decimales)"
        )
    try:
        latitude = float(parts[0].replace(",", "."))
        longitude = float(parts[1].replace(",", "."))
    except ValueError as exc:
        raise ValueError("las coordenadas deben ser dos números") from exc
    if not -90 <= latitude <= 90:
        raise ValueError("la latitud debe estar entre -90 y 90")
    if not -180 <= longitude <= 180:
        raise ValueError("la longitud debe estar entre -180 y 180")
    return latitude, longitude
