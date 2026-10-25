import os
import sys
import tempfile
from pathlib import Path

import pytest

from memorial_common.testing import make_keypair

PRIVATE, PUBLIC = make_keypair()
_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL=f"sqlite+aiosqlite:///{_tmp}/contrib.db",
    MPESA_ENABLED="true",
    MPESA_SHORTCODE="174379",
    MPESA_PASSKEY="testpasskey",
    MPESA_CONSUMER_KEY="ck",
    MPESA_CONSUMER_SECRET="cs",
    MPESA_CALLBACK_TOKEN="cb-secret-token-1234567890",
    PENDING_TIMEOUT_MINUTES="15",
    JWT_PUBLIC_KEY=PUBLIC,
    SITE_ORIGIN="http://testserver",
    ENVIRONMENT="test",
)
SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated():
    cwd = os.getcwd()
    os.chdir(SERVICE_DIR)
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        os.chdir(cwd)


@pytest.fixture
async def client():
    from app.main import app

    app.state.limiter._mem.clear()
    app.state.daraja = FakeDaraja()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", headers={"origin": "http://testserver"}
    ) as c:
        yield c


from memorial_common.testing import mint  # noqa: E402


def auth(user_id: str, *roles: str) -> dict:
    return {"authorization": f"Bearer {mint(PRIVATE, user_id, list(roles))}"}


class FakeDaraja:
    """Stands in for Safaricom. Tests set `query_state` to decide what M-Pesa reports."""

    def __init__(self):
        self.pushes = []
        self.query_state = "success"
        self.push_error = None
        self._n = 0

    async def stk_push(self, *, phone, amount, reference, description):
        if self.push_error:
            raise self.push_error
        self._n += 1
        self.pushes.append({"phone": phone, "amount": amount})
        return {"CheckoutRequestID": f"ws_CO_{self._n:04d}_{id(self)}", "MerchantRequestID": "m", "ResponseCode": "0"}

    async def stk_query(self, checkout_request_id):
        codes = {"success": "0", "failed": "1", "cancelled": "1032", "timeout": "1037", "processing": ""}
        return {"state": self.query_state, "code": codes[self.query_state], "desc": self.query_state}

    async def close(self):
        pass
