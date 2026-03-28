from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ZugaLife standalone settings, loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ZugaLife"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8001
    database_url: str = "sqlite+aiosqlite:///data/zugalife.db"
    allowed_origins: list[str] = [
        "https://zugabot.ai",
        "http://localhost:5174",
        "http://localhost:5176",
        "http://192.168.1.200:5174",
        "http://192.168.1.200:5176",
    ]

    # AI providers
    venice_api_key: str = ""


settings = Settings()
