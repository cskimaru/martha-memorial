"""Verifying access tokens issued by the auth service.

Only the auth service holds the private signing key. Every other service
verifies tokens with the public key, so a compromised service cannot mint
tokens.
"""

from dataclasses import dataclass, field

import jwt
from fastapi import Depends, HTTPException, Request, status

ACCESS_COOKIE = "mm_access"
REFRESH_COOKIE = "mm_refresh"

ROLE_OWNER = "owner"
ROLE_EDITOR = "editor"
ROLE_TREASURER = "treasurer"
ALL_ROLES = frozenset({ROLE_OWNER, ROLE_EDITOR, ROLE_TREASURER})


@dataclass(frozen=True)
class Principal:
    user_id: str
    name: str
    roles: frozenset[str] = field(default_factory=frozenset)

    def has(self, *roles: str) -> bool:
        return ROLE_OWNER in self.roles or any(r in self.roles for r in roles)


class TokenVerifier:
    def __init__(self, public_key_pem: str | None, issuer: str, audience: str) -> None:
        self.public_key_pem = public_key_pem
        self.issuer = issuer
        self.audience = audience

    def verify(self, token: str) -> Principal | None:
        if not self.public_key_pem:
            return None
        try:
            claims = jwt.decode(
                token,
                self.public_key_pem,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except jwt.PyJWTError:
            return None
        if claims.get("typ") != "access":
            return None
        roles = frozenset(r for r in claims.get("roles", []) if r in ALL_ROLES)
        return Principal(user_id=str(claims["sub"]), name=str(claims.get("name", "")), roles=roles)


def token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(ACCESS_COOKIE)


def optional_principal(request: Request) -> Principal | None:
    verifier: TokenVerifier | None = getattr(request.app.state, "verifier", None)
    token = token_from_request(request)
    if not verifier or not token:
        return None
    return verifier.verify(token)


def current_principal(principal: Principal | None = Depends(optional_principal)) -> Principal:
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    return principal


def require_roles(*roles: str):
    def dep(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.has(*roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account doesn't have permission for this.")
        return principal

    return dep
