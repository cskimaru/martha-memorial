"""Confirm a payment with Safaricom's status API before counting it."""

import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from memorial_common.db import aware, utcnow

from .config import Settings
from .daraja import DarajaClient, DarajaError
from .ledger import transition
from .models import Contribution

log = logging.getLogger("verify")
OPEN = ("pending", "verifying", "expired")


async def verify_contribution(
    s: AsyncSession, daraja: DarajaClient, settings: Settings, c: Contribution, actor: str
) -> str:
    if c.status not in OPEN:
        return c.status
    now = utcnow()
    age = now - aware(c.created_at)
    timeout = timedelta(minutes=settings.pending_timeout_minutes)

    if not c.checkout_request_id:
        # The STK request never got an answer, so there is nothing to ask M-Pesa about.
        if c.status == "pending" and age > timeout:
            transition(s, c, "expired", actor, "No response from M-Pesa when the prompt was sent. Check the statement.")
        return c.status

    try:
        q = await daraja.stk_query(c.checkout_request_id)
    except DarajaError as e:
        c.last_checked_at = now
        log.warning("Status query failed", extra={"fields": {"id": c.id, "error": str(e)}})
        return c.status

    c.last_checked_at = now
    state = q["state"]
    if state == "processing":
        if c.status == "pending" and age > timeout:
            transition(s, c, "expired", actor, "Still processing after the time limit.")
        return c.status

    c.result_code, c.result_desc = q["code"], q["desc"][:300]
    if state == "success":
        if c.amount_received is not None and c.amount_received != c.amount_requested:
            transition(s, c, "mismatch", actor, f"Received KES {c.amount_received}, expected KES {c.amount_requested}.")
        else:
            transition(s, c, "confirmed", actor, "Verified with the M-Pesa status query.")
    elif c.status != "expired":
        target = {"cancelled": "cancelled", "timeout": "expired"}.get(state, "failed")
        transition(s, c, target, actor, q["desc"])
    return c.status
