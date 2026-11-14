"""Configuración del bot cargada desde variables de entorno (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un número entero") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un número") from exc


def _parse_chat_ids(raw: str, name: str = "ALLOWED_CHAT_IDS") -> frozenset[int]:
    ids: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.add(int(chunk))
        except ValueError as exc:
            raise ValueError(
                f"{name} contiene un id no válido: {chunk!r}"
            ) from exc
    return frozenset(ids)


@dataclass(frozen=True)
class Settings:
    """Ajustes globales del bot."""

    telegram_bot_token: str
    allowed_chat_ids: frozenset[int]
    admin_chat_ids: frozenset[int]
    database_path: Path
    default_interval: int
    min_interval: int
    max_notifications_per_check: int
    seen_retention_days: int
    wallapop_base_url: str
    wallapop_api_base: str
    vinted_base_url: str
    vinted_locale: str
    request_timeout: float
    log_level: str

    @classmethod
    def from_env(cls) -> Settings:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError(
                "Falta TELEGRAM_BOT_TOKEN. Copia .env.example a .env y rellénalo."
            )

        database_path = Path(
            os.getenv("DATABASE_PATH") or PROJECT_DIR / "tracker.db"
        ).expanduser()

        min_interval = max(30, _env_int("MIN_INTERVAL_SECONDS", 60))
        default_interval = max(
            min_interval, _env_int("DEFAULT_INTERVAL_SECONDS", 90)
        )

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            log_level = "INFO"

        return cls(
            telegram_bot_token=token,
            allowed_chat_ids=_parse_chat_ids(
                os.getenv("ALLOWED_CHAT_IDS", "")
            ),
            admin_chat_ids=_parse_chat_ids(
                os.getenv("ADMIN_CHAT_IDS", ""), "ADMIN_CHAT_IDS"
            ),
            database_path=database_path,
            default_interval=default_interval,
            min_interval=min_interval,
            max_notifications_per_check=max(
                1, _env_int("MAX_NOTIFICATIONS_PER_CHECK", 15)
            ),
            seen_retention_days=max(1, _env_int("SEEN_RETENTION_DAYS", 60)),
            wallapop_base_url=os.getenv(
                "WALLAPOP_BASE_URL", "https://es.wallapop.com"
            ).rstrip("/"),
            wallapop_api_base=os.getenv(
                "WALLAPOP_API_BASE", "https://api.wallapop.com"
            ).rstrip("/"),
            vinted_base_url=os.getenv(
                "VINTED_BASE_URL", "https://www.vinted.es"
            ).rstrip("/"),
            vinted_locale=os.getenv("VINTED_LOCALE", "es-ES").strip() or "es-ES",
            request_timeout=_env_float("REQUEST_TIMEOUT_SECONDS", 25.0),
            log_level=log_level,
        )

    @property
    def effective_admin_chat_ids(self) -> frozenset[int]:
        """Administradores explícitos o, si no hay, los chats autorizados."""
        return self.admin_chat_ids or self.allowed_chat_ids
