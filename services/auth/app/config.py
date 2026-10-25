from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from memorial_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "auth"

    jwt_private_key: str | None = None
    jwt_private_key_file: str | None = None

    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 30
    invite_ttl_days: int = 14

    cookie_secure: bool = True
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    min_password_length: int = 10

    def private_key_pem(self) -> str:
        if self.jwt_private_key:
            return self.jwt_private_key
        if self.jwt_private_key_file and Path(self.jwt_private_key_file).is_file():
            return Path(self.jwt_private_key_file).read_text()
        raise RuntimeError("JWT private key is not configured (JWT_PRIVATE_KEY or JWT_PRIVATE_KEY_FILE).")

    def public_key_pem(self) -> str | None:
        explicit = super().public_key_pem()
        if explicit:
            return explicit
        try:
            key = serialization.load_pem_private_key(self.private_key_pem().encode(), password=None)
        except RuntimeError:
            return None
        return (
            key.public_key()
            .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            .decode()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
