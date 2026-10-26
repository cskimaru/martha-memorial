import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(v: str) -> str:
    return _CTRL.sub("", v).strip()


def Text(max_len: int, min_len: int = 0):
    return Annotated[str, Field(max_length=max_len), AfterValidator(_clean), AfterValidator(_min(min_len))]


def _min(n: int):
    def check(v: str) -> str:
        if len(v) < n:
            raise ValueError("This field is required." if n == 1 else f"Use at least {n} characters.")
        return v

    return check


MediaId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
HttpsUrl = Annotated[str, Field(max_length=300, pattern=r"^(https://\S+)?$")]
Theme = Literal["plum", "forest", "navy", "burgundy", "charcoal"]


class ProfileIn(BaseModel):
    full_name: Text(160, 1)
    known_as: Text(200) = ""
    born: Text(60) = ""
    died: Text(60) = ""
    birthplace: Text(160) = ""
    resting_place: Text(160) = ""
    epitaph: Text(600) = ""
    portrait_media_id: MediaId | None = None
    service_date: Text(80) = ""
    service_venue: Text(200) = ""
    stream_url: HttpsUrl = ""
    theme: Theme = "plum"


class ProfileOut(ProfileIn):
    updated_at: datetime


class ChapterIn(BaseModel):
    title: Text(120, 1)
    intro: Text(6000) = ""
    prompt: Text(400) = ""
    position: int | None = Field(default=None, ge=0, le=100000)


class ChapterPatch(BaseModel):
    title: Text(120, 1) | None = None
    intro: Text(6000) | None = None
    prompt: Text(400) | None = None
    position: int | None = Field(default=None, ge=0, le=100000)
    hidden: bool | None = None


class EntryIn(BaseModel):
    chapter_id: str = Field(max_length=32)
    title: Text(160) = ""
    period: Text(40) = ""
    body: Text(20000) = ""
    media_id: MediaId | None = None
    caption: Text(240) = ""
    author_name: Text(80, 1)
    relation: Text(80) = ""


class EntryPatch(BaseModel):
    chapter_id: str | None = Field(default=None, max_length=32)
    title: Text(160) | None = None
    period: Text(40) | None = None
    body: Text(20000) | None = None
    media_id: MediaId | None = None
    remove_media: bool = False
    caption: Text(240) | None = None
    author_name: Text(80, 1) | None = None
    relation: Text(80) | None = None


class EntryOut(BaseModel):
    id: str
    chapter_id: str
    title: str
    period: str
    body: str
    media_id: str | None
    caption: str
    author_id: str
    author_name: str
    relation: str
    created_at: datetime
    updated_at: datetime


class ChapterOut(BaseModel):
    id: str
    slug: str
    title: str
    prompt: str
    intro: str
    position: int
    hidden: bool
    entries: list[EntryOut] = []


class StoryOut(BaseModel):
    profile: ProfileOut | None
    chapters: list[ChapterOut]


class TributeIn(BaseModel):
    name: Text(80, 1)
    relation: Text(80) = ""
    message: Text(4000, 2)
    website: str = Field(default="", max_length=200)  # honeypot: humans never fill this


class TributeOut(BaseModel):
    id: str
    name: str
    relation: str
    message: str
    status: str
    created_at: datetime


class ModerateIn(BaseModel):
    status: Literal["approved", "rejected"]


class CandleIn(BaseModel):
    name: Text(80, 1)
    note: Text(100) = ""
    website: str = Field(default="", max_length=200)


class CandleOut(BaseModel):
    id: str
    name: str
    note: str
    created_at: datetime


class CandlesOut(BaseModel):
    count: int
    candles: list[CandleOut]
