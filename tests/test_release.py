from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import release


@pytest.mark.parametrize(
    ("current", "part", "expected"),
    [
        ("1.0.0", "patch", "1.0.1"),
        ("1.0.0", "minor", "1.1.0"),
        ("1.0.0", "major", "2.0.0"),
        ("1.9.9", "patch", "1.9.10"),
        ("2.3.4", "minor", "2.4.0"),
    ],
)
def test_bump_version(current, part, expected):
    assert release.bump_version(current, part) == expected


def test_bump_version_invalida():
    with pytest.raises(release.ReleaseError):
        release.bump_version("1.0", "patch")


def test_insert_changelog_entry():
    changelog = "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n- anterior\n"
    entry = release.build_changelog_entry("1.0.1", "2026-11-12", "Arreglo")

    result = release.insert_changelog_entry(changelog, entry)

    assert result.index("## [1.0.1]") < result.index("## [1.0.0]")
    assert "- Arreglo" in result


def test_update_version_file(tmp_path, monkeypatch):
    version_file = tmp_path / "version.py"
    version_file.write_text(
        '"""doc"""\n\n__version__ = "1.0.0"\n'
        '__release_date__ = "2026-01-01"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(release, "VERSION_FILE", version_file)

    release.update_version_file("1.2.3", "2026-11-12")

    content = version_file.read_text(encoding="utf-8")
    assert '__version__ = "1.2.3"' in content
    assert '__release_date__ = "2026-11-12"' in content
