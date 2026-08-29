from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Local-only configuration. No paid/cloud service credentials belong here."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://foodguard:foodguard@localhost:5433/foodguard"
    SECRET_KEY: str = "dev-only-secret-change-me"
    DEBUG: bool = True
    MODEL_PATH: str = "./models"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    TESSERACT_CMD: str = "/opt/homebrew/bin/tesseract"

    JWT_ALGORITHM: str = "HS256"


@lru_cache
def get_settings() -> Settings:
    return Settings()
