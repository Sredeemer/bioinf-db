"""Application settings and environment configuration."""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for UbuntuBio Hub."""

    model_config = SettingsConfigDict(
        env_prefix="UBUNTUBIO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General & Service Identity
    ENV: str = "development"
    DEBUG: bool = True
    APP_NAME: str = "UbuntuBio Hub"
    API_URL: str = "http://localhost:8000"
    WEB_URL: str = "http://localhost:3000"
    CAS_URL: str = "http://localhost:8080"

    # Logging Configuration
    LOG_LEVEL: str = Field(
        default="INFO",
        validation_alias=AliasChoices("UBUNTUBIO_LOG_LEVEL", "LOG_LEVEL"),
    )
    LOG_FORMAT: str = Field(
        default="json",
        validation_alias=AliasChoices("UBUNTUBIO_LOG_FORMAT", "LOG_FORMAT"),
    )

    DATA_ROOT: Path = Path("/srv/ubuntubio/data")
    GIT_ROOT: Path = Path("/srv/ubuntubio/data/git")
    TMP_ROOT: Path = Path("/srv/ubuntubio/data/tmp")

    # Embedded Database & Search (Single File: ubuntubio.db)
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./.data/ubuntubio.db",
        validation_alias=AliasChoices("UBUNTUBIO_DATABASE_URL", "DATABASE_URL"),
    )

    # Optional / Legacy service endpoints
    VALKEY_URL: str = Field(
        default="",
        validation_alias=AliasChoices("UBUNTUBIO_VALKEY_URL", "VALKEY_URL"),
    )
    MEILI_URL: str = "http://localhost:7700"
    MEILI_MASTER_KEY: str = "ubuntubio_meili_master_key_dev_only"

    # Security & CAS Tokens
    JWT_SECRET: str = "dev_insecure_jwt_secret_change_in_production"
    CAS_TOKEN_AUDIENCE: str = "openxet"
    CAS_TOKEN_LIFETIME_SECONDS: int = 900  # 15 minutes

    # ORCID OAuth2 (Default Sandbox)
    ORCID_CLIENT_ID: str = "APP-0000000000000000"
    ORCID_CLIENT_SECRET: str = "dev_orcid_secret"
    ORCID_BASE_URL: str = "https://sandbox.orcid.org"
    ORCID_TOKEN_URL: str = "https://sandbox.orcid.org/oauth/token"
    ORCID_AUTHORIZE_URL: str = "https://sandbox.orcid.org/oauth/authorize"


settings = Settings()
