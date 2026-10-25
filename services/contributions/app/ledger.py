"""Status changes for contributions. Every change goes through `transition`."""

import logging

from prometheus_client import Counter
from sqlalchemy.ext.asyncio import AsyncSession

from memorial_common.db import utcnow

from .models import Contribution, ContributionEvent

log = logging.getLogger("ledger")

TRANSITIONS: dict[str, set[str]] = {
    "pending": {"verifying", "confirmed", "failed", "cancelled", "expired"},
    "verifying": {"confirmed", "failed", "mismatch", "expired", "cancelled"},
    "confirmed": {"void"},
    "failed": set(),
    "cancelled": set(),
    "expired": {"verifying", "confirmed"},  # a late, verified success still counts
    "mismatch": {"confirmed", "void"},  # treasurer resolves after checking M-Pesa statement
    "void": set(),
}
TERMINAL = {"confirmed", "failed", "cancelled", "void"}
COUNTED = "confirmed"

status_changes = Counter("contributions_status_changes_total", "Contribution status changes", ["to_status", "method"])


class TransitionError(Exception):
    pass


def transition(s: AsyncSession, c: Contribution, to: str, actor: str, note: str = "") -> bool:
    """Apply a status change. Returns False (and does nothing) if it isn't allowed."""
    if to == c.status:
        return False
    if to not in TRANSITIONS.get(c.status, set()):
        log.warning("Refused transition", extra={"fields": {"id": c.id, "from": c.status, "to": to}})
        return False
    if to == "void" and c.method == "mpesa_stk" and c.status == "confirmed":
        raise TransitionError("A verified M-Pesa payment can't be voided. Record a refund note instead.")
    s.add(ContributionEvent(contribution_id=c.id, from_status=c.status, to_status=to, actor=actor, note=note[:2000]))
    c.status = to
    if to == "confirmed":
        c.confirmed_at = utcnow()
        if c.amount_received is None:
            c.amount_received = c.amount_requested
    status_changes.labels(to_status=to, method=c.method).inc()
    return True
