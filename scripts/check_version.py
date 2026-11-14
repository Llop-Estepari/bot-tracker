#!/usr/bin/env python3
"""Verifica la coherencia de la versión y, opcionalmente, de un tag.

El esquema es ``0.1.<build>``, donde ``<build>`` coincide con el fichero
``BUILD``.

Uso:
    python scripts/check_version.py          # valida version.py y CHANGELOG.md
    python scripts/check_version.py v0.1.42  # además, comprueba el tag
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from version import __release_date__, __version__

VERSION_RE = re.compile(r"^0\.1\.(\d+)$")
BUILD_RE = re.compile(r"^(\d+)$")


def read_build() -> int:
    raw = (ROOT / "BUILD").read_text(encoding="utf-8").strip()
    match = BUILD_RE.fullmatch(raw)
    if match is None:
        raise ValueError(f"BUILD no es un número: {raw!r}")
    return int(match.group(1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", nargs="?", help="tag esperado, por ejemplo v0.1.42")
    args = parser.parse_args(argv)

    errors: list[str] = []
    match = VERSION_RE.fullmatch(__version__)
    if match is None:
        errors.append(f"__version__ no sigue el esquema 0.1.N: {__version__!r}")

    try:
        build = read_build()
    except (OSError, ValueError) as exc:
        build = None
        errors.append(str(exc))

    if (
        match is not None
        and build is not None
        and int(match.group(1)) != build
    ):
        errors.append(
            f"version.py ({__version__}) no coincide con BUILD ({build})"
        )

    try:
        date.fromisoformat(__release_date__)
    except ValueError:
        errors.append(
            f"__release_date__ no es una fecha ISO: {__release_date__!r}"
        )

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{__version__}]" not in changelog:
        errors.append(f"CHANGELOG.md no tiene entrada para {__version__}")

    if args.tag:
        expected = f"v{__version__}"
        if args.tag != expected:
            errors.append(f"el tag {args.tag!r} no coincide con {expected!r}")

    if errors:
        for error in errors:
            print(f"❌ {error}", file=sys.stderr)
        return 1

    print(f"✅ v{__version__} ({__release_date__}) coherente")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
