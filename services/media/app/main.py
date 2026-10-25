from memorial_common.app import create_app
from memorial_common.db import Database

from .config import get_settings
from .routes import router
from .storage import make_storage

settings = get_settings()
db = Database(settings.database_url)
app = create_app(settings, title="Memorial media", db=db)
app.state.storage = make_storage(settings)
app.include_router(router)
