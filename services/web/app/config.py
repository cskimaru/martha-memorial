from functools import lru_cache

from memorial_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "web"
    memorial_url: str = "http://memorial:8000"
    page_cache_seconds: float = 15.0
    upstream_timeout_seconds: float = 4.0
    # Added to /static URLs so browsers fetch new styles after an update. Empty: derived from the files.
    asset_version: str = ""
    # Private preview before launch: shows a "not yet public" bar with a colour switcher.
    # The gateway adds a password in this mode (see docs/runbook.md).
    site_preview: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
