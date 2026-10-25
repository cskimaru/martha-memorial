from functools import lru_cache

from memorial_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "web"
    memorial_url: str = "http://memorial:8000"
    contributions_url: str = "http://contributions:8000"
    page_cache_seconds: float = 15.0
    upstream_timeout_seconds: float = 4.0
    asset_version: str = "1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
