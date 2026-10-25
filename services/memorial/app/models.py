from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from memorial_common.db import Base, IdMixin, TimestampMixin, utcnow


class Profile(TimestampMixin, Base):
    __tablename__ = "profile"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="main")
    full_name: Mapped[str] = mapped_column(String(160))
    known_as: Mapped[str] = mapped_column(String(200), default="")
    born: Mapped[str] = mapped_column(String(60), default="")
    died: Mapped[str] = mapped_column(String(60), default="")
    birthplace: Mapped[str] = mapped_column(String(160), default="")
    resting_place: Mapped[str] = mapped_column(String(160), default="")
    epitaph: Mapped[str] = mapped_column(Text, default="")
    portrait_media_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    service_date: Mapped[str] = mapped_column(String(80), default="")
    service_venue: Mapped[str] = mapped_column(String(200), default="")
    stream_url: Mapped[str] = mapped_column(String(300), default="")
    updated_by: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Chapter(IdMixin, TimestampMixin, Base):
    __tablename__ = "chapters"

    slug: Mapped[str] = mapped_column(String(60), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    prompt: Mapped[str] = mapped_column(Text, default="")
    intro: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0, index=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    entries: Mapped[list["Entry"]] = relationship(back_populates="chapter", lazy="raise")


class Entry(IdMixin, TimestampMixin, Base):
    __tablename__ = "entries"

    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    period: Mapped[str] = mapped_column(String(40), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    media_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    caption: Mapped[str] = mapped_column(String(240), default="")
    author_id: Mapped[str] = mapped_column(String(32), index=True)
    author_name: Mapped[str] = mapped_column(String(80))
    relation: Mapped[str] = mapped_column(String(80), default="")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chapter: Mapped[Chapter] = relationship(back_populates="entries", lazy="raise")


class Tribute(IdMixin, Base):
    __tablename__ = "tributes"

    name: Mapped[str] = mapped_column(String(80))
    relation: Mapped[str] = mapped_column(String(80), default="")
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    author_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    moderated_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Candle(IdMixin, Base):
    __tablename__ = "candles"

    name: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(String(100), default="")
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_log"

    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(64), default="")
