"""Helpers for service tests: a throwaway RSA key pair and token minting."""

from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def make_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public


def mint(private_pem: str, user_id: str, roles: list[str], name: str = "Test User") -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id,
            "name": name,
            "roles": roles,
            "typ": "access",
            "iss": "memorial-auth",
            "aud": "memorial",
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        private_pem,
        algorithm="RS256",
    )
