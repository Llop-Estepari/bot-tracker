"""Comprobación de la última versión publicada en GitHub."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.request import urlopen

REMOTE_VERSION_URL = (
    "https://raw.githubusercontent.com/Llop-Estepari/bot-tracker"
    "/main/version.py"
)
VERSION_RE = re.compile(r'__version__ = "([^"]+)"')


def parse_version(raw: str) -> tuple[int, int, int]:
    """Convierte '0.1.435464' en una tupla comparable."""
    parts = (raw or "").strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"versión no válida: {raw!r}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def is_newer(remote: str, current: str) -> bool:
    """True si la versión remota es posterior a la instalada."""
    return parse_version(remote) > parse_version(current)


def fetch_remote_version(timeout: float = 10.0) -> str:
    """Lee version.py de la rama main del repositorio público."""
    with urlopen(REMOTE_VERSION_URL, timeout=timeout) as response:
        content = response.read().decode("utf-8", errors="replace")
    match = VERSION_RE.search(content)
    if match is None:
        raise ValueError("no se encontró __version__ en el remoto")
    version = match.group(1).strip()
    parse_version(version)
    return version


def read_update_status(path: Path) -> str | None:
    """Lee el estado dejado por self-update.sh, si existe."""
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return value or None
