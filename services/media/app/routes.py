import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from memorial_common.db import utcnow
from memorial_common.ratelimit import rate_limit
from memorial_common.security import ROLE_EDITOR, ROLE_OWNER, Principal, require_roles

from .images import InvalidImage, process
from .models import MediaObject

router = APIRouter(prefix="/api/media")
ID_RE = re.compile(r"^[0-9a-f]{32}$")
CACHE = "public, max-age=31536000, immutable"


class MediaOut(BaseModel):
    id: str
    width: int
    height: int
    url: str
    thumb_url: str


async def session_dep(request: Request):
    async for s in request.app.state.db.session():
        yield s


def out(m: MediaObject) -> MediaOut:
    return MediaOut(
        id=m.id, width=m.width, height=m.height, url=f"/api/media/{m.id}", thumb_url=f"/api/media/{m.id}/thumb"
    )


async def read_limited(file: UploadFile, limit: int) -> bytes:
    chunks, total = [], 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, f"That file is larger than {limit // (1024 * 1024)} MB.")
        chunks.append(chunk)
    if not total:
        raise HTTPException(422, "The file is empty.")
    return b"".join(chunks)


@router.post(
    "/upload", response_model=MediaOut, status_code=201, dependencies=[Depends(rate_limit("upload", 120, 3600))]
)
async def upload(
    request: Request,
    file: UploadFile,
    p: Principal = Depends(require_roles(ROLE_EDITOR)),
    s: AsyncSession = Depends(session_dep),
) -> MediaOut:
    st = request.app.state.settings
    data = await read_limited(file, st.max_upload_mb * 1024 * 1024)
    try:
        img = await run_in_threadpool(
            process,
            data,
            max_pixels=st.max_pixels,
            max_dim=st.max_dimension,
            thumb_dim=st.thumb_dimension,
            quality=st.jpeg_quality,
        )
    except InvalidImage as e:
        raise HTTPException(422, str(e)) from e
    m = MediaObject(
        owner_id=p.user_id,
        content_type="image/jpeg",
        width=img.width,
        height=img.height,
        size_bytes=len(img.full),
        sha256=img.sha256,
        storage_key="",
        thumb_key="",
        original_name=(file.filename or "")[:200],
    )
    m.storage_key = f"photos/{m.id}/full.jpg"
    m.thumb_key = f"photos/{m.id}/thumb.jpg"
    storage = request.app.state.storage
    await storage.put(m.storage_key, img.full, "image/jpeg")
    await storage.put(m.thumb_key, img.thumb, "image/jpeg")
    s.add(m)
    await s.commit()
    return out(m)


async def _serve(request: Request, s: AsyncSession, media_id: str, thumb: bool) -> Response:
    if not ID_RE.match(media_id):
        raise HTTPException(404, "Photo not found.")
    m = await s.get(MediaObject, media_id)
    if not m or m.deleted_at:
        raise HTTPException(404, "Photo not found.")
    etag = f'"{m.sha256[:32]}{"t" if thumb else "f"}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": CACHE})
    data = await request.app.state.storage.get(m.thumb_key if thumb else m.storage_key)
    if data is None:
        raise HTTPException(404, "Photo not found.")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": CACHE,
            "ETag": etag,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


@router.get("/{media_id}")
async def get_full(media_id: str, request: Request, s: AsyncSession = Depends(session_dep)) -> Response:
    return await _serve(request, s, media_id, thumb=False)


@router.get("/{media_id}/thumb")
async def get_thumb(media_id: str, request: Request, s: AsyncSession = Depends(session_dep)) -> Response:
    return await _serve(request, s, media_id, thumb=True)


@router.delete("/{media_id}", status_code=204)
async def delete(
    media_id: str,
    request: Request,
    p: Principal = Depends(require_roles(ROLE_EDITOR)),
    s: AsyncSession = Depends(session_dep),
) -> Response:
    m = await s.get(MediaObject, media_id) if ID_RE.match(media_id) else None
    if not m or m.deleted_at:
        raise HTTPException(404, "Photo not found.")
    if m.owner_id != p.user_id and ROLE_OWNER not in p.roles:
        raise HTTPException(403, "Only the person who uploaded this photo, or an owner, can remove it.")
    m.deleted_at = utcnow()
    await s.commit()
    # Objects stay in storage (and backups) until a scheduled purge; the record is what hides them.
    return Response(status_code=204)
