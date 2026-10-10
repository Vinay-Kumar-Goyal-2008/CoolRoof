"""BlobStore: object storage. Local = ``./data/blobs`` folder, AWS = S3.

Keys use forward slashes and the spec's prefixes
(``raw/ curated/ tiles/ models/ rules/ audio/ exports/``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packages.core.errors import NotFoundError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

__all__ = ["BlobStore", "LocalBlobStore", "S3BlobStore"]


class BlobStore(ABC):
    """Interface for binary object storage."""

    @abstractmethod
    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Object bytes; raises ``NotFoundError`` if absent."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def list(self, prefix: str = "") -> list[str]:
        """Keys under ``prefix``, sorted."""

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def uri(self, key: str) -> str:
        """A URI GDAL/rasterio can open directly (local path or ``s3://``)."""

    @abstractmethod
    def presigned_url(self, key: str, expires_s: int) -> str:
        """Time-limited download URL (local: ``file://`` URL, expiry not enforced)."""

    def put_text(self, key: str, text: str, *, content_type: str = "text/plain") -> None:
        self.put(key, text.encode("utf-8"), content_type=f"{content_type}; charset=utf-8")

    def get_text(self, key: str) -> str:
        return self.get(key).decode("utf-8")


class LocalBlobStore(BlobStore):
    """Filesystem implementation rooted at a directory."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / key.lstrip("/")).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError(f"key escapes blob root: {key!r}")
        return path

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise NotFoundError(f"blob not found: {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str = "") -> list[str]:
        base = self._root
        return sorted(
            p.relative_to(base).as_posix()
            for p in base.rglob("*")
            if p.is_file() and p.relative_to(base).as_posix().startswith(prefix)
        )

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def uri(self, key: str) -> str:
        return str(self._path(key))

    def presigned_url(self, key: str, expires_s: int) -> str:
        return self._path(key).as_uri()


class S3BlobStore(BlobStore):
    """Amazon S3 implementation."""

    def __init__(self, bucket: str, client: S3Client | None = None) -> None:
        import boto3

        self._bucket = bucket
        self._s3: S3Client = client or boto3.client("s3")

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        extra: dict[str, Any] = {"ContentType": content_type} if content_type else {}
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data, **extra)

    def get(self, key: str) -> bytes:
        try:
            obj = self._s3.get_object(Bucket=self._bucket, Key=key)
        except self._s3.exceptions.NoSuchKey as exc:
            raise NotFoundError(f"blob not found: {key}") from exc
        return obj["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
        except ClientError:
            return False
        return True

    def list(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return sorted(keys)

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)

    def uri(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    def presigned_url(self, key: str, expires_s: int) -> str:
        return self._s3.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=expires_s
        )
