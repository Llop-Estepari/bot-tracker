"""Tests de configuración de chats y administradores."""

from __future__ import annotations

import pytest

from config import Settings


def test_admin_usa_allowed_si_esta_vacio(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1,2")
    monkeypatch.delenv("ADMIN_CHAT_IDS", raising=False)

    settings = Settings.from_env()

    assert settings.effective_admin_chat_ids == frozenset({1, 2})


def test_admin_explicito(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1,2")
    monkeypatch.setenv("ADMIN_CHAT_IDS", "2")

    settings = Settings.from_env()

    assert settings.effective_admin_chat_ids == frozenset({2})


def test_admin_invalido(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ADMIN_CHAT_IDS", "no-es-un-id")

    with pytest.raises(ValueError):
        Settings.from_env()
