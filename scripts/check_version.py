#!/usr/bin/env python3
"""Verifica la coherencia de la versión y, opcionalmente, de un tag.

Uso:
    python scripts/check_version.py          # valida version.py y CHANGELOG.md
    python scripts/check_version.py v1.0.0   # además, comprueba el tag
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

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", nargs="?", help="tag esperado, por ejemplo v1.0.0")
    args = parser.parse_args(argv)

    errors: list[str] = []
    if not SEMVER_RE.fullmatch(__version__):
        errors.append(f"__version__ no es SemVer: {__version__!r}")

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
