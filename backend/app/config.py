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
    )

    # AI Gateway API keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    moonshot_api_key: str = ""
    venice_api_key: str = ""

    # Budget
    daily_budget_limit: float = 10.0


settings = Settings()
