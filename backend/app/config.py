"""ZugaLife standalone config bridge.

Providers import `from app.config import settings`. In ZugaApp, this resolves
to ZugaApp's config. In ZugaLife standalone, this file provides the same
interface with the settings ZugaLife needs (API keys, budget limit).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings for AI gateway when running in ZugaLife standalone mode."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # AI Gateway API keys
    openai_api_key: str = ""
    venice_api_key: str = ""

    # TTS provider key — when set, meditation module uses Cartesia voices
    # (see meditation/routes.py _use_cartesia gate at L285 + L601). When empty,
    # falls back to OpenAI TTS transparently. Required declaration: pydantic-
    # settings uses extra="ignore", so an env var for an undeclared field is
    # silently dropped — meaning Cartesia would never activate even if the
    # env var is set. Previous ZugaLife meditations (pre-2026-04-19) all
    # rendered via OpenAI because this field was missing.
    cartesia_api_key: str = ""


settings = Settings()
