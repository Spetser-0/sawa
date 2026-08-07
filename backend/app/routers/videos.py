"""
مسارات الفيديوهات — رفع، جلب، حذف، بث، مشاركة محمية، HLS
"""
import os
import uuid
import struct
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import aiofiles

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text
from pydantic import BaseModel, Field
from app.limiter import limiter

from app.database import get_db, Video, Transcript, TranscriptStatus, User
from app.exceptions import APIException
from app.auth import get_current_user, require_auth, hash_password, verify_password
from app.config import settings
from app.transcription import transcribe_audio, extract_audio_if_needed, denoise_audio
from app.storage import storage

logger = logging.getLogger(__name__)

router = APIRouter()


def _select_for_update(db, table, uid):
    """SELECT FOR UPDATE on PostgreSQL, plain SELECT on SQLite."""
    dialect = db.bind.dialect.name if db.bind else "unknown"
    if dialect == "sqlite":
        row = db.execute(text(f"SELECT plan FROM {table} WHERE id = :uid"), {"uid": uid}).fetchone()
    else:
        row = db.execute(text(f"SELECT plan FROM {table} WHERE id = :uid FOR UPDATE"), {"uid": uid}).fetchone()
    return row


def _is_truly_public(video: Video) -> bool:
    """Returns True only if the video is public with no password or expiry protection."""
    if not video.is_public:
        return False
    if video.share_password_hash:
        return False
    if video.share_expires_at and video.share_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        return False
    return True


# ── Magic bytes validation ─────────────────────────────
# ملاحظة: b"\x1a\x45\xdf\xa3" (EBML) هو نفسه توقيع webm و mkv، و
# b"\x52\x49\x46\x46" (RIFF) هو نفسه توقيع avi و wav — لذلك كل توقيع يُطابَق
# بمجموعة (set) من الامتدادات المسموحة، بدل قيمة واحدة كانت تُكتب فوق الأخرى.
MAGIC_SIGNATURES = {
    b"\x1a\x45\xdf\xa3": {"webm", "mkv"},
    b"\x52\x49\x46\x46":  {"avi", "wav"},
    b"\x49\x44\x33":      {"mp3"},
    b"\xff\xfb":          {"mp3"},
    b"\xff\xf3":          {"mp3"},
    b"\xff\xf2":          {"mp3"},
    b"\x66\x4c\x61\x43":  {"flac"},
    b"\x4f\x67\x67\x53":  {"ogg"},
}

ALLOWED_EXTENSIONS = {
    "mp4", "webm", "mov", "mp3", "wav", "m4a", "avi", "mkv", "ogg", "flac"
}

ALLOWED_UPLOAD_CONTENT_TYPES = {
    "video/mp4", "video/quicktime", "video/webm", "video/x-msvideo",
    "video/x-matroska", "video/ogg", "audio/mpeg", "audio/wav",
    "audio/mp4", "audio/ogg", "audio/flac", "application/octet-stream",
}


def _validate_magic_bytes(header: bytes, declared_ext: str) -> bool:
    """يتحقق من bytes رأس الملف (16 بايت على الأقل يفضَّل) مقابل الامتداد
    المُصرَّح به. هذا هو التطبيق الوحيد المشترك — سواء جاءت الـ header bytes
    من ملف محلي (proxy upload) أو من أول 16 بايت مقروءة من R2 (/complete)."""
    if len(header) < 4:
        return False

    # ── mp4 / mov: صندوق ftyp يبدأ بعد أول 4 بايت (حجم الصندوق) ──
    # التحقق بـ bytes[4:8] == b"ftyp" أدق وأثبت من افتراض أطوال صناديق محددة.
    if declared_ext in ("mp4", "mov", "m4a"):
        if len(header) >= 8 and header[4:8] == b"ftyp":
            return True
        # بعض ملفات m4a تبدأ بصندوق "free" أو "wide" قبل ftyp — نقبلها بحذر
        # طالما الامتداد كان مسموحاً أصلاً (تحقق سابق في نقطة الدخول).
        return declared_ext == "m4a"

    file_magic4 = header[:4]
    file_magic2 = header[:2]

    for sig, exts in MAGIC_SIGNATURES.items():
        if len(sig) == 4 and file_magic4 == sig:
            return declared_ext in exts
        if len(sig) == 2 and file_magic2 == sig:
            return declared_ext in exts

    return True  # توقيع غير معروف — اسمح به طالما الامتداد اجتاز الفحص مسبقاً


def _validate_file_magic(file_path: str, declared_ext: str) -> bool:
    """Check a local file's header bytes against the declared extension."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
        return _validate_magic_bytes(header, declared_ext)
    except Exception:
        return False


# ── Schemas ───────────────────────────────────────────
class VideoResponse(BaseModel):
    id:           str
    title:        str
    description:  Optional[str]
    duration:     Optional[float]
    file_size:    Optional[int]
    dialect:      str
    is_public:    bool
    share_token:  str
    views_count:  int
    created_at:   datetime
    transcript_status: Optional[str] = None
    thumbnail_url: Optional[str] = None

    class Config:
        from_attributes = True


class ShareSettingsRequest(BaseModel):
    password: Optional[str] = None
    expires_in_days: Optional[int] = None


class UnlockShareRequest(BaseModel):
    password: str


class PresignedUploadRequest(BaseModel):
    filename:     str  = Field(..., min_length=1, max_length=255)
    content_type: str  = "video/webm"
    title:        str  = Field(default="تسجيل جديد", max_length=200)
    dialect:      str  = Field(default="ar", max_length=10)


# ══════════════════════════════════════════════════════
#  POST /api/videos/upload
# ══════════════════════════════════════════════════════
@router.post("/upload", response_model=VideoResponse, status_code=201)
@limiter.limit("10/hour")
async def upload_video(
    request:          Request,
    background_tasks: BackgroundTasks,
    file:        UploadFile    = File(...),
    title:       str           = Form("تسجيل جديد"),
    description: Optional[str] = Form(None),
    dialect:     str           = Form("ar"),
    mode:        str           = Form("screen"),
    noise_reduction: bool      = Form(False),
    db:          Session       = Depends(get_db),
    current_user: User         = Depends(require_auth),
):
    ext = Path(file.filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"نوع الملف غير مدعوم. الأنواع المقبولة: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # ── Prevent race condition with SELECT FOR UPDATE ──
    user_row = _select_for_update(db, "users", current_user.id)
    user_plan = user_row[0] if user_row else current_user.plan

    if user_plan == "free":
        video_count = db.query(Video).filter(
            Video.owner_id == current_user.id,
            Video.status != "pending",
        ).count()
        if video_count >= settings.FREE_MAX_VIDEOS:
            raise HTTPException(
                status_code=403,
                detail=f"وصلت للحد الأقصى ({settings.FREE_MAX_VIDEOS} تسجيل) في الخطة المجانية. يرجى الترقية.",
            )

    video_id  = str(uuid.uuid4())
    filename  = f"{video_id}.{ext}"

    store = storage()
    use_r2 = hasattr(store, "client") and hasattr(store, "bucket")  # R2Storage

    r2_key = None
    if use_r2:
        r2_key = f"users/{current_user.id}/videos/{video_id}/{filename}"
        file_path = r2_key
    else:
        file_path = os.path.join(settings.UPLOAD_DIR, filename)

    # ── حد واحد موحّد لكل مسارات الرفع (presigned و proxy) ──
    max_bytes = settings.MAX_UPLOAD_BYTES
    total_bytes = 0

    tmp_path = file_path if not use_r2 else os.path.join(settings.UPLOAD_DIR, filename)
    tmp_path_exists = False
    succeeded = False

    try:
        # ── اكتب الملف محلياً (مؤقتاً إن كان use_r2) ──
        async with aiofiles.open(tmp_path, "wb") as buffer:
            tmp_path_exists = True
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    await buffer.close()
                    raise HTTPException(
                        status_code=413,
                        detail=f"الملف أكبر من الحد الأقصى ({max_bytes // (1024*1024)} ميجابايت)",
                    )
                await buffer.write(chunk)

        file_size = total_bytes

        # ── Validate magic bytes ──
        if not _validate_file_magic(tmp_path, ext):
            raise HTTPException(
                status_code=400,
                detail="محتوى الملف لا يتوافق مع الامتداد المُصرّح",
            )

        # ── ارفع إلى R2 (streaming) ──
        if use_r2:
            try:
                with open(tmp_path, "rb") as f:
                    store.put_streaming(r2_key, f, file.content_type or "application/octet-stream")
            except Exception as e:
                logger.error(f"R2 upload failed: {e}")
                raise HTTPException(status_code=500, detail="فشل رفع الملف إلى التخزين السحابي")

        video = Video(
            id          = video_id,
            title       = title,
            description = description,
            file_path   = file_path,
            file_size   = file_size,
            mime_type   = file.content_type,
            dialect     = dialect,
            owner_id    = current_user.id,
        )
        db.add(video)

        transcript = Transcript(video_id=video_id)
        db.add(transcript)
        db.commit()
        db.refresh(video)

        # ── Celery Tasks (dispatch آمن — لا يفشل الطلب لو الـ broker غير متاح) ──
        from app.worker import transcribe_task, hls_task, thumbnail_task, dispatch

        # ── دائماً نمرر r2_key كـ file_path عند use_r2: العمّال يعيدون
        #    التحميل من R2 بأنفسهم عند الحاجة، وتنظيف tmp_path هنا في
        #    finally لا يترك ملفات يتيمة على قرص الويب سيرفس. ──
        dispatched = all([
            dispatch(
                transcribe_task,
                video_id=video_id,
                file_path=r2_key if use_r2 else file_path,
                r2_key=r2_key,
                language=dialect,
                noise_reduction=noise_reduction,
            ),
            dispatch(
                hls_task,
                video_id=video_id,
                input_path=r2_key if use_r2 else file_path,
                r2_key=r2_key,
            ),
            dispatch(
                thumbnail_task,
                video_id=video_id,
                file_path=r2_key if use_r2 else file_path,
                r2_key=r2_key,
            ),
        ])

        if not dispatched:
            transcript.status = TranscriptStatus.FAILED
            transcript.error_message = "processing queue unavailable"
            db.commit()

        response = VideoResponse.model_validate(video)
        response.transcript_status = (
            TranscriptStatus.PENDING if dispatched else TranscriptStatus.FAILED
        )
        succeeded = True
        return response

    finally:
        # ── use_r2: الملف المحلي مؤقت دائماً — نظّفه سواء نجح الرفع أو فشل،
        #    لأن العمّال يعيدون التحميل من R2 عند الحاجة.
        # ── not use_r2: tmp_path هو مسار التخزين الدائم — لا نحذفه إلا لو
        #    فشلت العملية (ملف جزئي/غير صالح). ──
        should_cleanup = tmp_path_exists and os.path.exists(tmp_path) and (
            use_r2 or not succeeded
        )
        if should_cleanup:
            try:
                os.remove(tmp_path)
            except OSError as e:
                logger.warning(f"Failed to remove tmp upload file {tmp_path}: {e}")


# ══════════════════════════════════════════════════════
#  POST /api/videos/presigned-upload
# ══════════════════════════════════════════════════════
@router.post("/presigned-upload")
@limiter.limit("10/minute")
def get_presigned_upload(
    request:      Request,
    payload:      PresignedUploadRequest,
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """يُعطي رابط رفع مباشر للمتصفح (لـ R2) مع التحقق من الخطة."""
    content_type = payload.content_type.split(";")[0].strip().lower()
    if content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="نوع المحتوى غير مدعوم")

    # ── Enforce plan limits (SELECT FOR UPDATE) ──
    user_row = _select_for_update(db, "users", current_user.id)
    user_plan = user_row[0] if user_row else current_user.plan

    if user_plan == "free":
        video_count = db.query(Video).filter(
            Video.owner_id == current_user.id,
            Video.status != "pending",
        ).count()
        if video_count >= settings.FREE_MAX_VIDEOS:
            raise HTTPException(
                status_code=403,
                detail=f"وصلت للحد الأقصى ({settings.FREE_MAX_VIDEOS} تسجيل) في الخطة المجانية.",
            )

    ext = Path(payload.filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم")

    video_id = str(uuid.uuid4())
    r2_key = f"users/{current_user.id}/videos/{video_id}/{video_id}.{ext}"

    # ── Create pending video record ──
    video = Video(
        id=video_id,
        title=payload.title,
        file_path=r2_key,
        dialect=payload.dialect,
        owner_id=current_user.id,
        status="pending",
    )
    db.add(video)
    transcript = Transcript(video_id=video_id)
    db.add(transcript)
    db.commit()

    # ── R2 لا يدعم presigned POST — PUT هو الآلية المدعومة الوحيدة.
    #    لا يمكن حراسة الحجم وقت إصدار الرابط (لا content-length-range على
    #    presigned PUT)؛ التحقق الفعلي من الحجم والمحتوى يتم لاحقاً في
    #    POST /videos/{id}/complete عبر head_object + magic bytes. ──
    store = storage()
    result = store.get_presigned_upload_url(r2_key, content_type, expires=900)
    return {"video_id": video_id, **result}


# ══════════════════════════════════════════════════════
#  POST /api/videos/{id}/complete
# ══════════════════════════════════════════════════════
@router.post("/{video_id}/complete")
def complete_upload(
    video_id:         str,
    background_tasks: BackgroundTasks,
    db:               Session = Depends(get_db),
    current_user:     User    = Depends(require_auth),
):
    """Finalize a presigned-upload: validate the R2 object exists and trigger processing."""
    video = db.query(Video).filter(
        Video.id == video_id, Video.owner_id == current_user.id
    ).first()
    if not video:
        raise HTTPException(404, "الفيديو غير موجود")

    # ── هذه هي الحراسة الحقيقية على الحجم والمحتوى — presigned PUT لا يسمح
    #    بفرض حد أقصى وقت الرفع، فكل التحقق مؤجَّل إلى هنا. ──
    store = storage()
    head = store.head_object(video.file_path)
    if not head:
        raise HTTPException(400, "الملف لم يتم رفعه بعد")
    if head["size"] < 1024:
        store.delete(video.file_path)
        db.delete(video)
        db.commit()
        raise HTTPException(400, "الملف فارغ أو تالف")
    if head["size"] > settings.MAX_UPLOAD_BYTES:
        store.delete(video.file_path)
        db.delete(video)
        db.commit()
        raise HTTPException(413, "الملف أكبر من الحد المسموح")

    # ── تحقق فعلي من المحتوى (magic bytes) — نقرأ أول 16 بايت فقط من R2 ──
    ext = Path(video.file_path).suffix.lower().lstrip(".")
    header = b""
    if hasattr(store, "client") and hasattr(store, "bucket"):
        try:
            obj = store.client.get_object(
                Bucket=store.bucket, Key=video.file_path, Range="bytes=0-15"
            )
            header = obj["Body"].read()
        except Exception as e:
            logger.warning(f"Failed to read header bytes for magic check: {e}")
    else:
        local = store.get_local_path(video.file_path)
        if local:
            try:
                with open(local, "rb") as f:
                    header = f.read(16)
            except OSError:
                header = b""

    if header and not _validate_magic_bytes(header, ext):
        store.delete(video.file_path)
        db.delete(video)
        db.commit()
        raise HTTPException(400, "محتوى الملف لا يتوافق مع الامتداد المُصرّح")

    video.file_size = head["size"]
    video.status = "uploaded"
    db.commit()

    # ── Trigger Celery tasks بأمان (dispatch لا يفشل الطلب لو الـ broker غير متاح) ──
    from app.worker import transcribe_task, hls_task, thumbnail_task, dispatch

    dispatched = all([
        dispatch(
            transcribe_task,
            video_id=video_id,
            file_path=video.file_path,
            r2_key=video.file_path,
            language=video.dialect,
        ),
        dispatch(
            hls_task,
            video_id=video_id,
            input_path=video.file_path,
            r2_key=video.file_path,
        ),
        dispatch(
            thumbnail_task,
            video_id=video_id,
            file_path=video.file_path,
            r2_key=video.file_path,
        ),
    ])

    if not dispatched:
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
        if transcript:
            transcript.status = TranscriptStatus.FAILED
            transcript.error_message = "processing queue unavailable"
            db.commit()

    response = VideoResponse.model_validate(video)
    response.transcript_status = (
        TranscriptStatus.PENDING if dispatched else TranscriptStatus.FAILED
    )
    return response


# ══════════════════════════════════════════════════════
#  GET /api/videos/my
# ══════════════════════════════════════════════════════
@router.get("/my", response_model=List[VideoResponse])
def get_my_videos(
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_auth),
):
    videos = (
        db.query(Video)
        .options(joinedload(Video.transcript))
        .filter(Video.owner_id == current_user.id)
        .order_by(Video.created_at.desc())
        .all()
    )
    
    store = storage()
    # Batch process thumbnail URLs if needed, but get_presigned_read_url is usually a local sign operation.
    # The real N+1 was the transcript relation.
    result = []
    for v in videos:
        r = VideoResponse.model_validate(v)
        r.transcript_status = v.transcript.status if v.transcript else None
        if v.thumbnail_path:
            # Note: This is still O(N) calls to sign, but no longer hits DB per item.
            r.thumbnail_url = store.get_presigned_read_url(
                v.thumbnail_path, is_public=_is_truly_public(v)
            )
        result.append(r)
    return result


# ══════════════════════════════════════════════════════
#  GET /api/videos/share/{token}
# ══════════════════════════════════════════════════════
@router.get("/share/{token}")
def get_video_by_share_token(
    token: str,
    password: Optional[str] = None,
    db: Session = Depends(get_db),
):
    video = db.query(Video).filter(Video.share_token == token).first()
    if not video:
        raise HTTPException(status_code=404, detail="الرابط غير صحيح أو منتهي")

    # تحقق من انتهاء الصلاحية
    if video.share_expires_at and video.share_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=410, detail="انتهت صلاحية رابط المشاركة")

    # تحقق من كلمة المرور
    if video.share_password_hash:
        # إذا كان هناك كلمة مرور ولم يتم إرسالها — أعد بيانات محدودة
        if not password:
            return {
                "id": video.id,
                "title": video.title,
                "requires_password": True,
                "share_token": video.share_token,
                "thumbnail_url": storage().get_presigned_read_url(video.thumbnail_path, is_public=False) if video.thumbnail_path else None,
            }
        # تحقق من كلمة المرور
        if not verify_password(password, video.share_password_hash):
            raise APIException(401, "كلمة المرور غير صحيحة", error_code="WRONG_PASSWORD")

    video.views_count += 1
    db.commit()
    r = VideoResponse.model_validate(video)
    r.transcript_status = video.transcript.status if video.transcript else None
    r.thumbnail_url = storage().get_presigned_read_url(video.thumbnail_path, is_public=_is_truly_public(video)) if video.thumbnail_path else None
    return r


# ══════════════════════════════════════════════════════
#  GET /api/videos/share/{token}/stream
# ══════════════════════════════════════════════════════
@router.get("/share/{token}/stream")
def stream_video_by_share_token(
    token: str,
    password: Optional[str] = None,
    db: Session = Depends(get_db),
):
    video = db.query(Video).filter(Video.share_token == token).first()
    if not video:
        raise HTTPException(status_code=404, detail="الرابط غير صحيح أو منتهي")

    if video.share_expires_at and video.share_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=410, detail="انتهت صلاحية رابط المشاركة")

    if video.share_password_hash:
        if not password:
            raise HTTPException(status_code=401, detail="يتطلب كلمة مرور")
        if not verify_password(password, video.share_password_hash):
            raise HTTPException(status_code=401, detail="كلمة المرور غير صحيحة")

    # ── R2: أعد تحويلة إلى presigned URL ──
    store = storage()
    presigned = store.get_presigned_read_url(video.file_path, is_public=_is_truly_public(video))
    if presigned and presigned.startswith("http"):
        return RedirectResponse(url=presigned, status_code=302)

    # ── محلي: قدّم الملف مباشرة ──
    local = store.get_local_path(video.file_path)
    if not local:
        raise HTTPException(status_code=404, detail="الملف غير موجود على الخادم")

    return FileResponse(
        path        = local,
        media_type  = video.mime_type or "application/octet-stream",
        filename    = Path(local).name,
        headers     = {"Accept-Ranges": "bytes"},
    )


# ══════════════════════════════════════════════════════
#  PATCH /api/videos/{id}/share-settings
# ══════════════════════════════════════════════════════
@router.patch("/{video_id}/share-settings")
def update_share_settings(
    video_id:     str,
    data:         ShareSettingsRequest,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_auth),
):
    video = db.query(Video).filter(
        Video.id == video_id, Video.owner_id == current_user.id
    ).first()
    if not video:
        raise HTTPException(404, "الفيديو غير موجود أو ليس لديك صلاحية")

    if data.password is not None:
        if data.password == "":
            video.share_password_hash = None
        else:
            video.share_password_hash = hash_password(data.password)

    if data.expires_in_days is not None:
        if data.expires_in_days <= 0:
            video.share_expires_at = None
        else:
            video.share_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=data.expires_in_days)

    db.commit()
    return {"message": "تم تحديث إعدادات المشاركة"}


# ══════════════════════════════════════════════════════
#  POST /api/videos/share/{token}/unlock
# ══════════════════════════════════════════════════════
@router.post("/share/{token}/unlock")
@limiter.limit("5/minute")
def unlock_shared_video(
    request: Request,
    token:   str,
    data:    UnlockShareRequest,
    db:      Session = Depends(get_db),
):
    video = db.query(Video).filter(Video.share_token == token).first()
    if not video:
        raise HTTPException(404, "الرابط غير صحيح")

    if video.share_expires_at and video.share_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(410, "انتهت صلاحية رابط المشاركة")

    if not video.share_password_hash:
        raise HTTPException(400, "هذا الفيديو لا يتطلب كلمة مرور")

    if not verify_password(data.password, video.share_password_hash):
        raise APIException(401, "كلمة المرور غير صحيحة", error_code="WRONG_PASSWORD")

    from app.auth import create_access_token
    access_token = create_access_token(
        {"sub": video.owner_id or "guest", "video_id": video.id, "type": "share_access"},
        timedelta(hours=1),
    )
    video.views_count += 1
    db.commit()

    return {"access_token": access_token}


# ══════════════════════════════════════════════════════
#  GET /api/videos/{id}
# ══════════════════════════════════════════════════════
@router.get("/{video_id}", response_model=VideoResponse)
def get_video(
    video_id:     str,
    db:           Session       = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="الفيديو غير موجود")

    if not video.is_public:
        if not current_user or video.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="ليس لديك صلاحية لمشاهدة هذا الفيديو")

    video.views_count += 1
    db.commit()

    r = VideoResponse.model_validate(video)
    r.transcript_status = video.transcript.status if video.transcript else None
    r.thumbnail_url = storage().get_presigned_read_url(video.thumbnail_path, is_public=_is_truly_public(video)) if video.thumbnail_path else None
    return r


# ══════════════════════════════════════════════════════
#  GET /api/videos/{id}/stream
# ══════════════════════════════════════════════════════
@router.get("/{video_id}/stream")
def stream_video(
    video_id:     str,
    db:           Session       = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="الفيديو غير موجود")

    if not video.is_public:
        if not current_user or video.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="ليس لديك صلاحية لمشاهدة هذا الفيديو")

    # ── R2: أعد تحويلة إلى presigned URL ──
    store = storage()
    presigned = store.get_presigned_read_url(video.file_path, is_public=_is_truly_public(video))
    if presigned and presigned.startswith("http"):
        return RedirectResponse(url=presigned, status_code=302)

    # ── محلي: قدّم الملف مباشرة ──
    local = store.get_local_path(video.file_path)
    if not local:
        raise HTTPException(status_code=404, detail="الملف غير موجود على الخادم")

    return FileResponse(
        path        = local,
        media_type  = video.mime_type or "application/octet-stream",
        filename    = Path(local).name,
        headers     = {"Accept-Ranges": "bytes"},
    )


# ══════════════════════════════════════════════════════
#  GET /api/videos/{id}/hls/playlist.m3u8
# ══════════════════════════════════════════════════════
@router.get("/{video_id}/hls/playlist.m3u8")
def get_hls_playlist(
    video_id:     str,
    db:           Session       = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "الفيديو غير موجود")

    if not video.is_public:
        if not current_user or video.owner_id != current_user.id:
            raise HTTPException(403, "ليس لديك صلاحية لمشاهدة هذا الفيديو")

    if not video.hls_ready or not video.hls_playlist_path:
        raise HTTPException(404, "HLS غير جاهز بعد")

    # ── R2: أعد تحويلة إلى presigned URL ──
    store = storage()
    presigned = store.get_presigned_read_url(video.hls_playlist_path, is_public=_is_truly_public(video))
    if presigned and presigned.startswith("http"):
        return RedirectResponse(url=presigned, status_code=302)

    # ── محلي ──
    local = store.get_local_path(video.hls_playlist_path)
    if not local:
        raise HTTPException(404, "ملف HLS غير موجود")

    return FileResponse(
        path=local,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "public, max-age=10",
        },
    )


# ══════════════════════════════════════════════════════
#  POST /api/videos/{id}/hls/convert
# ══════════════════════════════════════════════════════
@router.post("/{video_id}/hls/convert")
def trigger_hls_conversion(
    video_id:         str,
    background_tasks: BackgroundTasks,
    db:               Session = Depends(get_db),
    current_user:     User    = Depends(require_auth),
):
    video = db.query(Video).filter(
        Video.id == video_id, Video.owner_id == current_user.id
    ).first()
    if not video:
        raise HTTPException(404, "الفيديو غير موجود أو ليس لديك صلاحية")

    store = storage()
    input_path = store.get_local_path(video.file_path) or video.file_path

    from app.worker import hls_task
    hls_task.delay(
        video_id=video_id,
        input_path=input_path,
        r2_key=video.file_path if not store.get_local_path(video.file_path) else None,
    )

    return {"message": "بدأ التحويل إلى HLS في الخلفية"}


# ══════════════════════════════════════════════════════
#  DELETE /api/videos/{id}
# ══════════════════════════════════════════════════════
@router.delete("/{video_id}", status_code=204)
def delete_video(
    video_id:     str,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_auth),
):
    video = db.query(Video).filter(
        Video.id == video_id,
        Video.owner_id == current_user.id,
    ).first()

    if not video:
        raise HTTPException(status_code=404, detail="الفيديو غير موجود أو ليس لديك صلاحية حذفه")

    # ── احذف من التخزين ──
    try:
        storage().delete(video.file_path)
    except Exception:
        pass

    # ── احذف HLS ──
    if video.hls_playlist_path:
        try:
            store = storage()
            hls_prefix = f"hls/{video_id}"
            if hasattr(store, "client") and hasattr(store, "bucket"):
                import boto3
                paginator = store.client.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=store.bucket, Prefix=hls_prefix):
                    for obj in page.get("Contents", []):
                        store.client.delete_object(Bucket=store.bucket, Key=obj["Key"])
            else:
                import shutil
                local_hls = Path("hls") / video_id
                if local_hls.exists():
                    shutil.rmtree(local_hls, ignore_errors=True)
        except Exception:
            pass

    # ── احذف الصورة المصغرة ──
    if video.thumbnail_path:
        try:
            storage().delete(video.thumbnail_path)
        except Exception:
            pass

    db.delete(video)
    db.commit()
