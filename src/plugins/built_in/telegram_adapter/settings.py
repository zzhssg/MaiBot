from typing import ClassVar

import os

from maibot_sdk import Field, PluginConfigBase

TOKEN_ENV = "TELEGRAM_BOT_TOKEN"


class PluginSettings(PluginConfigBase):
    __ui_label__: ClassVar[str] = "插件"
    __ui_order__: ClassVar[int] = 0

    enabled: bool = Field(default=False, description="启用 Telegram 机器人连接")
    config_version: str = Field(default="0.1.0", description="配置版本")


class TelegramSettings(PluginConfigBase):
    __ui_label__: ClassVar[str] = "Telegram"
    __ui_order__: ClassVar[int] = 1

    bot_token: str = Field(
        default="",
        repr=False,
        description=f"BotFather 签发的机器人 Token；留空时读取环境变量 {TOKEN_ENV}",
        json_schema_extra={"x-widget": "password"},
    )
    api_base_url: str = Field(default="https://api.telegram.org", description="Bot API 地址，可使用本地 Bot API 服务")
    proxy_url: str = Field(
        default="",
        repr=False,
        description="HTTP/SOCKS5 代理地址；留空直连，不读取环境代理",
        json_schema_extra={"x-widget": "password"},
    )
    poll_timeout_sec: int = Field(default=30, ge=1, le=50, description="长轮询等待时间（秒）")
    reconnect_delay_sec: float = Field(default=5, ge=1, le=300, description="网络故障后重试间隔（秒）")
    max_download_mb: int = Field(
        default=20, ge=1, le=50, description="单个媒体下载上限（MB）；云端 Bot API 下载上限为 20 MB"
    )
    media_timeout_sec: int = Field(default=60, ge=10, le=300, description="媒体转换超时（秒）")

    @property
    def resolved_bot_token(self) -> str:
        """配置优先；配置留空时读环境变量，让 Keychain 保存唯一一份 Token。"""
        return self.bot_token.strip() or os.environ.get(TOKEN_ENV, "").strip()


class AdapterSettings(PluginConfigBase):
    plugin: PluginSettings = Field(default_factory=PluginSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
