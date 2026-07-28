"""
الإعدادات المركزية لمشروع سوى
"""
from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional


class Settings(BaseSettings):
    # ── قاعدة البيانات ──────────────────────────────
    DATABASE_URL: str = "sqlite:///./sawa.db"

    # ── التخزين ──────────────────────────────────────
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 500
    MAX_UPLOAD_BYTES: int = 2 * 1024 * 1024 * 1024   # 2 GB hard cap (enforced by R2 presigned POST)
    ALLOWED_EXTENSIONS: list = ["mp4", "webm", "mov", "mp3", "wav", "m4a", "avi", "mkv", "ogg", "flac"]

    # ── نموذج Whisper ────────────────────────────────
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"

    # ── المصادقة ─────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    COOKIE_SECURE: bool = False

    # ── حدود الخطط ──────────────────────────────────
    FREE_MAX_VIDEOS: int = 25
    FREE_MAX_DURATION_SECONDS: int = 300
    PRO_MAX_DURATION_SECONDS: int = 3600
    PENDING_UPLOAD_TTL_MINUTES: int = 60

    # ── مفاتيح خارجية ────────────────────────────────
    ANTHROPIC_API_KEY: Optional[str] = None
    HUGGINGFACE_TOKEN: Optional[str] = None
    CRYPTOMUS_MERCHANT_ID: Optional[str] = None
    CRYPTOMUS_API_KEY: Optional[str] = None

    # ── مزودي التفريغ ────────────────────────────────
    TRANSCRIPTION_PROVIDER: str = "gemini"  # gemini | groq | local
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    # ── البريد الإلكتروني ───────────────────────────
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None
    MAIL_FROM: Optional[str] = None
    MAIL_SERVER: str = "smtp.gmail.com"

    # ── روابط التطبيق والبيئة ────────────────────────
    FRONTEND_URL: str = "http://localhost:3000"
    BACKEND_URL: str = "http://localhost:8000"
    ENVIRONMENT: str = "development"

    # ── Celery & Redis ──────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    @model_validator(mode="after")
    def _setup_celery(self):
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = self.REDIS_URL
        return self

    @model_validator(mode="after")
    def _auto_cookie_secure(self):
        if self.ENVIRONMENT == "production":
            self.COOKIE_SECURE = True
        return self

    # ── Cloudflare R2 (اختياري) ──────────────────────
    R2_BUCKET_NAME: Optional[str] = None
    R2_ENDPOINT: Optional[str] = None
    R2_ACCESS_KEY_ID: Optional[str] = None
    R2_SECRET_ACCESS_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"   # ← يتجاهل أي متغيرات إضافية في .env بدل رفع خطأ


settings = Settings()
