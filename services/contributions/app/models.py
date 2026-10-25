from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from memorial_common.db import Base, IdMixin, TimestampMixin, utcnow


class Contribution(IdMixin, TimestampMixin, Base):
    __tablename__ = "contributions"

    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    method: Mapped[str] = mapped_column(String(20))  # mpesa_stk | mpesa_manual | cash | bank
    status: Mapped[str] = mapped_column(String(20), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    amount_requested: Mapped[int] = mapped_column(Integer)
    amount_received: Mapped[int | None] = mapped_column(Integer, nullable=True)

    contributor_name: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(String(300), default="")
    show_name: Mapped[bool] = mapped_column(Boolean, default=True)
    phone_masked: Mapped[str] = mapped_column(String(20), default="")
    phone_hash: Mapped[str] = mapped_column(String(64), default="", index=True)

    checkout_request_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    merchant_request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Unique: one M-Pesa receipt can never be counted twice, whichever way it was recorded.
    mpesa_receipt: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)
    reference: Mapped[str] = mapped_column(String(80), default="")
    result_code: Mapped[str] = mapped_column(String(20), default="")
    result_desc: Mapped[str] = mapped_column(String(300), default="")

    recorded_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContributionEvent(IdMixin, Base):
    """Append-only history of every change to a contribution."""

    __tablename__ = "contribution_events"

    contribution_id: Mapped[str] = mapped_column(ForeignKey("contributions.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    from_status: Mapped[str] = mapped_column(String(20), default="")
    to_status: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(40))  # user id, "mpesa-callback", "reconciler", "system"
    note: Mapped[str] = mapped_column(Text, default="")


class CallbackLog(IdMixin, Base):
    """Every callback body Safaricom sends, kept verbatim for audit and reconciliation."""

    __tablename__ = "mpesa_callbacks"

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    source_ip: Mapped[str] = mapped_column(String(64), default="")
    checkout_request_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    body: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(40), default="")
