"""Telegram 适配器 Token 来源：配置优先，留空时读环境变量（Keychain 唯一副本）。"""

import pytest

from src.plugins.built_in.telegram_adapter.settings import TOKEN_ENV, TelegramSettings


def test_env_token_used_when_config_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV, "env-token")
    settings = TelegramSettings(bot_token="")
    assert settings.resolved_bot_token == "env-token"
    assert settings.bot_token == ""


def test_configured_token_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV, "env-token")
    settings = TelegramSettings(bot_token="config-token")
    assert settings.resolved_bot_token == "config-token"


def test_blank_config_without_env_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    assert TelegramSettings(bot_token="   ").resolved_bot_token == ""


def test_whitespace_config_still_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV, "  env-token  ")
    assert TelegramSettings(bot_token="  ").resolved_bot_token == "env-token"
