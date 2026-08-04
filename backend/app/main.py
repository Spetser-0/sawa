"""
سوى — Backend (Production Ready)
"""
import os
import sys
import logging
import traceback
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.responses import Response

from app.limiter import limiter
from app.exceptions import APIException

from app.database import engine, Base
from app.routers import videos, auth, transcripts, payments, search, comments, analytics
from app.config import settings

# ── Sentry (اختياري — لمراقبة الأخطاء) ──────────────
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
        environment=settings.ENVIRONMENT,
    )

# ── Structured Logging ────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sawa")

# ── Startup Diagnostic: log storage config ────────────
def _log_storage_config():
    r2_bucket = os.environ.get("R2_BUCKET_NAME", "")
    r2_endpoint = os.environ.get("R2_ENDPOINT", "")
    r2_key_id = os.environ.get("R2_ACCESS_KEY_ID", "")
    r2_secret = os.environ.get("R2_SECRET_ACCESS_KEY", "")

    if r2_bucket:
        missing = []
        if not r2_endpoint:
            missing.append("R2_ENDPOINT")
        if not r2_key_id:
            missing.append("R2_ACCESS_KEY_ID")
        if not r2_secret:
            missing.append("R2_SECRET_ACCESS_KEY")
        if missing:
            logger.error(f"❌ R2_BUCKET_NAME is set but MISSING: {', '.join(missing)} — "
                         "R2Storage.__init__ will raise KeyError on startup!")
        else:
            logger.info(f"✅ R2 configured: bucket={r2_bucket}, endpoint={r2_endpoint[:40]}..., "
                        f"presigned-only mode")
    else:
        logger.info(f"ℹ️  R2_BUCKET_NAME not set — using local storage: {settings.UPLOAD_DIR}")

    logger.info(f"   ENVIRONMENT={settings.ENVIRONMENT}, UPLOAD_DIR={settings.UPLOAD_DIR}")

_log_storage_config()

# ── Startup Diagnostic: log dependency versions ───────
def _log_dependency_versions():
    deps = ["fastapi", "starlette", "python_multipart", "uvicorn",
            "sqlalchemy", "pydantic", "boto3", "slowapi"]
    for dep in deps:
        try:
            mod = __import__(dep)
            ver = getattr(mod, "__version__", getattr(mod, "VERSION", "?"))
            if isinstance(ver, tuple):
                ver = ".".join(str(x) for x in ver)
            logger.info(f"   {dep}=={ver}")
        except ImportError:
            logger.warning(f"   {dep}: NOT INSTALLED")
        except Exception as e:
            logger.warning(f"   {dep}: version check failed ({e})")

_log_dependency_versions()

# ── Rate Limiter (shared across routers) ─────────────

app = FastAPI(
    title="Sawa سوى",
    description="بديل Loom العربي — API",
    version="2.0.0",
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _safe(obj):
    """يحوّل أي قيمة bytes إلى نص عشان JSON ما ينكسر"""
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe(v) for v in obj]
    return obj


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    PASSWORD_ERROR_TYPES = {"string_too_short", "string_too_long", "value_error"}
    for err in exc.errors():
        loc = err.get("loc", ())
        etype = err.get("type", "")
        if "password" in loc and etype in PASSWORD_ERROR_TYPES:
            if etype == "value_error":
                ctx_msg = str(err.get("ctx", {}).get("error", ""))
                detail = ctx_msg if ctx_msg else "كلمة المرور طويلة جداً"
            else:
                detail = "كلمة المرور يجب أن تكون 8 أحرف على الأقل"
            return JSONResponse(status_code=422, content={"detail": detail, "error_code": "VALIDATION_ERROR"})

    safe_errors = jsonable_encoder(_safe(exc.errors()))
    return JSONResponse(
        status_code=422,
        content={"detail": safe_errors, "error_code": "VALIDATION_ERROR"},
    )


@app.exception_handler(APIException)
async def api_exception_handler(request: Request, exc: APIException):
    content = {"detail": exc.detail}
    if exc.error_code:
        content["error_code"] = exc.error_code
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=exc.headers,
    )

# ══════════════════════════════════════════════════════
#  CORS — المُصلح 🔧
# ══════════════════════════════════════════════════════
ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    # ← أضف نطاق فرونتندك مباشرة هنا (احتياط)
    "https://sawa-plum.vercel.app",
}

# من متغير البيئة FRONTEND_URL
frontend_url = os.getenv("FRONTEND_URL", "").strip()
if frontend_url:
    ALLOWED_ORIGINS.add(frontend_url.rstrip("/"))

# من متغير إضافي CORS_ORIGINS (لأكثر من نطاق)
extra_origins = os.getenv("CORS_ORIGINS", "")
if extra_origins:
    for origin in extra_origins.split(","):
        origin = origin.strip()
        if origin:
            ALLOWED_ORIGINS.add(origin)

cors_origins = sorted(o for o in ALLOWED_ORIGINS if o)

logger.info(f"🌐 CORS origins: {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-CSRF-Token",
        "X-Requested-With",
        "Accept",
        "Accept-Language",
        "Accept-Encoding",
        "Origin",
        "Referer",
        "User-Agent",
    ],
    expose_headers=["Set-Cookie", "X-Request-Id"],
    max_age=600,  # cache preflight لـ 10 دقائق
)


# ── Error Safety Net (pure ASGI — no body buffering) ──
class ErrorSafetyMiddleware:
    """ Catches unhandled exceptions, logs to Sentry, returns 500. """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            logger.exception("Unhandled exception in request handler")
            sentry_sdk.capture_exception(exc)
            body = b'{"detail":"Internal Server Error"}'
            response = Response(status_code=500, content=body, media_type="application/json")
            await response(scope, receive, send)

app.add_middleware(ErrorSafetyMiddleware)


# ── Error Logger (logs full traceback for ALL 500s) ───
class ErrorLoggerMiddleware:
    """Logs full traceback + request details for any unhandled exception."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        try:
            await self.app(scope, receive, send)
        except Exception:
            method = scope.get("method", "?")
            path = scope.get("path", "?")
            client = scope.get("client", ("?", 0))
            logger.error(
                f"💥 UNHANDLED EXCEPTION on {method} {path} from {client[0]}:{client[1]}\n"
                f"{traceback.format_exc()}"
            )
            raise

app.add_middleware(ErrorLoggerMiddleware)

# ── Upload Dir (ensure exists) ────────────────────────
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)


def _sweep_stale_uploads():
    """احذف الملفات في UPLOAD_DIR الأقدم من 6 ساعات عند بدء التشغيل.
    يمنع تراكم ملفات tmp المؤقتة التي تسرّبت بسبب أخطاء سابقة."""
    import time
    cutoff = time.time() - 6 * 3600
    try:
        for fname in os.listdir(settings.UPLOAD_DIR):
            fpath = os.path.join(settings.UPLOAD_DIR, fname)
            if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                try:
                    os.remove(fpath)
                    logger.info(f"🧹 Swept stale upload file: {fname}")
                except Exception as e:
                    logger.warning(f"Could not remove stale file {fname}: {e}")
    except Exception as e:
        logger.warning(f"Startup upload sweep failed: {e}")


_sweep_stale_uploads()

# ── Routers ───────────────────────────────────────────
app.include_router(auth.router,        prefix="/api/auth",
                   tags=["Auth"])
app.include_router(videos.router,      prefix="/api/videos",
                   tags=["Videos"])
app.include_router(transcripts.router,
                   prefix="/api/transcripts", tags=["Transcripts"])
app.include_router(payments.router,
                   prefix="/api/payments",    tags=["Payments"])
app.include_router(search.router,      prefix="/api/search",
                   tags=["Search"])
app.include_router(comments.router,    prefix="/api",
                   tags=["Comments"])
app.include_router(analytics.router,   prefix="/api/videos",
                   tags=["Analytics"])


@app.get("/")
def root():
    return {"message": "سوى API 🎙️", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/deps")
def health_deps():
    """يتحقق من توفر Redis و R2 وقاعدة البيانات ويُعيد حالة كل منهما.
    مفيد للتشخيص السريع في الإنتاج بدلاً من قراءة السجلات."""
    status = {"redis": False, "r2": False, "db": False}

    # ── Redis ping ──
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2)
        r.ping()
        status["redis"] = True
    except Exception as e:
        logger.warning(f"health/deps: Redis ping failed: {e}")

    # ── R2 / storage ping ──
    try:
        from app.storage import storage
        store = storage()
        # head_object on a sentinel key — returns None (not found) or metadata, both are fine
        store.head_object("__health_check__")
        status["r2"] = True
    except Exception as e:
        logger.warning(f"health/deps: R2/storage ping failed: {e}")

    # ── DB ping ──
    try:
        from sqlalchemy import text as sa_text
        from app.database import SessionLocal
        with SessionLocal() as db_session:
            db_session.execute(sa_text("SELECT 1"))
        status["db"] = True
    except Exception as e:
        logger.warning(f"health/deps: DB ping failed: {e}")

    return status