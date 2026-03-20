"""Application settings via pydantic-settings."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./kya_dev.db"
    REDIS_URL: str = "redis://localhost:6379"
    OPA_URL: str = "http://localhost:8181"
    JWT_PRIVATE_KEY_PATH: str = "./keys/private.pem"
    JWT_PUBLIC_KEY_PATH: str = "./keys/public.pem"
    JWT_ALGORITHM: str = "EdDSA"
    JWT_ISSUER: str = "kya-platform"
    JWT_EXPIRY_SECONDS: int = 3600
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    # In-memory mode: skip Redis/OPA when not available
    USE_INMEMORY_CACHE: bool = True
    USE_BUILTIN_POLICY: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
