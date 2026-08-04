import os
import json
import logging
from celery import Celery
from celery.schedules import crontab
from app.config import settings
from app.database import SessionLocal, Video, Transcript, TranscriptStatus
from app.storage import storage
from app.transcription import transcribe_audio, extract_audio_if_needed, denoise_audio
from app.hls import convert_to_hls
from app.thumbnails import generate_thumbnail

logger = logging.getLogger(__name__)

celery_app = Celery(
    "sawa_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Fast-fail when the broker (Redis) is unreachable instead of hanging indefinitely.
    # Without this, a dead broker causes kombu to retry for minutes, which manifests
    # as a 500 in the web process after the DB commit has already succeeded.
    broker_transport_options={
        "max_retries": 2,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 1,
    },
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "cleanup-pending-videos": {
        "task": "app.worker.cleanup_pending_videos",
        "schedule": crontab(minute="*/15"),
    },
}


def dispatch(task, **kwargs) -> bool:
    """ارسل مهمة Celery بأمان — إذا كان Redis/Broker غير متاح، سجّل الخطأ وأعد False
    بدلاً من رفع استثناء يُعيد 500 بعد نجاح commit قاعدة البيانات."""
    try:
        task.delay(**kwargs)
        return True
    except Exception as exc:
        logger.error(
            "celery dispatch failed for %s: %s — the file is stored but the job was not queued.",
            task.name, exc,
        )
        return False

@celery_app.task(name="app.worker.transcribe_task")
def transcribe_task(
    video_id: str,
    file_path: str,
    language: str,
    noise_reduction: bool = False,
    r2_key: str = None,
):
    db = SessionLocal()
    tmp_file = None
    try:
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
        if not transcript:
            return

        # ── حمّل من R2 إن لم يكن الملف موجوداً محلياً ──
        store = storage()
        if r2_key and not os.path.exists(file_path):
            tmp_file = os.path.join(settings.UPLOAD_DIR, f"transcribe_{video_id}.tmp")
            store.download(r2_key, tmp_file)
            file_path = tmp_file

        audio_path = extract_audio_if_needed(file_path)

        if noise_reduction:
            transcript.status = TranscriptStatus.DENOISING
            db.commit()
            try:
                audio_path = denoise_audio(audio_path)
            except Exception as denoise_err:
                logger.warning(f"⚠️ Denoising failed, transcribing without it: {denoise_err}")

        transcript.status = TranscriptStatus.PROCESSING
        db.commit()
        result = transcribe_audio(audio_path, language=language)

        transcript.full_text         = result["full_text"]
        transcript.segments_json     = json.dumps(result["segments"], ensure_ascii=False)
        transcript.language_detected = result["language_detected"]
        transcript.processing_time   = result["processing_time"]
        transcript.status            = TranscriptStatus.DONE
        db.commit()

        # Trigger auto-chapters
        from app.routers.videos import _auto_generate_chapters
        _auto_generate_chapters(video_id, transcript, db)

    except Exception as e:
        logger.error(f"Transcription task failed: {e}")
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
        if transcript:
            transcript.status = TranscriptStatus.FAILED
            transcript.error_message = str(e)
            db.commit()
    finally:
        db.close()
        # احذف الملف المؤقت الذي حمّلناه من R2
        if tmp_file and os.path.exists(tmp_file):
            os.remove(tmp_file)

@celery_app.task(name="app.worker.hls_task")
def hls_task(video_id: str, input_path: str, r2_key: str = None):
    db = SessionLocal()
    tmp_file = None
    try:
        store = storage()
        if r2_key and not os.path.exists(input_path):
            tmp_file = os.path.join(settings.UPLOAD_DIR, f"hls_{video_id}.tmp")
            store.download(r2_key, tmp_file)
            input_path = tmp_file

        playlist_key = convert_to_hls(video_id, input_path, storage=store)
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.hls_playlist_path = playlist_key
            video.hls_ready = True
            db.commit()
    except Exception as e:
        logger.error(f"HLS task failed: {e}")
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.hls_ready = False
            db.commit()
    finally:
        db.close()
        if tmp_file and os.path.exists(tmp_file):
            os.remove(tmp_file)

@celery_app.task(name="app.worker.thumbnail_task")
def thumbnail_task(video_id: str, file_path: str, r2_key: str = None):
    db = SessionLocal()
    tmp_file = None
    try:
        store = storage()
        if r2_key and not os.path.exists(file_path):
            tmp_file = os.path.join(settings.UPLOAD_DIR, f"thumb_{video_id}.tmp")
            store.download(r2_key, tmp_file)
            file_path = tmp_file

        thumbnail_key = generate_thumbnail(file_path, video_id, storage=store)
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.thumbnail_path = thumbnail_key
            db.commit()
    except Exception as e:
        logger.warning(f"Thumbnail task failed: {e}")
    finally:
        db.close()
        if tmp_file and os.path.exists(tmp_file):
            os.remove(tmp_file)


@celery_app.task(name="app.worker.cleanup_pending_videos")
def cleanup_pending_videos():
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.PENDING_UPLOAD_TTL_MINUTES)
    db = SessionLocal()
    store = storage()
    try:
        stale = db.query(Video).filter(
            Video.status == "pending",
            Video.created_at < cutoff,
        ).all()
        for v in stale:
            try:
                store.delete(v.file_path)
            except Exception:
                pass
            db.delete(v)
        db.commit()
        logger.info(f"Cleaned up {len(stale)} pending videos")
        return {"deleted": len(stale)}
    finally:
        db.close()
