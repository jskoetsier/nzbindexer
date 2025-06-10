import secrets
from typing import Any, Dict, List, Optional, Union

from pydantic import AnyHttpUrl, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Version information
VERSION = "0.8.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "NZBIndexer"

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days

    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "nzbindexer"
    SQLALCHEMY_DATABASE_URI: Optional[PostgresDsn] = None

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=values.data.get("POSTGRES_USER"),
            password=values.data.get("POSTGRES_PASSWORD"),
            host=values.data.get("POSTGRES_SERVER"),
            path=f"{values.data.get('POSTGRES_DB') or ''}",
        )

    # NNTP Settings
    NNTP_SERVER: str = ""
    NNTP_PORT: int = 119
    NNTP_SSL: bool = False
    NNTP_SSL_PORT: int = 563
    NNTP_USERNAME: str = ""
    NNTP_PASSWORD: str = ""

    # Redis settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # Celery settings
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # File storage
    COVERS_DIR: str = "data/covers"
    SAMPLES_DIR: str = "data/samples"
    NZB_DIR: str = "data/nzb"

    # External APIs
    TMDB_API_KEY: str = ""
    TVDB_API_KEY: str = ""
    TVMAZE_API_KEY: str = ""
    OMDB_API_KEY: str = ""

    # Indexer settings
    UPDATE_THREADS: int = 1
    RELEASES_THREADS: int = 1
    POSTPROCESS_THREADS: int = 1
    BACKFILL_DAYS: int = 3
    RETENTION_DAYS: int = 1100

    # Web interface settings
    ITEMS_PER_PAGE: int = 50
    LATEST_RELEASES_LIMIT: int = 8

    # Email settings
    EMAILS_ENABLED: bool = False
    SMTP_TLS: bool = True
    SMTP_PORT: Optional[int] = None
    SMTP_HOST: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: Optional[str] = None
    EMAILS_FROM_NAME: Optional[str] = None


settings = Settings()
