"""Safaricom Daraja (M-Pesa Express / STK Push) client."""

import asyncio
import base64
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .config import Settings

log = logging.getLogger("daraja")
NAIROBI = ZoneInfo("Africa/Nairobi")


class DarajaError(Exception):
    """The request failed or the answer was not usable. `sent` is False when
    we know for certain no prompt reached the customer's phone."""

    def __init__(self, message: str, *, sent: bool | None = None) -> None:
        super().__init__(message)
        self.sent = sent


class DarajaClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.s = settings
        self.http = httpx.AsyncClient(
            base_url=settings.daraja_base, timeout=httpx.Timeout(20.0, connect=5.0), transport=transport
        )
        self._token: str | None = None
        self._token_exp = 0.0
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        await self.http.aclose()

    async def token(self) -> str:
        async with self._lock:
            if self._token and time.monotonic() < self._token_exp:
                return self._token
            try:
                r = await self.http.get(
                    "/oauth/v1/generate",
                    params={"grant_type": "client_credentials"},
                    auth=(self.s.mpesa_consumer_key, self.s.mpesa_consumer_secret),
                )
                r.raise_for_status()
                data = r.json()
            except (httpx.HTTPError, ValueError) as e:
                raise DarajaError(f"Could not get M-Pesa access token: {e}", sent=False) from e
            self._token = data["access_token"]
            self._token_exp = time.monotonic() + int(data.get("expires_in", 3599)) - 120
            return self._token

    def _password(self) -> tuple[str, str]:
        ts = datetime.now(NAIROBI).strftime("%Y%m%d%H%M%S")
        raw = f"{self.s.mpesa_shortcode}{self.s.mpesa_passkey}{ts}".encode()
        return base64.b64encode(raw).decode(), ts

    async def stk_push(self, *, phone: str, amount: int, reference: str, description: str) -> dict:
        password, ts = self._password()
        payload = {
            "BusinessShortCode": self.s.mpesa_shortcode,
            "Password": password,
            "Timestamp": ts,
            "TransactionType": self.s.mpesa_transaction_type,
            "Amount": amount,
            "PartyA": phone,
            "PartyB": self.s.mpesa_party_b or self.s.mpesa_shortcode,
            "PhoneNumber": phone,
            "CallBackURL": self.s.callback_url,
            "AccountReference": reference[:12],
            "TransactionDesc": description[:13],
        }
        headers = {"Authorization": f"Bearer {await self.token()}"}
        try:
            r = await self.http.post("/mpesa/stkpush/v1/processrequest", json=payload, headers=headers)
        except httpx.TimeoutException as e:
            # The prompt may or may not have been sent. We cannot tell.
            raise DarajaError("M-Pesa did not answer in time", sent=None) from e
        except httpx.HTTPError as e:
            raise DarajaError(f"Could not reach M-Pesa: {e}", sent=False) from e
        try:
            data = r.json()
        except ValueError as e:
            raise DarajaError(f"Unexpected M-Pesa response ({r.status_code})", sent=None) from e
        if r.status_code != 200 or str(data.get("ResponseCode")) != "0":
            msg = data.get("errorMessage") or data.get("ResponseDescription") or f"HTTP {r.status_code}"
            raise DarajaError(str(msg), sent=False)
        return data

    async def stk_query(self, checkout_request_id: str) -> dict:
        """Ask Safaricom for the definitive result of an STK push.

        Returns {"state": "success" | "failed" | "cancelled" | "timeout" | "processing", "code": str, "desc": str}.
        """
        password, ts = self._password()
        payload = {
            "BusinessShortCode": self.s.mpesa_shortcode,
            "Password": password,
            "Timestamp": ts,
            "CheckoutRequestID": checkout_request_id,
        }
        headers = {"Authorization": f"Bearer {await self.token()}"}
        try:
            r = await self.http.post("/mpesa/stkpushquery/v1/query", json=payload, headers=headers)
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise DarajaError(f"Status query failed: {e}") from e
        if "ResultCode" in data:
            code = str(data["ResultCode"])
            return {"state": classify(code), "code": code, "desc": str(data.get("ResultDesc", ""))}
        err = str(data.get("errorMessage", ""))
        if "being processed" in err.lower() or str(data.get("errorCode", "")).startswith("500.001.1001"):
            return {"state": "processing", "code": str(data.get("errorCode", "")), "desc": err}
        raise DarajaError(f"Status query error: {err or r.status_code}")


def classify(result_code: str) -> str:
    if result_code == "0":
        return "success"
    if result_code == "1032":
        return "cancelled"
    if result_code in ("1037", "1019"):
        return "timeout"
    return "failed"
