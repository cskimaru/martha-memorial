import uuid
from datetime import timedelta

import httpx
import respx
from sqlalchemy import update

from app.daraja import DarajaClient, DarajaError
from app.phones import normalize_ke_phone

from .conftest import auth

TREASURER = auth("u-treasurer", "treasurer")
EDITOR = auth("u-editor", "editor")
CB = "/api/contributions/mpesa/callback/cb-secret-token-1234567890"


def key() -> dict:
    return {"Idempotency-Key": uuid.uuid4().hex}


async def start(client, amount=1000, phone="0712345678", headers=None, name="Kerubo"):
    return await client.post(
        "/api/contributions/mpesa/stk",
        json={"phone": phone, "amount": amount, "name": name, "message": "Pole sana"},
        headers=headers or key(),
    )


def callback_body(checkout, code=0, amount=1000, receipt="TJK1ABC234"):
    cb = {"MerchantRequestID": "m", "CheckoutRequestID": checkout, "ResultCode": code, "ResultDesc": "desc"}
    if code == 0:
        cb["CallbackMetadata"] = {
            "Item": [
                {"Name": "Amount", "Value": amount},
                {"Name": "MpesaReceiptNumber", "Value": receipt},
                {"Name": "TransactionDate", "Value": 20261020101010},
                {"Name": "PhoneNumber", "Value": 254712345678},
            ]
        }
    return {"Body": {"stkCallback": cb}}


async def checkout_of(cid):
    from app.main import db
    from app.models import Contribution

    async with db.sessionmaker() as s:
        return (await s.get(Contribution, cid)).checkout_request_id


async def status(client, cid):
    return (await client.get(f"/api/contributions/{cid}/status")).json()["status"]


def receipt():
    return "T" + uuid.uuid4().hex[:9].upper()


async def test_phone_normalisation():
    assert normalize_ke_phone("0712 345 678") == "254712345678"
    assert normalize_ke_phone("+254 112 345 678") == "254112345678"
    assert normalize_ke_phone("712345678") == "254712345678"
    assert normalize_ke_phone("0812345678") is None
    assert normalize_ke_phone("12345") is None


async def test_happy_path_is_confirmed_only_after_verification(client):
    before = (await client.get("/api/contributions/summary")).json()["total"]
    r = await start(client)
    assert r.status_code == 202, r.text
    cid = r.json()["id"]
    assert r.json()["status"] == "pending"
    checkout = await checkout_of(cid)
    r = await client.post(CB, json=callback_body(checkout, receipt=receipt()))
    assert r.json() == {"ResultCode": 0, "ResultDesc": "Accepted"}
    assert await status(client, cid) == "confirmed"
    after = (await client.get("/api/contributions/summary")).json()
    assert after["total"] == before + 1000
    assert any(c["name"] == "Kerubo" for c in after["contributors"])
    assert all(c["amount"] is None for c in after["contributors"])  # amounts hidden by default


async def test_forged_success_callback_is_not_counted(client):
    from app.main import app

    before = (await client.get("/api/contributions/summary")).json()["total"]
    cid = (await start(client)).json()["id"]
    app.state.daraja.query_state = "failed"  # Safaricom says it never succeeded
    await client.post(CB, json=callback_body(await checkout_of(cid), receipt=receipt()))
    assert await status(client, cid) == "failed"
    assert (await client.get("/api/contributions/summary")).json()["total"] == before


async def test_amount_mismatch_is_held_for_review(client):
    cid = (await start(client, amount=5000)).json()["id"]
    await client.post(CB, json=callback_body(await checkout_of(cid), amount=50, receipt=receipt()))
    assert await status(client, cid) == "mismatch"
    r = await client.post(f"/api/contributions/{cid}/review", json={"to": "confirmed", "note": "x"}, headers=TREASURER)
    assert r.status_code == 422  # note too short
    r = await client.post(
        f"/api/contributions/{cid}/review",
        json={"to": "void", "note": "Checked statement: only KES 50"},
        headers=TREASURER,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "void"


async def test_replayed_callback_does_not_double_count(client):
    cid = (await start(client, amount=700)).json()["id"]
    body = callback_body(await checkout_of(cid), amount=700, receipt=receipt())
    await client.post(CB, json=body)
    total = (await client.get("/api/contributions/summary")).json()["total"]
    await client.post(CB, json=body)
    assert (await client.get("/api/contributions/summary")).json()["total"] == total


async def test_same_receipt_on_two_payments_counts_once(client):
    rc = receipt()
    a = (await start(client, amount=300)).json()["id"]
    b = (await start(client, amount=300, phone="0722000111")).json()["id"]
    await client.post(CB, json=callback_body(await checkout_of(a), amount=300, receipt=rc))
    await client.post(CB, json=callback_body(await checkout_of(b), amount=300, receipt=rc))
    assert await status(client, a) == "confirmed"
    assert await status(client, b) == "pending"


async def test_idempotency_key_prevents_double_prompt(client):
    from app.main import app

    h = key()
    r1 = await start(client, headers=h)
    r2 = await start(client, headers=h)
    assert r1.json()["id"] == r2.json()["id"]
    assert len(app.state.daraja.pushes) == 1


async def test_cancel_on_phone(client):
    cid = (await start(client)).json()["id"]
    await client.post(CB, json=callback_body(await checkout_of(cid), code=1032))
    assert await status(client, cid) == "cancelled"


async def test_callback_security(client):
    r = await client.post("/api/contributions/mpesa/callback/wrong-token", json=callback_body("x"))
    assert r.status_code == 404
    r = await client.post(CB, json=callback_body("ws_CO_unknown"))
    assert r.status_code == 200  # acknowledged, logged as orphan
    r = await client.post(CB, content=b"not json", headers={"content-type": "application/json"})
    assert r.status_code == 200


async def test_validation_and_disabled(client):
    from app.main import app

    assert (await start(client, phone="0812345678")).status_code == 422
    assert (await start(client, amount=5)).status_code == 422
    assert (await start(client, amount=10_000_000)).status_code == 422
    r = await client.post("/api/contributions/mpesa/stk", json={"phone": "0712345678", "amount": 100, "name": "A"})
    assert r.status_code == 422  # missing Idempotency-Key
    app.state.settings.mpesa_enabled = False
    try:
        assert (await start(client)).status_code == 503
    finally:
        app.state.settings.mpesa_enabled = True


async def test_unreachable_mpesa_marks_failed(client):
    from app.main import app

    app.state.daraja.push_error = DarajaError("down", sent=False)
    r = await start(client)
    assert r.status_code == 502
    assert "No money was taken" in r.json()["detail"]


async def test_per_phone_limit(client):
    for _ in range(3):
        assert (await start(client, phone="0733111222")).status_code == 202
    assert (await start(client, phone="0733111222")).status_code == 429


async def test_reconciler_settles_missing_callbacks(client):
    from app.main import app, db
    from app.models import Contribution
    from app.worker import run_once
    from memorial_common.db import utcnow

    ok = (await start(client, phone="0744000001")).json()["id"]
    slow = (await start(client, phone="0744000002")).json()["id"]
    async with db.sessionmaker() as s:
        await s.execute(
            update(Contribution).where(Contribution.id == ok).values(created_at=utcnow() - timedelta(minutes=2))
        )
        await s.execute(
            update(Contribution).where(Contribution.id == slow).values(created_at=utcnow() - timedelta(minutes=30))
        )
        await s.commit()
    fake = app.state.daraja
    fake.query_state = "success"
    async with db.sessionmaker() as s:
        await s.execute(update(Contribution).where(Contribution.id == slow).values(last_checked_at=utcnow()))
        await s.commit()
    await run_once(db, fake, app.state.settings, batch=1)  # oldest-checked first: `ok`
    assert await status(client, ok) == "confirmed"
    fake.query_state = "processing"
    await run_once(db, fake, app.state.settings)
    assert await status(client, slow) == "expired"


async def test_treasurer_ledger(client):
    r = await client.post(
        "/api/contributions/manual",
        json={"method": "mpesa_manual", "amount": 2000, "name": "=HYPERLINK(evil)", "reference": "tab12cd345"},
        headers=TREASURER,
    )
    assert r.status_code == 201, r.text
    dup = await client.post(
        "/api/contributions/manual",
        json={"method": "mpesa_manual", "amount": 2000, "name": "Again", "reference": "TAB12CD345"},
        headers=TREASURER,
    )
    assert dup.status_code == 409
    assert (await client.get("/api/contributions/ledger", headers=EDITOR)).status_code == 403
    led = await client.get("/api/contributions/ledger", headers=TREASURER)
    assert led.status_code == 200 and led.json()["total_confirmed"] >= 2000
    csv = await client.get("/api/contributions/ledger.csv", headers=TREASURER)
    assert "'=HYPERLINK(evil)" in csv.text
    detail = await client.get(f"/api/contributions/ledger/{r.json()['id']}", headers=TREASURER)
    assert detail.json()["events"][0]["to_status"] == "confirmed"


async def test_verified_mpesa_payment_cannot_be_voided(client):
    cid = (await start(client, phone="0755000001")).json()["id"]
    await client.post(CB, json=callback_body(await checkout_of(cid), receipt=receipt()))
    r = await client.post(
        f"/api/contributions/{cid}/review", json={"to": "void", "note": "Trying to remove it"}, headers=TREASURER
    )
    assert r.status_code == 409


@respx.mock
async def test_daraja_client_token_cache_and_query_mapping():
    from app.config import Settings

    st = Settings(mpesa_consumer_key="k", mpesa_consumer_secret="s", mpesa_shortcode="174379", mpesa_passkey="p")
    token = respx.get("https://sandbox.safaricom.co.ke/oauth/v1/generate").mock(
        return_value=httpx.Response(200, json={"access_token": "abc", "expires_in": "3599"})
    )
    query = respx.post("https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query")
    query.side_effect = [
        httpx.Response(500, json={"errorCode": "500.001.1001", "errorMessage": "The transaction is being processed"}),
        httpx.Response(200, json={"ResultCode": "1032", "ResultDesc": "Request cancelled by user"}),
    ]
    c = DarajaClient(st)
    assert (await c.stk_query("ws_1"))["state"] == "processing"
    assert (await c.stk_query("ws_1"))["state"] == "cancelled"
    assert token.call_count == 1
    sent = query.calls[0].request
    assert sent.headers["authorization"] == "Bearer abc"
    await c.close()


@respx.mock
async def test_daraja_stk_push_payload_and_errors():
    import base64

    from app.config import Settings

    st = Settings(
        mpesa_consumer_key="k",
        mpesa_consumer_secret="s",
        mpesa_shortcode="174379",
        mpesa_passkey="pk",
        mpesa_callback_token="tok",
        site_origin="https://martha.example",
    )
    respx.get("https://sandbox.safaricom.co.ke/oauth/v1/generate").mock(
        return_value=httpx.Response(200, json={"access_token": "abc", "expires_in": "3599"})
    )
    push = respx.post("https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest")
    push.side_effect = [
        httpx.Response(200, json={"ResponseCode": "0", "CheckoutRequestID": "ws_CO_1", "MerchantRequestID": "m1"}),
        httpx.Response(400, json={"errorMessage": "Bad Request - Invalid PhoneNumber"}),
        httpx.TimeoutException("slow"),
    ]
    c = DarajaClient(st)
    data = await c.stk_push(phone="254712345678", amount=500, reference="MarthaOngosiLong", description="Contribution")
    assert data["CheckoutRequestID"] == "ws_CO_1"
    import json as _json

    sent = _json.loads(push.calls[0].request.content)
    assert sent["Amount"] == 500 and sent["PartyB"] == "174379" and sent["AccountReference"] == "MarthaOngosi"
    assert sent["CallBackURL"] == "https://martha.example/api/contributions/mpesa/callback/tok"
    assert base64.b64decode(sent["Password"]).decode() == "174379pk" + sent["Timestamp"]
    try:
        await c.stk_push(phone="254712345678", amount=500, reference="r", description="d")
        raise AssertionError("expected DarajaError")
    except DarajaError as e:
        assert e.sent is False
    try:
        await c.stk_push(phone="254712345678", amount=500, reference="r", description="d")
        raise AssertionError("expected DarajaError")
    except DarajaError as e:
        assert e.sent is None  # unknown: the reconciler and the statement settle it
    await c.close()


@respx.mock
async def test_daraja_token_failure_is_reported():
    from app.config import Settings

    respx.get("https://sandbox.safaricom.co.ke/oauth/v1/generate").mock(return_value=httpx.Response(401))
    c = DarajaClient(Settings(mpesa_consumer_key="k", mpesa_consumer_secret="bad"))
    try:
        await c.token()
        raise AssertionError("expected DarajaError")
    except DarajaError as e:
        assert e.sent is False
    await c.close()


async def test_slow_mpesa_keeps_payment_pending_then_expires(client):
    from app.main import app, db
    from app.models import Contribution
    from app.worker import run_once
    from memorial_common.db import utcnow

    app.state.daraja.push_error = DarajaError("timeout", sent=None)
    r = await start(client, phone="0766000001")
    assert r.status_code == 202 and r.json()["status"] == "pending"
    cid = r.json()["id"]
    async with db.sessionmaker() as s:
        await s.execute(
            update(Contribution).where(Contribution.id == cid).values(created_at=utcnow() - timedelta(minutes=40))
        )
        await s.commit()
    await run_once(db, app.state.daraja, app.state.settings, batch=100)
    assert await status(client, cid) == "expired"


async def test_status_and_ledger_lookups(client):
    assert (await client.get("/api/contributions/" + "0" * 32 + "/status")).status_code == 404
    assert (await client.get("/api/contributions/short/status")).status_code == 404
    assert (await client.get("/api/contributions/ledger/missing", headers=TREASURER)).status_code == 404
    r = await client.post(
        "/api/contributions/missing/review", json={"to": "void", "note": "nothing here"}, headers=TREASURER
    )
    assert r.status_code == 404
    bank = await client.post(
        "/api/contributions/manual", json={"method": "bank", "amount": 100, "name": "A"}, headers=TREASURER
    )
    assert bank.status_code == 422
    led = await client.get("/api/contributions/ledger", params={"status": "confirmed"}, headers=TREASURER)
    assert all(r["status"] == "confirmed" for r in led.json()["rows"])


async def test_gauges_update():
    from app.main import app, db
    from app.worker import confirmed_gauge, update_gauges

    await update_gauges(db, app.state.settings)
    assert confirmed_gauge._value.get() >= 0
