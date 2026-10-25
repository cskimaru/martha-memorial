import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from memorial_common.db import aware, new_id, utcnow
from memorial_common.logging import log_fields
from memorial_common.ratelimit import client_ip, hash_value, rate_limit
from memorial_common.security import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    ROLE_OWNER,
    Principal,
    current_principal,
    require_roles,
)

from .config import Settings
from .models import AuditLog, Invitation, RefreshToken, User
from .passwords import hash_password, needs_rehash, verify_password
from .schemas import (
    AcceptIn,
    InviteIn,
    InviteInfoOut,
    InviteOut,
    LoginIn,
    PasswordChangeIn,
    UserOut,
    UserPatch,
)
from .tokens import access_token, opaque_token, sha256

router = APIRouter(prefix="/api/auth")
log = logging.getLogger("auth")


def settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def session_dep(request: Request):
    async for s in request.app.state.db.session():
        yield s


def user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        roles=u.role_list,
        is_active=u.is_active,
        last_login_at=u.last_login_at,
    )


def audit(s: AsyncSession, request: Request, actor: str | None, action: str, target: str = "", detail: str = ""):
    salt = request.app.state.settings.ip_hash_salt
    s.add(
        AuditLog(
            actor_id=actor,
            action=action,
            target=target,
            detail=(detail + f" ip={hash_value(client_ip(request), salt)[:12]}").strip(),
        )
    )


def check_password_strength(pw: str, settings: Settings, email: str = "") -> None:
    if len(pw) < settings.min_password_length:
        raise HTTPException(422, f"Use a password of at least {settings.min_password_length} characters.")
    if email and email.split("@")[0].lower() in pw.lower():
        raise HTTPException(422, "Your password shouldn't contain your email address.")
    if len(set(pw)) < 5:
        raise HTTPException(422, "That password is too easy to guess. Try a short phrase.")


async def issue_session(
    s: AsyncSession, response: Response, request: Request, settings: Settings, user: User, family_id: str | None = None
) -> None:
    raw = opaque_token()
    s.add(
        RefreshToken(
            user_id=user.id,
            token_hash=sha256(raw),
            family_id=family_id or new_id(),
            expires_at=utcnow() + timedelta(days=settings.refresh_ttl_days),
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": "strict"}
    response.set_cookie(
        ACCESS_COOKIE, access_token(settings, user), max_age=settings.access_ttl_minutes * 60, path="/", **common
    )
    response.set_cookie(REFRESH_COOKIE, raw, max_age=settings.refresh_ttl_days * 86400, path="/api/auth", **common)


def clear_cookies(response: Response, settings: Settings) -> None:
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": "strict"}
    response.delete_cookie(ACCESS_COOKIE, path="/", **common)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth", **common)


@router.post("/login", response_model=UserOut, dependencies=[Depends(rate_limit("login", 10, 300))])
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    s: AsyncSession = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> UserOut:
    email = body.email.lower()
    user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
    now = utcnow()
    generic = HTTPException(status.HTTP_401_UNAUTHORIZED, "That email and password don't match an account.")

    if user and aware(user.locked_until) and aware(user.locked_until) > now:
        verify_password(None, body.password)  # keep timing uniform
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Too many failed attempts. Try again in {settings.lockout_minutes} minutes.",
        )

    ok = verify_password(user.password_hash if user else None, body.password)
    if not user or not ok or not user.is_active:
        if user:
            user.failed_logins += 1
            if user.failed_logins >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_logins = 0
                audit(s, request, user.id, "login.locked", user.email)
            audit(s, request, user.id, "login.failed", user.email)
            await s.commit()
        log_fields(log, logging.WARNING, "login failed")
        raise generic

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    await issue_session(s, response, request, settings, user)
    audit(s, request, user.id, "login.ok", user.email)
    await s.commit()
    return user_out(user)


@router.post("/refresh", response_model=UserOut, dependencies=[Depends(rate_limit("refresh", 60, 300))])
async def refresh(
    request: Request,
    response: Response,
    s: AsyncSession = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> UserOut:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(401, "Sign in to continue.")
    tok = (await s.execute(select(RefreshToken).where(RefreshToken.token_hash == sha256(raw)))).scalar_one_or_none()
    now = utcnow()
    if not tok or aware(tok.expires_at) <= now:
        clear_cookies(response, settings)
        raise HTTPException(401, "Your session has ended. Please sign in again.")
    if tok.revoked_at is not None:
        # A rotated token was used again: likely stolen. End every session in this chain.
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == tok.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        audit(s, request, tok.user_id, "refresh.reuse_detected")
        await s.commit()
        clear_cookies(response, settings)
        raise HTTPException(401, "Your session has ended. Please sign in again.")
    user = await s.get(User, tok.user_id)
    if not user or not user.is_active:
        tok.revoked_at = now
        await s.commit()
        clear_cookies(response, settings)
        raise HTTPException(401, "Your session has ended. Please sign in again.")
    tok.revoked_at = now
    await issue_session(s, response, request, settings, user, family_id=tok.family_id)
    await s.commit()
    return user_out(user)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    s: AsyncSession = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> Response:
    response = Response(status_code=204)
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        tok = (await s.execute(select(RefreshToken).where(RefreshToken.token_hash == sha256(raw)))).scalar_one_or_none()
        if tok and tok.revoked_at is None:
            await s.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == tok.family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
            await s.commit()
    clear_cookies(response, settings)
    return response


@router.get("/me", response_model=UserOut)
async def me(p: Principal = Depends(current_principal), s: AsyncSession = Depends(session_dep)) -> UserOut:
    user = await s.get(User, p.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Sign in to continue.")
    return user_out(user)


@router.post("/password", status_code=204, dependencies=[Depends(rate_limit("password", 10, 900))])
async def change_password(
    body: PasswordChangeIn,
    request: Request,
    p: Principal = Depends(current_principal),
    s: AsyncSession = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> Response:
    user = await s.get(User, p.user_id)
    if not user or not verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, "Your current password is incorrect.")
    check_password_strength(body.new_password, settings, user.email)
    user.password_hash = hash_password(body.new_password)
    await s.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    audit(s, request, user.id, "password.changed")
    await s.commit()
    return Response(status_code=204)


# ---- Invitations (owner only) ----


def invite_out(inv: Invitation, url: str | None = None) -> InviteOut:
    return InviteOut(
        id=inv.id,
        email=inv.email,
        display_name=inv.display_name,
        roles=[r for r in inv.roles.split(",") if r],
        expires_at=inv.expires_at,
        accepted_at=inv.accepted_at,
        revoked_at=inv.revoked_at,
        invite_url=url,
    )


@router.post("/invitations", response_model=InviteOut, status_code=201)
async def create_invitation(
    body: InviteIn,
    request: Request,
    p: Principal = Depends(require_roles(ROLE_OWNER)),
    s: AsyncSession = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> InviteOut:
    email = body.email.lower()
    if (await s.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "Someone with that email already has an account.")
    raw = opaque_token()
    inv = Invitation(
        email=email,
        display_name=body.display_name.strip(),
        roles=",".join(body.roles),
        token_hash=sha256(raw),
        invited_by=p.user_id,
        expires_at=utcnow() + timedelta(days=settings.invite_ttl_days),
    )
    s.add(inv)
    audit(s, request, p.user_id, "invite.created", email, ",".join(body.roles))
    await s.commit()
    # The link is shown once to the owner, who shares it (e.g. on WhatsApp).
    return invite_out(inv, f"{settings.site_origin}/invite#{raw}")


@router.get("/invitations", response_model=list[InviteOut])
async def list_invitations(
    _: Principal = Depends(require_roles(ROLE_OWNER)), s: AsyncSession = Depends(session_dep)
) -> list[InviteOut]:
    rows = (await s.execute(select(Invitation).order_by(Invitation.created_at.desc()).limit(200))).scalars()
    return [invite_out(i) for i in rows]


@router.delete("/invitations/{invite_id}", status_code=204)
async def revoke_invitation(
    invite_id: str,
    request: Request,
    p: Principal = Depends(require_roles(ROLE_OWNER)),
    s: AsyncSession = Depends(session_dep),
) -> Response:
    inv = await s.get(Invitation, invite_id)
    if not inv:
        raise HTTPException(404, "That invitation doesn't exist.")
    if inv.accepted_at is None and inv.revoked_at is None:
        inv.revoked_at = utcnow()
        audit(s, request, p.user_id, "invite.revoked", inv.email)
        await s.commit()
    return Response(status_code=204)


async def _valid_invite(s: AsyncSession, token: str) -> Invitation:
    inv = (await s.execute(select(Invitation).where(Invitation.token_hash == sha256(token)))).scalar_one_or_none()
    if not inv or inv.accepted_at or inv.revoked_at or aware(inv.expires_at) <= utcnow():
        raise HTTPException(404, "This invitation link is no longer valid. Ask the family for a new one.")
    return inv


@router.get("/invitations/lookup", response_model=InviteInfoOut, dependencies=[Depends(rate_limit("invite", 30, 600))])
async def lookup_invitation(token: str, s: AsyncSession = Depends(session_dep)) -> InviteInfoOut:
    inv = await _valid_invite(s, token)
    return InviteInfoOut(email=inv.email, display_name=inv.display_name, roles=inv.roles.split(","))


@router.post(
    "/invitations/accept",
    response_model=UserOut,
    status_code=201,
    dependencies=[Depends(rate_limit("invite", 30, 600))],
)
async def accept_invitation(
    body: AcceptIn,
    request: Request,
    response: Response,
    s: AsyncSession = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> UserOut:
    inv = await _valid_invite(s, body.token)
    check_password_strength(body.password, settings, inv.email)
    if (await s.execute(select(User).where(User.email == inv.email))).scalar_one_or_none():
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    user = User(
        email=inv.email,
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
        roles=inv.roles,
        last_login_at=utcnow(),
    )
    s.add(user)
    inv.accepted_at = utcnow()
    await s.flush()
    await issue_session(s, response, request, settings, user)
    audit(s, request, user.id, "invite.accepted", inv.email)
    await s.commit()
    return user_out(user)


# ---- Users (owner only) ----


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: Principal = Depends(require_roles(ROLE_OWNER)), s: AsyncSession = Depends(session_dep)
) -> list[UserOut]:
    rows = (await s.execute(select(User).order_by(User.display_name))).scalars()
    return [user_out(u) for u in rows]


@router.patch("/users/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: str,
    body: UserPatch,
    request: Request,
    p: Principal = Depends(require_roles(ROLE_OWNER)),
    s: AsyncSession = Depends(session_dep),
) -> UserOut:
    user = await s.get(User, user_id)
    if not user:
        raise HTTPException(404, "That account doesn't exist.")
    new_roles = body.roles if body.roles is not None else user.role_list
    new_active = body.is_active if body.is_active is not None else user.is_active
    losing_owner = ROLE_OWNER in user.role_list and (ROLE_OWNER not in new_roles or not new_active)
    if losing_owner:
        owners = (
            await s.execute(
                select(func.count()).select_from(User).where(User.roles.contains(ROLE_OWNER), User.is_active)
            )
        ).scalar_one()
        if owners <= 1:
            raise HTTPException(409, "The memorial needs at least one owner.")
    user.roles = ",".join(new_roles)
    user.is_active = new_active
    if not new_active:
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
    audit(s, request, p.user_id, "user.updated", user.email, f"roles={user.roles} active={user.is_active}")
    await s.commit()
    return user_out(user)
