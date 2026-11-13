"""Filtros de texto y precio que se aplican en cliente."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from geo import haversine_km

if TYPE_CHECKING:
    from db import Alert
    from sources.base import Listing


def normalize(text: str) -> str:
    """Minúsculas, sin acentos y con espacios colapsados."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.lower()).strip()


def parse_price(raw: str) -> float | None:
    """Convierte '1.234,56 €' o '1234.56' en 1234.56."""
    cleaned = (
        str(raw)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("€", "")
        .replace("eur", "")
    )
    if not cleaned:
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cleaned):
        cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except ValueError as exc:
        raise ValueError(f"precio no válido: {raw!r}") from exc


def parse_price_range(raw: str) -> tuple[float | None, float | None]:
    """Interpreta '100-400', '100-', '-400', '100' o '-'."""
    text = (raw or "").strip().replace("–", "-").replace("—", "-")
    if text.lower() in {"", "-", "sin filtro", "ninguno", "nada"}:
        return None, None
    if text.startswith("-"):
        return None, parse_price(text[1:])
    if text.endswith("-"):
        return parse_price(text[:-1]), None
    if "-" not in text:
        # Un único número se interpreta como precio máximo.
        return None, parse_price(text)
    minimum_raw, maximum_raw = text.split("-", 1)
    minimum = parse_price(minimum_raw) if minimum_raw.strip() else None
    maximum = parse_price(maximum_raw) if maximum_raw.strip() else None
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("el precio mínimo no puede ser mayor que el máximo")
    return minimum, maximum


def format_price(value: float | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return f"{int(value)} €"
    return f"{value:.2f} €".replace(".", ",")


MAX_RADIUS_KM = 500


def parse_distance(raw: str) -> int | None:
    """Interpreta '25', '25 km', 'todo' o '-' (None = sin límite)."""
    text = normalize(raw).replace("km", "").strip()
    if text in {
        "",
        "-",
        "0",
        "todo",
        "todos",
        "todas",
        "sin limite",
        "sin limites",
        "sinlimite",
        "ninguno",
    }:
        return None
    if text.startswith("-") and text != "-":
        raise ValueError(
            "usa un número de km (1-500) o 'todo' para sin límite"
        )
    try:
        value = round(float(text.replace(",", ".")))
    except ValueError as exc:
        raise ValueError(
            "usa un número de km (1-500) o 'todo' para sin límite"
        ) from exc
    if value <= 0:
        return None
    if value > MAX_RADIUS_KM:
        raise ValueError(f"el radio máximo es {MAX_RADIUS_KM} km")
    return value


def split_words(raw: str) -> list[str]:
    """Separa palabras/frases por comas, punto y coma o saltos de línea."""
    return [
        part.strip()
        for part in re.split(r"[,;\n]", raw or "")
        if part.strip()
    ]


def keyword_tokens(keywords: str) -> list[str]:
    """Divide las palabras clave en tokens sin acentos ni mayúsculas."""
    return [token for token in re.split(r"[\s,;]+", normalize(keywords)) if token]


def matches(listing: Listing, alert: Alert) -> bool:
    """Comprueba precio, distancia, modo estricto y palabras excluidas."""
    if alert.min_price is not None or alert.max_price is not None:
        if listing.price is None:
            return False
        if alert.min_price is not None and listing.price < alert.min_price - 0.001:
            return False
        if alert.max_price is not None and listing.price > alert.max_price + 0.001:
            return False

    # La distancia solo existe en Wallapop. Se comprueba también en local por
    # si la API ignorara el parámetro o devolviera algo fuera del radio.
    if (
        listing.source == "wallapop"
        and alert.radius_km is not None
        and alert.origin_latitude is not None
        and alert.origin_longitude is not None
        and listing.latitude is not None
        and listing.longitude is not None
    ):
        distance = haversine_km(
            alert.origin_latitude,
            alert.origin_longitude,
            listing.latitude,
            listing.longitude,
        )
        if distance > alert.radius_km:
            return False

    if alert.strict_keywords and alert.keywords.strip():
        tokens = keyword_tokens(alert.keywords)
        meaningful = [token for token in tokens if len(token) >= 3] or tokens
        if meaningful:
            title = normalize(listing.title)
            if not any(token in title for token in meaningful):
                return False

    excluded = [normalize(word) for word in split_words(alert.exclude_words)]
    excluded = [word for word in excluded if word]
    if excluded:
        haystack = normalize(f"{listing.title} {listing.description or ''}")
        for word in excluded:
            if word in haystack:
                return False

    return True
