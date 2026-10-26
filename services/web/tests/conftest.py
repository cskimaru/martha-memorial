import os
import sys
from pathlib import Path

import pytest

os.environ.update(
    SITE_ORIGIN="http://testserver",
    ENVIRONMENT="test",
    MEMORIAL_URL="http://memorial.internal",
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c
