from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from memorial_common.security import ALL_ROLES


def _roles(v: list[str]) -> list[str]:
    clean = sorted({r.strip().lower() for r in v})
    bad = [r for r in clean if r not in ALL_ROLES]
    if bad:
        raise ValueError(f"Unknown role: {', '.join(bad)}")
    if not clean:
        raise ValueError("Choose at least one role.")
    return clean


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    roles: list[str]
    is_active: bool
    last_login_at: datetime | None = None


class InviteIn(BaseModel):
    email: EmailStr
    display_name: str = Field(default="", max_length=120)
    roles: list[str] = Field(default_factory=lambda: ["editor"])

    _v = field_validator("roles")(_roles)


class InviteOut(BaseModel):
    id: str
    email: str
    display_name: str
    roles: list[str]
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    invite_url: str | None = None


class AcceptIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(max_length=256)


class InviteInfoOut(BaseModel):
    email: str
    display_name: str
    roles: list[str]


class UserPatch(BaseModel):
    roles: list[str] | None = None
    is_active: bool | None = None

    @field_validator("roles")
    @classmethod
    def _v(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _roles(v)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)
