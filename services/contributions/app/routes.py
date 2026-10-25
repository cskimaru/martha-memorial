import csv
import hmac
import io
import json
import logging
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import Counter
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from memorial_common.logging import log_fields
from memorial_common.ratelimit import client_ip, rate_limit
from memorial_common.security import ROLE_TREASURER, Principal, require_roles

from .config import Settings
from .daraja import DarajaError, classify
from .ledger import COUNTED, TransitionError, transition
from .models import CallbackLog, Contribution, ContributionEvent
from .phones import mask, normalize_ke_phone, phone_hash
from .schemas import (
    ContributorOut,
    EventOut,
    LedgerDetail,
    LedgerOut,
    LedgerRow,
    ManualIn,
    ReviewIn,
    StatusOut,
    StkIn,
    SummaryOut,
)
from .verify import verify_contribution

router = APIRouter(prefix="/api/contributions")
log = logging.getLogger("contributions")
treasurer = require_roles(ROLE_TREASURER)
ACK = {"ResultCode": 0, "ResultDesc": "Accepted"}
callbacks = Counter("mpesa_callbacks_total", "M-Pesa callbacks received", ["outcome"])

MESSAGES = {
    "pending": "Check your phone and enter your M-Pesa PIN to complete the contribution.",
    "verifying": "Payment received. Confirming with M-Pesa…",
    "confirmed": "Thank you. Your contribution has been received.",
    "failed": "The payment didn't go through. No money was taken. You can try again.",
    "cancelled": "The payment was cancelled on your phone. No money was taken.",
    "expired": (
        "The M-Pesa prompt timed out. If money left your account, the family will confirm it from their statement."
    ),
    "mismatch": "Payment received. The family will confirm it shortly.",
    "void": "This entry was withdrawn.",
}


async def session_dep(request: Request):
    async for s in request.app.state.db.session():
        yield s


def settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def status_out(c: Contribution) -> StatusOut:
    return StatusOut(id=c.id, status=c.status, message=MESSAGES.get(c.status, ""))


# ---- Public ----


@router.get("/summary", response_model=SummaryOut)
async def summary(s: AsyncSession = Depends(session_dep), st: Settings = Depends(settings_dep)) -> SummaryOut:
    counted = Contribution.status == COUNTED
    total, count = (
        await s.execute(select(func.coalesce(func.sum(Contribution.amount_received), 0), func.count()).where(counted))
    ).one()
    rows = (
        await s.execute(
            select(Contribution)
            .where(counted, Contribution.show_name)
            .order_by(Contribution.confirmed_at.desc())
            .limit(200)
        )
    ).scalars()
    return SummaryOut(
        giving_open=st.mpesa_enabled,
        total=int(total),
        count=int(count),
        contributors=[
            ContributorOut(
                name=c.contributor_name, message=c.message, amount=c.amount_received if st.public_show_amounts else None
            )
            for c in rows
        ],
        paybill=st.display_paybill,
        account=st.display_account,
        min_amount=st.min_amount,
        max_amount=st.max_amount,
    )


@router.post("/mpesa/stk", response_model=StatusOut, status_code=202, dependencies=[Depends(rate_limit("stk", 6, 600))])
async def start_stk(
    body: StkIn,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
    s: AsyncSession = Depends(session_dep),
    st: Settings = Depends(settings_dep),
) -> StatusOut:
    if not st.mpesa_enabled:
        raise HTTPException(503, "M-Pesa giving isn't open yet.")
    phone = normalize_ke_phone(body.phone)
    if not phone:
        raise HTTPException(422, "Enter a Safaricom number like 0712 345 678.")
    if not st.min_amount <= body.amount <= st.max_amount:
        raise HTTPException(422, f"Enter an amount between KES {st.min_amount:,} and KES {st.max_amount:,}.")
    if body.website:
        return StatusOut(id="0" * 32, status="pending", message=MESSAGES["pending"])

    existing = (
        await s.execute(select(Contribution).where(Contribution.idempotency_key == idempotency_key))
    ).scalar_one_or_none()
    if existing:
        return status_out(existing)

    ph = phone_hash(phone, st.phone_hash_pepper)
    if not await request.app.state.limiter.hit(f"stk-phone:{ph}", 3, 600):
        raise HTTPException(429, "Several prompts were already sent to this number. Please wait ten minutes.")

    c = Contribution(
        idempotency_key=idempotency_key,
        method="mpesa_stk",
        status="pending",
        amount_requested=body.amount,
        contributor_name=body.name,
        message=body.message,
        show_name=body.show_name,
        phone_masked=mask(phone),
        phone_hash=ph,
    )
    s.add(c)
    try:
        await s.flush()
    except IntegrityError:
        await s.rollback()
        existing = (
            await s.execute(select(Contribution).where(Contribution.idempotency_key == idempotency_key))
        ).scalar_one()
        return status_out(existing)
    s.add(ContributionEvent(contribution_id=c.id, to_status="pending", actor="system", note="STK push requested"))
    await s.commit()

    try:
        data = await request.app.state.daraja.stk_push(
            phone=phone, amount=body.amount, reference=st.mpesa_account_reference, description="Contribution"
        )
    except DarajaError as e:
        log_fields(log, logging.ERROR, "STK push failed", id=c.id, error=str(e), sent=e.sent)
        c.result_desc = str(e)[:300]
        if e.sent is False:
            transition(s, c, "failed", "system", str(e))
            await s.commit()
            raise HTTPException(502, "We couldn't reach M-Pesa. No money was taken. Please try again.") from e
        await s.commit()
        return StatusOut(
            id=c.id,
            status="pending",
            message="M-Pesa is slow to respond. If a prompt appears on your phone, you can complete it.",
        )

    c.checkout_request_id = str(data.get("CheckoutRequestID", ""))[:80] or None
    c.merchant_request_id = str(data.get("MerchantRequestID", ""))[:80] or None
    await s.commit()
    return status_out(c)


@router.get("/{contribution_id}/status", response_model=StatusOut)
async def get_status(contribution_id: str, s: AsyncSession = Depends(session_dep)) -> StatusOut:
    c = await s.get(Contribution, contribution_id) if len(contribution_id) == 32 else None
    if not c:
        raise HTTPException(404, "We couldn't find that contribution.")
    return status_out(c)


# ---- Safaricom callback ----


def _amount(value: object) -> int | None:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return int(d) if d == d.to_integral_value() and d > 0 else None


async def _verify_later(app, contribution_id: str) -> None:
    async with app.state.db.sessionmaker() as s:
        c = await s.get(Contribution, contribution_id)
        if c:
            await verify_contribution(s, app.state.daraja, app.state.settings, c, "mpesa-callback")
            await s.commit()


@router.post("/mpesa/callback/{token}", include_in_schema=False)
async def mpesa_callback(
    token: str,
    request: Request,
    background: BackgroundTasks,
    s: AsyncSession = Depends(session_dep),
    st: Settings = Depends(settings_dep),
) -> JSONResponse:
    if not st.mpesa_callback_token or not hmac.compare_digest(token.encode(), st.mpesa_callback_token.encode()):
        callbacks.labels("bad_token").inc()
        raise HTTPException(404, "Not found")
    ip = client_ip(request)
    if st.allowed_ips and ip not in st.allowed_ips:
        callbacks.labels("ip_refused").inc()
        log_fields(log, logging.WARNING, "Callback from unexpected IP", ip=ip)
        raise HTTPException(403, "Forbidden")

    raw = await request.body()
    if len(raw) > 64 * 1024:
        raise HTTPException(413, "Too large")
    entry = CallbackLog(source_ip=ip, body=raw.decode("utf-8", errors="replace"))
    s.add(entry)

    try:
        cb = json.loads(raw)["Body"]["stkCallback"]
        checkout = str(cb["CheckoutRequestID"])
        code = str(cb["ResultCode"])
    except (ValueError, KeyError, TypeError):
        entry.outcome = "malformed"
        callbacks.labels("malformed").inc()
        await s.commit()
        return JSONResponse(ACK)

    entry.checkout_request_id = checkout[:80]
    q = select(Contribution).where(Contribution.checkout_request_id == checkout).with_for_update()
    c = (await s.execute(q)).scalar_one_or_none()
    if not c:
        entry.outcome = "orphan"
        callbacks.labels("orphan").inc()
        log_fields(log, logging.ERROR, "Callback for unknown payment", checkout=checkout)
        await s.commit()
        return JSONResponse(ACK)

    c.result_code = code
    c.result_desc = str(cb.get("ResultDesc", ""))[:300]
    if code == "0":
        items = {i.get("Name"): i.get("Value") for i in (cb.get("CallbackMetadata") or {}).get("Item", [])}
        receipt = str(items.get("MpesaReceiptNumber") or "")[:30] or None
        amount = _amount(items.get("Amount"))
        if c.status not in ("pending", "expired"):
            entry.outcome = f"ignored_{c.status}"
        elif (
            receipt
            and (
                await s.execute(
                    select(Contribution.id).where(Contribution.mpesa_receipt == receipt, Contribution.id != c.id)
                )
            ).first()
        ):
            entry.outcome = "duplicate_receipt"
            log_fields(log, logging.ERROR, "Receipt already recorded", receipt=receipt, id=c.id)
        else:
            c.mpesa_receipt = receipt
            c.amount_received = amount
            transition(s, c, "verifying", "mpesa-callback", f"Callback reports success, receipt {receipt}")
            entry.outcome = "success_unverified"
            background.add_task(_verify_later, request.app, c.id)
    else:
        target = {"cancelled": "cancelled", "timeout": "expired"}.get(classify(code), "failed")
        transition(s, c, target, "mpesa-callback", c.result_desc)
        entry.outcome = target
    callbacks.labels(entry.outcome).inc()
    await s.commit()
    return JSONResponse(ACK)


# ---- Treasurer ----


def ledger_row(c: Contribution) -> LedgerRow:
    return LedgerRow.model_validate(c, from_attributes=True)


@router.post("/manual", response_model=LedgerRow, status_code=201)
async def record_manual(
    body: ManualIn, p: Principal = Depends(treasurer), s: AsyncSession = Depends(session_dep)
) -> LedgerRow:
    if body.method in ("bank", "mpesa_manual") and not body.reference:
        raise HTTPException(422, "Add the bank reference or M-Pesa receipt number.")
    receipt = body.reference.upper() if body.method == "mpesa_manual" else None
    if receipt and (await s.execute(select(Contribution.id).where(Contribution.mpesa_receipt == receipt))).first():
        raise HTTPException(409, "That M-Pesa receipt is already in the ledger.")
    c = Contribution(
        method=body.method,
        status="pending",
        amount_requested=body.amount,
        amount_received=body.amount,
        contributor_name=body.name,
        message=body.message,
        show_name=body.show_name,
        reference=body.reference,
        mpesa_receipt=receipt,
        recorded_by=p.user_id,
    )
    s.add(c)
    await s.flush()
    transition(s, c, "confirmed", p.user_id, f"Recorded by treasurer ({body.method})")
    await s.commit()
    return ledger_row(c)


@router.post("/{contribution_id}/review", response_model=LedgerRow)
async def review(
    contribution_id: str, body: ReviewIn, p: Principal = Depends(treasurer), s: AsyncSession = Depends(session_dep)
) -> LedgerRow:
    c = await s.get(Contribution, contribution_id)
    if not c:
        raise HTTPException(404, "We couldn't find that contribution.")
    if body.to == "confirmed" and c.status != "mismatch":
        raise HTTPException(409, "Only payments with an amount mismatch can be confirmed by hand.")
    try:
        changed = transition(s, c, body.to, p.user_id, body.note)
    except TransitionError as e:
        raise HTTPException(409, str(e)) from e
    if not changed:
        raise HTTPException(409, f"A {c.status} contribution can't be changed to {body.to}.")
    await s.commit()
    return ledger_row(c)


@router.get("/ledger", response_model=LedgerOut)
async def ledger(
    status: str | None = None, _: Principal = Depends(treasurer), s: AsyncSession = Depends(session_dep)
) -> LedgerOut:
    q = select(Contribution).order_by(Contribution.created_at.desc()).limit(2000)
    if status:
        q = q.where(Contribution.status == status)
    rows = [ledger_row(c) for c in (await s.execute(q)).scalars()]
    total = (
        await s.execute(
            select(func.coalesce(func.sum(Contribution.amount_received), 0)).where(Contribution.status == COUNTED)
        )
    ).scalar_one()
    by_status = dict((await s.execute(select(Contribution.status, func.count()).group_by(Contribution.status))).all())
    return LedgerOut(rows=rows, total_confirmed=int(total), by_status=by_status)


@router.get("/ledger/{contribution_id}", response_model=LedgerDetail)
async def ledger_detail(
    contribution_id: str, _: Principal = Depends(treasurer), s: AsyncSession = Depends(session_dep)
) -> LedgerDetail:
    c = await s.get(Contribution, contribution_id)
    if not c:
        raise HTTPException(404, "We couldn't find that contribution.")
    events = (
        await s.execute(
            select(ContributionEvent).where(ContributionEvent.contribution_id == c.id).order_by(ContributionEvent.at)
        )
    ).scalars()
    return LedgerDetail(
        **ledger_row(c).model_dump(), events=[EventOut.model_validate(e, from_attributes=True) for e in events]
    )


def _csv_safe(v: object) -> str:
    text = "" if v is None else str(v)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/ledger.csv")
async def ledger_csv(_: Principal = Depends(treasurer), s: AsyncSession = Depends(session_dep)) -> StreamingResponse:
    cols = list(LedgerRow.model_fields)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for c in (await s.execute(select(Contribution).order_by(Contribution.created_at))).scalars():
        row = ledger_row(c).model_dump()
        w.writerow([_csv_safe(row[k]) for k in cols])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="contributions-ledger.csv"'},
    )
