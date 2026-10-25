import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from .config import Settings
from .models import User


def opaque_token() -> str:
    return secrets.token_urlsafe(48)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def access_token(settings: Settings, user: User) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user.id,
            "name": user.display_name,
            "roles": user.role_list,
            "typ": "access",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=settings.access_ttl_minutes),
            "jti": secrets.token_hex(8),
        },
        settings.private_key_pem(),
        algorithm="RS256",
    )
