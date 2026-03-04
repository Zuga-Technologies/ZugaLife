from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ZugaLife standalone settings, loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "ZugaLife"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8001
    database_url: str = "sqlite+aiosqlite:///data/zugalife.db"
    allowed_origins: list[str] = ["http://localhost:5174"]


settings = Settings()
