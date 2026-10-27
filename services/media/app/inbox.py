"""Import photos dropped in the pCloud "Add to Gallery" folder, for a family member to review.

The inbox service copies new files from pCloud into INBOX_DIR. Each one is checked and
re-encoded like an upload and recorded as "pending"; it appears on the memorial only after a
family member approves it in the Family area. Files that aren't usable photos go to
INBOX_DIR/.failed, which the inbox service returns to pCloud so the sender can see them.
"""

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI

from .images import InvalidImage

log = logging.getLogger("inbox")
OWNER = "pcloud"


def _waiting(inbox: Path) -> list[Path]:
    return sorted(p for p in inbox.iterdir() if p.is_file() and not p.name.startswith("."))


def _read(f: Path, limit: int) -> bytes:
    if f.stat().st_size > limit:
        raise InvalidImage(f"larger than {limit // (1024 * 1024)} MB")
    return f.read_bytes()


def _set_aside(f: Path) -> None:
    failed = f.parent / ".failed"
    failed.mkdir(exist_ok=True)
    with contextlib.suppress(OSError):
        f.replace(failed / f.name)


async def import_once(app: FastAPI) -> int:
    """Import every file waiting in the inbox. Returns how many photos were added for review."""
    from .routes import store_photo  # routes imports this package's helpers; avoid a cycle

    st = app.state.settings
    added = 0
    for f in await asyncio.to_thread(_waiting, Path(st.inbox_dir)):
        try:
            data = await asyncio.to_thread(_read, f, st.max_upload_mb * 1024 * 1024)
            async for s in app.state.db.session():
                if await store_photo(app, s, data, owner_id=OWNER, name=f.name, review="pending"):
                    added += 1
                else:
                    log.info("Skipped a shared photo already waiting or shown", extra={"fields": {"file": f.name}})
            await asyncio.to_thread(f.unlink)
        except (InvalidImage, OSError) as e:
            log.warning("Couldn't import a shared photo", extra={"fields": {"file": f.name, "error": str(e)}})
            await asyncio.to_thread(_set_aside, f)
    if added:
        log.info("Imported shared photos for review", extra={"fields": {"count": added}})
    return added


async def run(app: FastAPI) -> None:
    st = app.state.settings
    await asyncio.to_thread(Path(st.inbox_dir).mkdir, parents=True, exist_ok=True)
    while True:
        try:
            await import_once(app)
        except Exception:
            log.exception("Inbox import failed")
        await asyncio.sleep(st.inbox_poll_seconds)


async def start(app: FastAPI) -> None:
    if app.state.settings.inbox_dir:
        app.state.inbox_task = asyncio.create_task(run(app))


async def stop(app: FastAPI) -> None:
    task = getattr(app.state, "inbox_task", None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
