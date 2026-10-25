import os
import sys
import tempfile
from pathlib import Path

import pytest

from memorial_common.testing import make_keypair

PRIVATE, PUBLIC = make_keypair()
_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL=f"sqlite+aiosqlite:///{_tmp}/memorial.db",
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
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", headers={"origin": "http://testserver"}
    ) as c:
        yield c


from memorial_common.testing import mint  # noqa: E402


def auth(user_id: str, *roles: str) -> dict:
    return {"authorization": f"Bearer {mint(PRIVATE, user_id, list(roles))}"}
