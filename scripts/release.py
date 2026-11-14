#!/usr/bin/env python3
"""Publica una nueva build del bot.

El esquema de versión es ``0.1.<build>``: el prefijo ``0.1`` es fijo y el
último número es un contador que sube en cada publicación. No hay
major/minor/patch.

Uso:
    python scripts/release.py "Añade el comando /actualizar"
    python scripts/release.py --dry-run "Prueba sin publicar"
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "version.py"
BUILD_FILE = ROOT / "BUILD"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"

VERSION_RE = re.compile(r'__version__ = "([^"]+)"')
DATE_RE = re.compile(r'__release_date__ = "\d{4}-\d{2}-\d{2}"')
BUILD_RE = re.compile(r"^\d+$")
SCHEME = "0.1"


class ReleaseError(RuntimeError):
    """Error controlado del proceso de release."""


def read_build() -> int:
    if not BUILD_FILE.is_file():
        raise ReleaseError("no existe el fichero BUILD")
    raw = BUILD_FILE.read_text(encoding="utf-8").strip()
    if not BUILD_RE.fullmatch(raw):
        raise ReleaseError(f"BUILD no es un número: {raw!r}")
    return int(raw)


def write_build(build: int) -> None:
    BUILD_FILE.write_text(f"{build}\n", encoding="utf-8")


def next_version() -> tuple[str, int]:
    build = read_build() + 1
    return f"{SCHEME}.{build}", build


def read_version() -> str:
    content = VERSION_FILE.read_text(encoding="utf-8")
    match = VERSION_RE.search(content)
    if match is None:
        raise ReleaseError("no encuentro __version__ en version.py")
    return match.group(1)


def update_version_file(new_version: str, release_date: str) -> None:
    content = VERSION_FILE.read_text(encoding="utf-8")
    content = VERSION_RE.sub(f'__version__ = "{new_version}"', content, count=1)
    content = DATE_RE.sub(
        f'__release_date__ = "{release_date}"', content, count=1
    )
    VERSION_FILE.write_text(content, encoding="utf-8")


def build_changelog_entry(
    new_version: str, release_date: str, message: str
) -> str:
    return (
        f"## [{new_version}] - {release_date}\n\n"
        "### Cambios\n\n"
        f"- {message.strip()}\n"
    )


def insert_changelog_entry(changelog: str, entry: str) -> str:
    marker = re.search(r"^## \[", changelog, flags=re.MULTILINE)
    if marker is None:
        return changelog.rstrip() + "\n\n" + entry
    return changelog[: marker.start()] + entry + "\n" + changelog[marker.start() :]


def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def ensure_clean_tree() -> None:
    if run(["git", "status", "--porcelain"], capture=True):
        raise ReleaseError(
            "hay cambios sin commitear. Haz commit o descártalos antes de "
            "publicar una versión."
        )


def ensure_main_branch() -> None:
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True)
    if branch != "main":
        raise ReleaseError(f"debes estar en main (ahora: {branch})")


def tag_exists(tag: str) -> bool:
    output = run(["git", "tag", "--list", tag], capture=True)
    return bool(output)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publica una nueva build (0.1.N)."
    )
    parser.add_argument("message", nargs="+", help="descripción del cambio")
    parser.add_argument(
        "--dry-run", action="store_true", help="solo mostrar el resultado"
    )
    parser.add_argument(
        "--no-push", action="store_true", help="no empujar a GitHub"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    message = " ".join(args.message).strip()
    release_date = date.today().isoformat()

    try:
        ensure_main_branch()
        ensure_clean_tree()
        current = read_version()
        new_version, new_build = next_version()
        tag = f"v{new_version}"
        if tag_exists(tag):
            raise ReleaseError(f"el tag {tag} ya existe")

        entry = build_changelog_entry(new_version, release_date, message)
        if args.dry_run:
            print(f"versión actual: {current}")
            print(f"nueva versión : {new_version} (build {new_build})")
            print()
            print(entry, end="")
            return 0

        print(f"==> Actualizando versión {current} -> {new_version}")
        original = {
            VERSION_FILE: VERSION_FILE.read_text(encoding="utf-8"),
            BUILD_FILE: BUILD_FILE.read_text(encoding="utf-8"),
            CHANGELOG_FILE: CHANGELOG_FILE.read_text(encoding="utf-8"),
        }
        update_version_file(new_version, release_date)
        write_build(new_build)
        changelog = CHANGELOG_FILE.read_text(encoding="utf-8")
        CHANGELOG_FILE.write_text(
            insert_changelog_entry(changelog, entry), encoding="utf-8"
        )

        try:
            print("==> Comprobando lint y tests")
            run([sys.executable, "-m", "ruff", "check", "."])
            run([sys.executable, "-m", "pytest", "-q"])
        except subprocess.CalledProcessError:
            for path, content in original.items():
                path.write_text(content, encoding="utf-8")
            print("↩️  Cambios de versión revertidos", file=sys.stderr)
            raise

        print("==> Creando commit y tag")
        run(["git", "add", "version.py", "BUILD", "CHANGELOG.md"])
        run(["git", "commit", "-m", f"release: {tag} — {message}"])
        run(["git", "tag", "-a", tag, "-m", f"{tag} — {message}"])

        if args.no_push:
            print(f"✅ {tag} creado en local (sin push).")
        else:
            print("==> Empujando a GitHub")
            run(["git", "push", "origin", "main"])
            run(["git", "push", "origin", tag])
            print(f"✅ {tag} publicado.")
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
