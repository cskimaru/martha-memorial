"""Settings shared by every service.

Values come from environment variables. Secrets can also be mounted as files
under /run/secrets (Docker secrets), named after the setting, e.g.
/run/secrets/database_url.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETS_DIR = "/run/secrets"


def _secrets_dir() -> str | None:
    return SECRETS_DIR if Path(SECRETS_DIR).is_dir() else None


class CommonSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", secrets_dir=_secrets_dir())

    service_name: str = "service"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "sqlite+aiosqlite:///./dev.db"
    redis_url: str | None = None

    # Public origin of the site, e.g. https://martha.example.com. Used for the
    # cross-site request check on cookie-authenticated writes.
    site_origin: str = "http://localhost:8080"

    jwt_public_key: str | None = None
    jwt_public_key_file: str | None = None
    jwt_issuer: str = "memorial-auth"
    jwt_audience: str = "memorial"

    # Salt for hashing client IPs before they are stored (never store raw IPs).
    ip_hash_salt: str = "change-me"

    @field_validator("site_origin")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def public_key_pem(self) -> str | None:
        if self.jwt_public_key:
            return self.jwt_public_key
        if self.jwt_public_key_file and Path(self.jwt_public_key_file).is_file():
            return Path(self.jwt_public_key_file).read_text()
        return None


@lru_cache
def get_common_settings() -> CommonSettings:
    return CommonSettings()
