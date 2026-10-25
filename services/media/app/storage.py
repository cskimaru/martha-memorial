"""Object storage: S3-compatible (MinIO) in production, local disk for development."""

from pathlib import Path
from typing import Protocol

from starlette.concurrency import run_in_threadpool

from .config import Settings


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes | None: ...
    async def delete(self, key: str) -> None: ...
    async def ping(self) -> bool: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("Invalid storage key")
        return p

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)

    async def get(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.is_file() else None

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def ping(self) -> bool:
        return self.root.is_dir()


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(retries={"max_attempts": 5, "mode": "standard"}, connect_timeout=5, read_timeout=30),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await run_in_threadpool(
            self.client.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    async def get(self, key: str) -> bytes | None:
        def _get() -> bytes | None:
            try:
                return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            except self.client.exceptions.NoSuchKey:
                return None

        return await run_in_threadpool(_get)

    async def delete(self, key: str) -> None:
        await run_in_threadpool(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def ping(self) -> bool:
        try:
            await run_in_threadpool(self.client.head_bucket, Bucket=self.bucket)
            return True
        except Exception:
            return False


def make_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage(settings)
    return LocalStorage(settings.local_dir)
