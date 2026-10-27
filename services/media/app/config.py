from functools import lru_cache

from memorial_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "media"

    storage_backend: str = "local"  # "s3" in production (MinIO or any S3-compatible store)
    local_dir: str = "./media-data"
    s3_endpoint: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "memorial-media"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    max_upload_mb: int = 20
    max_pixels: int = 60_000_000
    max_dimension: int = 2400
    thumb_dimension: int = 640
    jpeg_quality: int = 85

    # Photos dropped in the pCloud "Add to Gallery" folder are fetched here (by the inbox service)
    # and imported for review. Empty turns the import off.
    inbox_dir: str = ""
    inbox_poll_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
