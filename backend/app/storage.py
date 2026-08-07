"""
طبقة التخزين المجردة — تدعم القرص المحلي و Cloudflare R2 (S3-compatible)
"""
import os
import logging
from pathlib import Path
from typing import Optional
from abc import ABC, abstractmethod

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """ارفع ملف وأعد المفتاح/المسار."""
        ...

    @abstractmethod
    def put_streaming(self, key: str, file_obj, content_type: str = "application/octet-stream") -> str:
        """ارفع ملف من file-like object بدون تحميله بالكامل في الذاكرة."""
        ...

    @abstractmethod
    def get_presigned_upload_url(self, key: str, content_type: str, expires: int = 3600) -> dict:
        """أعد presigned PUT URL للرفع المباشر من المتصفح.

        ملاحظة: R2 لا يدعم presigned POST (يعيد 501 NotImplemented) — PUT هو
        آلية الرفع المباشر الوحيدة. الحجم لا يمكن حراسته وقت الإصدار؛ التحقق
        الفعلي من الحجم والمحتوى يتم في /videos/{id}/complete عبر head_object."""
        ...

    @abstractmethod
    def head_object(self, key: str) -> Optional[dict]:
        """Return {size, content_type, etag} or None if not found."""
        ...

    @abstractmethod
    def get_presigned_read_url(self, key: str, expires: int = 3600, is_public: bool = True) -> str:
        """أعد presigned URL للقراءة مع انتهاء صلاحية. لا تستخدم روابط عامة دائمة."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def get_local_path(self, key: str) -> Optional[str]:
        """أعد المسار المحلي إن كان التخزين محلياً. None إذا كان سحابياً."""
        ...


class LocalStorage(StorageBackend):
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _full_path(self, key: str) -> str:
        if "\x00" in key:
            raise HTTPException(status_code=400, detail="Invalid file path")
        path = (Path(self.base_dir) / key).resolve()
        base = Path(self.base_dir).resolve()
        if not path.is_relative_to(base):
            raise HTTPException(status_code=400, detail="Invalid file path")
        return str(path)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._full_path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return key

    def put_streaming(self, key: str, file_obj, content_type: str = "application/octet-stream") -> str:
        path = self._full_path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            while chunk := file_obj.read(1024 * 1024):
                f.write(chunk)
        return key

    def get_presigned_upload_url(self, key: str, content_type: str, expires: int = 3600) -> dict:
        return {
            "url": f"/api/videos/upload-direct?key={key}",
            "method": "PUT",
            "headers": {"Content-Type": content_type},
        }

    def head_object(self, key: str) -> Optional[dict]:
        path = self._full_path(key)
        if not os.path.exists(path):
            return None
        st = os.stat(path)
        return {"size": st.st_size, "content_type": "application/octet-stream", "etag": None}

    def get_presigned_read_url(self, key: str, expires: int = 3600, is_public: bool = True) -> str:
        raise NotImplementedError("Local file serving not supported — use R2Storage")

    def delete(self, key: str) -> None:
        path = self._full_path(key)
        if os.path.exists(path):
            os.remove(path)

    def exists(self, key: str) -> bool:
        return os.path.exists(self._full_path(key))

    def get_local_path(self, key: str) -> Optional[str]:
        path = self._full_path(key)
        return path if os.path.exists(path) else None


class R2Storage(StorageBackend):
    """Cloudflare R2 — S3-compatible with zero egress fees."""

    def __init__(self):
        import boto3
        self.bucket = os.environ["R2_BUCKET_NAME"]
        self.client = boto3.client(
            "s3",
            endpoint_url=os.environ["R2_ENDPOINT"],
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
        )

    def download(self, key: str, local_path: str) -> None:
        """حمّل ملفاً من R2 إلى مسار محلي."""
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.client.download_file(self.bucket, key, local_path)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def put_streaming(self, key: str, file_obj, content_type: str = "application/octet-stream") -> str:
        """Upload via multipart-like streaming to avoid loading entire file into memory."""
        from boto3.s3.transfer import TransferConfig
        config = TransferConfig(multipart_threshold=8 * 1024 * 1024, multipart_chunksize=8 * 1024 * 1024)
        self.client.upload_fileobj(file_obj, self.bucket, key, ExtraArgs={"ContentType": content_type}, Config=config)
        return key

    def get_presigned_upload_url(self, key: str, content_type: str, expires: int = 3600) -> dict:
        """Presigned PUT URL for browser-direct upload to R2.

        R2 does not implement presigned POST (returns 501 NotImplemented), so PUT
        is the only direct-upload mechanism. Content-Length cannot be constrained
        on a presigned PUT, so size enforcement happens afterwards in
        POST /videos/{id}/complete via head_object."""
        url = self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires,
        )
        return {"url": url, "method": "PUT", "headers": {"Content-Type": content_type}}

    def head_object(self, key: str) -> Optional[dict]:
        try:
            r = self.client.head_object(Bucket=self.bucket, Key=key)
            return {
                "size": r["ContentLength"],
                "content_type": r.get("ContentType"),
                "etag": r.get("ETag"),
            }
        except self.client.exceptions.ClientError:
            return None
        except Exception:
            return None

    def get_presigned_read_url(self, key: str, expires: int = 3600, is_public: bool = True) -> str:
        """Always generate a presigned URL with expiration.
        Never use permanent public URLs — even for public videos — because
        the R2 bucket has Public Access enabled and raw URLs bypass all
        application-level auth/ownership checks."""
        if not key:
            return None
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def get_local_path(self, key: str) -> Optional[str]:
        return None  # سحابي — لا يوجد مسار محلي


def get_storage() -> StorageBackend:
    """يُنشئ طبقة التخزين المناسبة حسب البيئة."""
    r2_bucket = os.environ.get("R2_BUCKET_NAME")
    if r2_bucket:
        logger.info("Using Cloudflare R2 storage")
        return R2Storage()

    from app.config import settings
    logger.info(f"Using local storage: {settings.UPLOAD_DIR}")
    return LocalStorage(settings.UPLOAD_DIR)


# Singleton
_storage: Optional[StorageBackend] = None

def storage() -> StorageBackend:
    global _storage
    if _storage is None:
        _storage = get_storage()
    return _storage
