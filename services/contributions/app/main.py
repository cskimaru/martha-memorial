from fastapi import FastAPI

from memorial_common.app import create_app
from memorial_common.db import Database

from .config import get_settings
from .daraja import DarajaClient
from .routes import router

settings = get_settings()
db = Database(settings.database_url)


async def shutdown(app: FastAPI) -> None:
    await app.state.daraja.close()


app = create_app(settings, title="Memorial contributions", db=db, on_shutdown=shutdown)
app.state.daraja = DarajaClient(settings)
app.include_router(router)
