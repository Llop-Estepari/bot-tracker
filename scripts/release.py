#!/usr/bin/env python3
"""Sube la versión, actualiza el changelog y crea el tag de release.

Uso:
    python scripts/release.py patch "Corrige el filtrado de palabras"
    python scripts/release.py minor "Añade el comando /version"
    python scripts/release.py major "Rompe el formato de configuración"
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
CHANGELOG_FILE = ROOT / "CHANGELOG.md"

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
VERSION_RE = re.compile(r'__version__ = "(\d+\.\d+\.\d+)"')
DATE_RE = re.compile(r'__release_date__ = "\d{4}-\d{2}-\d{2}"')


class ReleaseError(RuntimeError):
    """Error controlado del proceso de release."""


def bump_version(version: str, part: str) -> str:
    match = SEMVER_RE.fullmatch(version)
    if not match:
        raise ReleaseError(f"versión actual no válida: {version!r}")
    major, minor, patch = (int(value) for value in match.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ReleaseError(f"tipo de subida no válido: {part!r}")


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
        description="Sube la versión y crea el tag de release."
    )
    parser.add_argument("bump", choices=["patch", "minor", "major"])
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
        new_version = bump_version(current, args.bump)
        tag = f"v{new_version}"
        if tag_exists(tag):
            raise ReleaseError(f"el tag {tag} ya existe")

        entry = build_changelog_entry(new_version, release_date, message)
        if args.dry_run:
            print(f"versión actual: {current}")
            print(f"nueva versión : {new_version}")
            print()
            print(entry, end="")
            return 0

        print("==> Comprobando lint y tests")
        run([sys.executable, "-m", "ruff", "check", "."])
        run([sys.executable, "-m", "pytest", "-q"])

        print(f"==> Actualizando versión {current} -> {new_version}")
        update_version_file(new_version, release_date)
        changelog = CHANGELOG_FILE.read_text(encoding="utf-8")
        CHANGELOG_FILE.write_text(
            insert_changelog_entry(changelog, entry), encoding="utf-8"
        )

        print("==> Creando commit y tag")
        run(["git", "add", "version.py", "CHANGELOG.md"])
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
