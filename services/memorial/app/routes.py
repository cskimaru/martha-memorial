import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from memorial_common.db import utcnow
from memorial_common.ratelimit import client_ip, hash_value, rate_limit
from memorial_common.security import ROLE_EDITOR, ROLE_OWNER, Principal, optional_principal, require_roles

from .models import AuditLog, Candle, Chapter, Entry, Profile, Tribute
from .schemas import (
    CandleIn,
    CandleOut,
    CandlesOut,
    ChapterIn,
    ChapterOut,
    ChapterPatch,
    EntryIn,
    EntryOut,
    EntryPatch,
    ModerateIn,
    ProfileIn,
    ProfileOut,
    StoryOut,
    TributeIn,
    TributeOut,
)

router = APIRouter(prefix="/api/memorial")
editor = require_roles(ROLE_EDITOR)


async def session_dep(request: Request):
    async for s in request.app.state.db.session():
        yield s


def audit(s: AsyncSession, actor: str | None, action: str, target: str = "") -> None:
    s.add(AuditLog(actor_id=actor, action=action, target=target))


def ip_hash(request: Request) -> str:
    return hash_value(client_ip(request), request.app.state.settings.ip_hash_salt)


def entry_out(e: Entry) -> EntryOut:
    return EntryOut.model_validate(e, from_attributes=True)


def chapter_out(c: Chapter, entries: list[EntryOut] | None = None) -> ChapterOut:
    return ChapterOut(
        id=c.id,
        slug=c.slug,
        title=c.title,
        prompt=c.prompt,
        intro=c.intro,
        position=c.position,
        hidden=c.hidden,
        entries=entries or [],
    )


# ---- Story (public) ----


@router.get("/story", response_model=StoryOut)
async def story(p: Principal | None = Depends(optional_principal), s: AsyncSession = Depends(session_dep)) -> StoryOut:
    is_editor = bool(p and p.has(ROLE_EDITOR))
    profile = await s.get(Profile, "main")
    q = select(Chapter).order_by(Chapter.position, Chapter.created_at)
    if not is_editor:
        q = q.where(Chapter.hidden.is_(False))
    chapters = list((await s.execute(q)).scalars())
    entries = (await s.execute(select(Entry).where(Entry.deleted_at.is_(None)).order_by(Entry.created_at))).scalars()
    by_chapter: dict[str, list[EntryOut]] = {}
    for e in entries:
        by_chapter.setdefault(e.chapter_id, []).append(entry_out(e))
    return StoryOut(
        profile=ProfileOut.model_validate(profile, from_attributes=True) if profile else None,
        chapters=[chapter_out(c, by_chapter.get(c.id)) for c in chapters],
    )


@router.put("/profile", response_model=ProfileOut)
async def put_profile(
    body: ProfileIn, p: Principal = Depends(editor), s: AsyncSession = Depends(session_dep)
) -> ProfileOut:
    profile = await s.get(Profile, "main")
    if profile is None:
        profile = Profile(id="main", full_name=body.full_name)
        s.add(profile)
    for k, v in body.model_dump().items():
        setattr(profile, k, v)
    profile.updated_by = p.user_id
    audit(s, p.user_id, "profile.updated")
    await s.commit()
    await s.refresh(profile)
    return ProfileOut.model_validate(profile, from_attributes=True)


# ---- Chapters (editors) ----


def slugify(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "chapter"
    return f"{base}-{secrets.token_hex(3)}"


@router.post("/chapters", response_model=ChapterOut, status_code=201)
async def create_chapter(
    body: ChapterIn, p: Principal = Depends(editor), s: AsyncSession = Depends(session_dep)
) -> ChapterOut:
    position = body.position
    if position is None:
        position = ((await s.execute(select(func.max(Chapter.position)))).scalar() or 0) + 10
    c = Chapter(slug=slugify(body.title), title=body.title, intro=body.intro, prompt=body.prompt, position=position)
    s.add(c)
    audit(s, p.user_id, "chapter.created", c.slug)
    await s.commit()
    return chapter_out(c)


@router.patch("/chapters/{chapter_id}", response_model=ChapterOut)
async def patch_chapter(
    chapter_id: str, body: ChapterPatch, p: Principal = Depends(editor), s: AsyncSession = Depends(session_dep)
) -> ChapterOut:
    c = await s.get(Chapter, chapter_id)
    if not c:
        raise HTTPException(404, "That chapter doesn't exist.")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    audit(s, p.user_id, "chapter.updated", c.id)
    await s.commit()
    return chapter_out(c)


# ---- Entries (editors write; authors and owners edit their own) ----


def can_change(p: Principal, e: Entry) -> bool:
    return e.author_id == p.user_id or ROLE_OWNER in p.roles


@router.post("/entries", response_model=EntryOut, status_code=201)
async def create_entry(
    body: EntryIn, p: Principal = Depends(editor), s: AsyncSession = Depends(session_dep)
) -> EntryOut:
    if not await s.get(Chapter, body.chapter_id):
        raise HTTPException(422, "Choose a chapter for this memory.")
    if not (body.body or body.title or body.media_id):
        raise HTTPException(422, "Write a memory or add a photograph first.")
    e = Entry(**body.model_dump(), author_id=p.user_id)
    s.add(e)
    await s.flush()
    audit(s, p.user_id, "entry.created", e.id)
    await s.commit()
    return entry_out(e)


@router.patch("/entries/{entry_id}", response_model=EntryOut)
async def patch_entry(
    entry_id: str, body: EntryPatch, p: Principal = Depends(editor), s: AsyncSession = Depends(session_dep)
) -> EntryOut:
    e = await s.get(Entry, entry_id)
    if not e or e.deleted_at:
        raise HTTPException(404, "That memory doesn't exist.")
    if not can_change(p, e):
        raise HTTPException(403, "Only the person who shared this memory, or an owner, can change it.")
    data = body.model_dump(exclude_none=True)
    if "chapter_id" in data and not await s.get(Chapter, data["chapter_id"]):
        raise HTTPException(422, "Choose a chapter for this memory.")
    if data.pop("remove_media", False):
        e.media_id = None
    for k, v in data.items():
        setattr(e, k, v)
    audit(s, p.user_id, "entry.updated", e.id)
    await s.commit()
    return entry_out(e)


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: str, p: Principal = Depends(editor), s: AsyncSession = Depends(session_dep)
) -> Response:
    e = await s.get(Entry, entry_id)
    if not e or e.deleted_at:
        raise HTTPException(404, "That memory doesn't exist.")
    if not can_change(p, e):
        raise HTTPException(403, "Only the person who shared this memory, or an owner, can remove it.")
    e.deleted_at = utcnow()  # soft delete: recoverable by an administrator
    audit(s, p.user_id, "entry.deleted", e.id)
    await s.commit()
    return Response(status_code=204)


# ---- Tributes ----


@router.get("/tributes", response_model=list[TributeOut])
async def list_tributes(
    status: str = "approved",
    p: Principal | None = Depends(optional_principal),
    s: AsyncSession = Depends(session_dep),
) -> list[TributeOut]:
    if status != "approved" and not (p and p.has(ROLE_EDITOR)):
        raise HTTPException(403, "Only family editors can see tributes awaiting approval.")
    if status not in ("approved", "pending", "rejected"):
        raise HTTPException(422, "Unknown status.")
    rows = (
        await s.execute(select(Tribute).where(Tribute.status == status).order_by(Tribute.created_at.desc()).limit(500))
    ).scalars()
    return [TributeOut.model_validate(t, from_attributes=True) for t in rows]


@router.post(
    "/tributes", response_model=TributeOut, status_code=201, dependencies=[Depends(rate_limit("tribute", 5, 3600))]
)
async def create_tribute(
    body: TributeIn,
    request: Request,
    p: Principal | None = Depends(optional_principal),
    s: AsyncSession = Depends(session_dep),
) -> TributeOut:
    trusted = bool(p and p.has(ROLE_EDITOR))
    moderate = request.app.state.settings.moderate_public_tributes and not trusted
    t = Tribute(
        name=body.name,
        relation=body.relation,
        message=body.message,
        status="pending" if moderate else "approved",
        author_id=p.user_id if p else None,
        ip_hash=ip_hash(request),
    )
    if body.website:
        # Bot filled the hidden field: pretend success, store nothing.
        return TributeOut(
            id="0" * 32, name=t.name, relation=t.relation, message=t.message, status="pending", created_at=utcnow()
        )
    s.add(t)
    await s.commit()
    return TributeOut.model_validate(t, from_attributes=True)


@router.post("/tributes/{tribute_id}/moderate", response_model=TributeOut)
async def moderate_tribute(
    tribute_id: str, body: ModerateIn, p: Principal = Depends(editor), s: AsyncSession = Depends(session_dep)
) -> TributeOut:
    t = await s.get(Tribute, tribute_id)
    if not t:
        raise HTTPException(404, "That tribute doesn't exist.")
    t.status = body.status
    t.moderated_by = p.user_id
    t.moderated_at = utcnow()
    audit(s, p.user_id, f"tribute.{body.status}", t.id)
    await s.commit()
    return TributeOut.model_validate(t, from_attributes=True)


# ---- Candles ----


@router.get("/candles", response_model=CandlesOut)
async def list_candles(s: AsyncSession = Depends(session_dep)) -> CandlesOut:
    visible = Candle.hidden.is_(False)
    count = (await s.execute(select(func.count()).select_from(Candle).where(visible))).scalar_one()
    rows = (await s.execute(select(Candle).where(visible).order_by(Candle.created_at.desc()).limit(300))).scalars()
    return CandlesOut(count=count, candles=[CandleOut.model_validate(c, from_attributes=True) for c in rows])


@router.post(
    "/candles", response_model=CandleOut, status_code=201, dependencies=[Depends(rate_limit("candle", 10, 3600))]
)
async def light_candle(body: CandleIn, request: Request, s: AsyncSession = Depends(session_dep)) -> CandleOut:
    c = Candle(name=body.name, note=body.note, ip_hash=ip_hash(request))
    if body.website:
        return CandleOut(id="0" * 32, name=c.name, note=c.note, created_at=utcnow())
    s.add(c)
    await s.commit()
    return CandleOut.model_validate(c, from_attributes=True)


@router.delete("/candles/{candle_id}", status_code=204)
async def hide_candle(
    candle_id: str, p: Principal = Depends(editor), s: AsyncSession = Depends(session_dep)
) -> Response:
    c = await s.get(Candle, candle_id)
    if not c:
        raise HTTPException(404, "That candle doesn't exist.")
    c.hidden = True
    audit(s, p.user_id, "candle.hidden", c.id)
    await s.commit()
    return Response(status_code=204)
