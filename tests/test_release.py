from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import release


def test_next_version_incrementa_el_build(tmp_path, monkeypatch):
    build_file = tmp_path / "BUILD"
    build_file.write_text("435463\n", encoding="utf-8")
    monkeypatch.setattr(release, "BUILD_FILE", build_file)

    assert release.next_version() == ("0.1.435464", 435464)


def test_read_build_invalido(tmp_path, monkeypatch):
    build_file = tmp_path / "BUILD"
    build_file.write_text("no-es-un-numero\n", encoding="utf-8")
    monkeypatch.setattr(release, "BUILD_FILE", build_file)

    with pytest.raises(release.ReleaseError):
        release.read_build()


def test_read_build_sin_fichero(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "BUILD_FILE", tmp_path / "BUILD")

    with pytest.raises(release.ReleaseError):
        release.read_build()


def test_insert_changelog_entry():
    changelog = (
        "# Changelog\n\n## [0.1.435464] - 2026-01-01\n\n- anterior\n"
    )
    entry = release.build_changelog_entry(
        "0.1.435465", "2026-11-14", "Arreglo"
    )

    result = release.insert_changelog_entry(changelog, entry)

    assert result.index("## [0.1.435465]") < result.index("## [0.1.435464]")
    assert "- Arreglo" in result


def test_update_version_file(tmp_path, monkeypatch):
    version_file = tmp_path / "version.py"
    version_file.write_text(
        '"""doc"""\n\n__version__ = "0.1.1"\n'
        '__release_date__ = "2026-01-01"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(release, "VERSION_FILE", version_file)

    release.update_version_file("0.1.435464", "2026-11-14")

    content = version_file.read_text(encoding="utf-8")
    assert '__version__ = "0.1.435464"' in content
    assert '__release_date__ = "2026-11-14"' in content
