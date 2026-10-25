from functools import lru_cache

from memorial_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "memorial"
    # Tributes from visitors who aren't signed in wait for a family editor to approve them.
    moderate_public_tributes: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
