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
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from app.limiter import limiter

from app.database import get_db, Video, Transcript, TranscriptStatus, User
from app.exceptions import APIException
from app.auth import get_current_user, require_auth, hash_password, verify_password
from app.config import settings
from app.transcription import transcribe_audio, extract_audio_if_needed, denoise_audio
from app.storage import storage

logger = logging.getLogger(__name__)

router = APIRouter()


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
MAGIC_SIGNATURES = {
    b"\x1a\x45\xdf\xa3": "webm",
    b"\x00\x00\x00\x1c": "mp4",
    b"\x00\x00\x00\x20": "mp4",
    b"\x00\x00\x00\x18": "mp4",
    b"\x00\x00\x00\x14": "mp4",
    b"\x52\x49\x46\x46": "avi",
    b"\x1a\x45\xdf\xa3": "mkv",
    b"\x49\x44\x33":      "mp3",
    b"\xff\xfb":          "mp3",
    b"\xff\xf3":          "mp3",
    b"\xff\xf2":          "mp3",
    b"\x52\x49\x46\x46":  "wav",
    b"\x66\x4c\x61\x43":  "flac",
    b"\x4f\x67\x67\x53":  "ogg",
    b"\x00\x00\x00\x0c":  "m4a",
}

ALLOWED_EXTENSIONS = {
    "mp4", "webm", "mov", "mp3", "wav", "m4a", "avi", "mkv", "ogg", "flac"
}


def _validate_file_magic(file_path: str, declared_ext: str) -> bool:
    """Check file header bytes against declared extension."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
        if len(header) < 4:
            return False
        file_magic = header[:4]
        for sig, fmt in MAGIC_SIGNATURES.items():
            if file_magic == sig:
                return fmt == declared_ext or declared_ext in ("mov", "mkv")
        return True  # unknown magic — allow if extension was already checked
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


# ══════════════════════════════════════════════════════
#  مهمة خلفية: التفريغ الصوتي + HLS + صورة مصغرة
# ══════════════════════════════════════════════════════
def run_transcription_task(video_id: str, file_path: str, language: str, noise_reduction: bool = False, r2_key: str = None):
    from app.database import Transcript, Video, TranscriptStatus, SessionLocal
    import json

    db = SessionLocal()
    transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    if not transcript:
        db.close()
        return

    try:
        audio_path = extract_audio_if_needed(file_path)

        if noise_reduction:
            transcript.status = TranscriptStatus.DENOISING
            db.commit()
            try:
                audio_path = denoise_audio(audio_path)
            except Exception as denoise_err:
                import logging
                logging.getLogger(__name__).warning(f"⚠️ فشل تنظيف الصوت، التفريغ بدون تنظيف: {denoise_err}")

        transcript.status = TranscriptStatus.PROCESSING
        db.commit()
        result = transcribe_audio(audio_path, language=language)

        transcript.full_text         = result["full_text"]
        transcript.segments_json     = json.dumps(result["segments"], ensure_ascii=False)
        transcript.language_detected = result["language_detected"]
        transcript.processing_time   = result["processing_time"]
        transcript.status            = TranscriptStatus.DONE

        db.commit()

        # ── بعد التفريغ: توليد فصول ذكية تلقائياً ──
        _auto_generate_chapters(video_id, transcript, db)

    except Exception as e:
        transcript.status        = TranscriptStatus.FAILED
        transcript.error_message = str(e)
        db.commit()

    finally:
        db.close()


def _auto_generate_chapters(video_id: str, transcript, db):
    """يولّد فصولاً ذكية تلقائياً بعد اكتمال التفريغ."""
    import json
    import anthropic
    import os
    import logging

    logger = logging.getLogger(__name__)

    if not transcript.full_text or transcript.chapters_json:
        return

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return

    try:
        segments = json.loads(transcript.segments_json) if transcript.segments_json else []
        if len(segments) < 3:
            return

        segments_text = "\n".join([
            f"[{s.get('start', 0):.1f}s - {s.get('end', 0):.1f}s]: {s.get('text', '')}"
            for s in segments
        ])

        prompt = f"""أنت مساعد ذكي. لديك نص مفرَّغ من تسجيل صوتي/فيديو.
قم بتقسيمه إلى فصول (chapters) منطقية (3-8 فصول).

أرجع JSON فقط بدون أي نص إضافي:
{{"chapters": [{{"start": 0.0, "end": 120.5, "title": "عنوان الفصل", "summary": "ملخص الفصل في جملة"}}]}}

- كل فصل يجب أن يكون منطقياً في المحتوى
- العنوان بالعربية
- استخدم الطوابع الزمنية الفعلية من النص

النص:
{segments_text[:8000]}"""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        chapters_data = json.loads(raw)

        transcript.chapters_json = json.dumps(chapters_data, ensure_ascii=False)
        db.commit()
        logger.info(f"📑 [Auto-Chapters] تم إنشاء فصول تلقائياً للفيديو {video_id[:8]}")

    except Exception as e:
        logger.warning(f"⚠️ [Auto-Chapters] فشل إنشاء الفصول التلقائية: {e}")


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
    user_row = db.execute(
        text("SELECT plan FROM users WHERE id = :uid FOR UPDATE"),
        {"uid": current_user.id},
    ).fetchone()
    user_plan = user_row[0] if user_row else current_user.plan

    if user_plan == "free":
        video_count = db.query(Video).filter(Video.owner_id == current_user.id).count()
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

    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    total_bytes = 0

    # ── اكتب الملف محلياً (للخلفية) + ارفع إلى R2 إن وُجد ──
    tmp_path = file_path if not use_r2 else os.path.join(settings.UPLOAD_DIR, filename)
    async with aiofiles.open(tmp_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                await buffer.close()
                os.remove(tmp_path)
                raise HTTPException(
                    status_code=413,
                    detail=f"الملف أكبر من الحد الأقصى ({settings.MAX_FILE_SIZE_MB} ميجابايت)",
                )
            await buffer.write(chunk)

    file_size = total_bytes

    # ── Validate magic bytes ──
    if not _validate_file_magic(tmp_path, ext):
        os.remove(tmp_path)
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
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
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

    # ── تفريغ صوتي ──
    background_tasks.add_task(
        run_transcription_task,
        video_id     = video_id,
        file_path    = tmp_path if use_r2 else file_path,
        r2_key       = r2_key,
        language     = dialect,
        noise_reduction = noise_reduction,
    )

    # ── تحويل HLS تلقائي ──
    background_tasks.add_task(
        _run_hls_conversion,
        video_id  = video_id,
        input_path = tmp_path if use_r2 else file_path,
        r2_key    = r2_key,
    )

    # ── صورة مصغرة تلقائية ──
    background_tasks.add_task(
        _run_thumbnail_generation,
        video_id  = video_id,
        file_path = tmp_path if use_r2 else file_path,
        r2_key   = r2_key,
    )

    response = VideoResponse.model_validate(video)
    response.transcript_status = TranscriptStatus.PENDING
    return response


def _run_hls_conversion(video_id: str, input_path: str, r2_key: str = None):
    from app.database import SessionLocal, Video
    db = SessionLocal()
    tmp_file = None
    try:
        from app.storage import storage
        store = storage()

        # ── حمّل من R2 إن لم يكن الملف محلياً ──
        if r2_key and not os.path.exists(input_path):
            tmp_file = os.path.join(settings.UPLOAD_DIR, f"hls_{video_id}.tmp")
            store.download(r2_key, tmp_file)
            input_path = tmp_file

        from app.hls import convert_to_hls
        playlist_key = convert_to_hls(video_id, input_path, storage=store)
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.hls_playlist_path = playlist_key
            video.hls_ready = True
            db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"HLS conversion failed: {e}")
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.hls_ready = False
            db.commit()
    finally:
        db.close()
        if tmp_file and os.path.exists(tmp_file):
            os.remove(tmp_file)


def _run_thumbnail_generation(video_id: str, file_path: str, r2_key: str = None):
    from app.database import SessionLocal, Video
    db = SessionLocal()
    tmp_file = None
    try:
        from app.storage import storage
        store = storage()

        # ── حمّل من R2 إن لم يكن الملف محلياً ──
        if r2_key and not os.path.exists(file_path):
            tmp_file = os.path.join(settings.UPLOAD_DIR, f"thumb_{video_id}.tmp")
            store.download(r2_key, tmp_file)
            file_path = tmp_file

        from app.thumbnails import generate_thumbnail
        thumbnail_key = generate_thumbnail(file_path, video_id, storage=store)
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.thumbnail_path = thumbnail_key
            db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Thumbnail generation failed: {e}")
    finally:
        db.close()
        # نظّف الملف المؤقت الذي حمّلناه من R2
        if tmp_file and os.path.exists(tmp_file):
            os.remove(tmp_file)


# ══════════════════════════════════════════════════════
#  POST /api/videos/presigned-upload
# ══════════════════════════════════════════════════════
@router.post("/presigned-upload")
def get_presigned_upload(
    request:      Request,
    filename:     str,
    content_type: str = "video/webm",
    title:        str = "تسجيل جديد",
    dialect:      str = "ar",
    db:           Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """يُعطي رابط رفع مباشر للمتصفح (لـ R2) مع التحقق من الخطة."""
    # ── Enforce plan limits (SELECT FOR UPDATE) ──
    user_row = db.execute(
        text("SELECT plan FROM users WHERE id = :uid FOR UPDATE"),
        {"uid": current_user.id},
    ).fetchone()
    user_plan = user_row[0] if user_row else current_user.plan

    if user_plan == "free":
        video_count = db.query(Video).filter(Video.owner_id == current_user.id).count()
        if video_count >= settings.FREE_MAX_VIDEOS:
            raise HTTPException(
                status_code=403,
                detail=f"وصلت للحد الأقصى ({settings.FREE_MAX_VIDEOS} تسجيل) في الخطة المجانية.",
            )

    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم")

    video_id = str(uuid.uuid4())
    r2_key = f"users/{current_user.id}/videos/{video_id}/{video_id}.{ext}"

    # ── Create pending video record ──
    video = Video(
        id=video_id,
        title=title,
        file_path=r2_key,
        dialect=dialect,
        owner_id=current_user.id,
    )
    db.add(video)
    transcript = Transcript(video_id=video_id)
    db.add(transcript)
    db.commit()

    store = storage()
    result = store.get_presigned_upload_url(r2_key, content_type)
    return {"key": r2_key, "video_id": video_id, **result}


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
        .filter(Video.owner_id == current_user.id)
        .order_by(Video.created_at.desc())
        .all()
    )
    store = storage()
    result = []
    for v in videos:
        r = VideoResponse.model_validate(v)
        r.transcript_status = v.transcript.status if v.transcript else None
        if v.thumbnail_path:
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

    background_tasks.add_task(
        _run_hls_conversion,
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
