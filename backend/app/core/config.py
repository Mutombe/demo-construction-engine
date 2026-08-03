from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "development"
    database_url: str = "postgresql+psycopg://erp:erp@localhost:5432/construction_erp"
    test_database_url: str = "postgresql+psycopg://erp:erp@localhost:5432/construction_erp_test"
    jwt_secret: str = "dev-secret-do-not-use-in-production"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    cors_origins: list[str] = ["http://localhost:5173"]
    anthropic_api_key: str | None = None
    media_root: str = "media"


settings = Settings()
