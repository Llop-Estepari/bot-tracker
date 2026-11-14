"""Tests de comprobación de versiones."""

from __future__ import annotations

import pytest

from updates import is_newer, parse_version


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.1.435464", (0, 1, 435464)),
        ("0.1.1", (0, 1, 1)),
        ("1.2.3", (1, 2, 3)),
    ],
)
def test_parse_version(raw, expected):
    assert parse_version(raw) == expected


@pytest.mark.parametrize("raw", ["", "0.1", "a.b.c", "0.1.2.3", "0.1.-1"])
def test_parse_version_invalida(raw):
    with pytest.raises(ValueError):
        parse_version(raw)


def test_is_newer():
    assert is_newer("0.1.435464", "0.1.435463") is True
    assert is_newer("0.1.435463", "0.1.435463") is False
    assert is_newer("0.1.2", "0.1.10") is False


def test_read_update_status(tmp_path):
    from updates import read_update_status

    status = tmp_path / "update-status"
    assert read_update_status(status) is None

    status.write_text("ok v0.1.435472\n", encoding="utf-8")
    assert read_update_status(status) == "ok v0.1.435472"

    status.write_text("   \n", encoding="utf-8")
    assert read_update_status(status) is None
