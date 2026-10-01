import os
import json
import logging
from celery import Celery
from celery.schedules import crontab
from app.config import settings
from app.database import SessionLocal, Video, Transcript, TranscriptStatus, TerminologyDictionary
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
)

celery_app.conf.beat_schedule = {
    "cleanup-pending-videos": {
        "task": "app.worker.cleanup_pending_videos",
        "schedule": crontab(minute="*/15"),
    },
    "cleanup-orphan-temp-files": {
        "task": "app.worker.cleanup_orphan_temp_files",
        "schedule": crontab(minute=0),  # كل ساعة
    },
}


def dispatch(task, **kwargs) -> bool:
    """يرسل مهمة Celery بأمان — لا يرفع استثناء إذا كان الـ broker غير متاح،
    حتى لا يفشل الطلب بـ 500 بعد نجاح الرفع فعلياً."""
    try:
        task.delay(**kwargs)
        return True
    except Exception as e:
        logger.error(f"Celery dispatch failed for {task.name}: {e}")
        return False


def _update_transcript_status(db, video_id: str, status: TranscriptStatus, **kwargs):
    """Update transcript status and metadata safely."""
    try:
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
        if transcript:
            transcript.status = status
            for key, value in kwargs.items():
                if hasattr(transcript, key):
                    setattr(transcript, key, value)
            db.commit()
    except Exception as e:
        logger.error(f"Failed to update transcript status for {video_id}: {e}")
        db.rollback()


@celery_app.task(name="app.worker.transcribe_task", bind=True, max_retries=3, default_retry_delay=60)
def transcribe_task(self, video_id: str, file_path: str, language: str, noise_reduction: bool = False, r2_key: str = None, dialect_hint: str = None):
    db = SessionLocal()
    try:
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
        if not transcript:
            return

        # Increment retry count on retry
        if self.request.retries > 0:
            transcript.retry_count = self.request.retries
            db.commit()

        # Load terminology dictionary if available
        terminology_dict = None
        if transcript.video and transcript.video.owner:
            term_dict = db.query(TerminologyDictionary).filter(
                TerminologyDictionary.user_id == transcript.video.owner_id,
                TerminologyDictionary.is_active == True
            ).first()
            if term_dict:
                import json
                terminology_dict = json.loads(term_dict.entries_json)

        _update_transcript_status(db, video_id, TranscriptStatus.QUEUED, current_stage="queued", progress_percent=5)

        audio_path = extract_audio_if_needed(file_path)

        if noise_reduction:
            _update_transcript_status(db, video_id, TranscriptStatus.DENOISING, current_stage="denoising", progress_percent=10)
            try:
                audio_path = denoise_audio(audio_path)
            except Exception as denoise_err:
                logger.warning(f"⚠️ Denoising failed, transcribing without it: {denoise_err}")

        _update_transcript_status(db, video_id, TranscriptStatus.TRANSCRIBING, current_stage="transcribing", progress_percent=30)
        result = transcribe_audio(audio_path, language=language, dialect_hint=dialect_hint or language, run_alignment=True, terminology_dict=terminology_dict)

        # Store provider metadata
        _update_transcript_status(
            db, video_id,
            TranscriptStatus.ALIGNING,
            current_stage="aligning",
            progress_percent=70,
            provider=result.get("provider"),
            model=result.get("model"),
            timestamp_source=result.get("segments", [{}])[0].get("timestamp_source") if result.get("segments") else None,
        )

        _update_transcript_status(
            db, video_id,
            TranscriptStatus.MERGING,
            current_stage="merging",
            progress_percent=90,
        )

        transcript.full_text = result["full_text"]
        transcript.segments_json = json.dumps(result["segments"], ensure_ascii=False)
        transcript.language_detected = result.get("language_detected") or result.get("metadata", {}).get("language_detected")
        transcript.processing_time = result["processing_time"]
        transcript.status = TranscriptStatus.DONE
        transcript.current_stage = "done"
        transcript.progress_percent = 100
        transcript.error_message = None
        transcript.error_code = None
        # Store dialect and terminology info
        transcript.dialect_selected = result.get("metadata", {}).get("dialect_selected")
        transcript.terminology_applied = result.get("metadata", {}).get("terminology_applied", False)
        transcript.terminology_dictionary_used = json.dumps(result.get("metadata", {}).get("terminology_corrections_count", 0))
        db.commit()

    except Exception as e:
        logger.error(f"Transcription task failed: {e}")
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
        if transcript:
            # Only retry on transient errors, not on validation errors
            error_str = str(e).lower()
            is_retryable = not any(keyword in error_str for keyword in [
                "invalid", "unauthorized", "forbidden", "not found", "quota", "billing"
            ])
            
            if is_retryable and self.request.retries < self.max_retries:
                logger.info(f"Retrying transcription for {video_id} (attempt {self.request.retries + 1})")
                raise self.retry(exc=e)
            
            transcript.status = TranscriptStatus.FAILED
            transcript.error_message = str(e)
            transcript.error_code = "TRANSCRIPTION_FAILED"
            transcript.current_stage = "failed"
            db.commit()
    finally:
        db.close()


@celery_app.task(name="app.worker.diarize_task", bind=True, max_retries=2, default_retry_delay=120)
def diarize_task(self, video_id: str, file_path: str, num_speakers: int = None, r2_key: str = None):
    """
    Async speaker diarization task.
    Runs pyannote.audio diarization and merges with existing transcript.
    """
    db = SessionLocal()
    tmp_file = None
    try:
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
        if not transcript:
            logger.error(f"Transcript not found for video {video_id}")
            return

        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            logger.error(f"Video not found for id {video_id}")
            return

        # Check if diarization already in progress or done (idempotency)
        if transcript.status == TranscriptStatus.DIARIZING:
            logger.info(f"Diarization already in progress for {video_id}, skipping duplicate")
            return
        
        # Check if already has speaker labels (already diarized)
        segments = json.loads(transcript.segments_json or "[]")
        if segments and any(s.get("speaker") and s["speaker"] != "متحدث غير معروف" for s in segments):
            logger.info(f"Transcript {video_id} already has speaker labels, skipping")
            return

        _update_transcript_status(db, video_id, TranscriptStatus.DIARIZING, current_stage="diarizing", progress_percent=10)

        # Download from R2 if needed
        audio_path = file_path
        store = storage()
        if r2_key and not os.path.exists(audio_path):
            tmp_file = os.path.join(settings.UPLOAD_DIR, f"diarize_{video_id}.tmp")
            store.download(r2_key, tmp_file)
            audio_path = tmp_file

        # Run diarization
        _update_transcript_status(db, video_id, TranscriptStatus.DIARIZING, current_stage="diarizing", progress_percent=30)
        
        from app.ai_services import diarize_audio, merge_diarization_with_transcript
        speakers = diarize_audio(audio_path, num_speakers)

        # Merge with transcript
        _update_transcript_status(db, video_id, TranscriptStatus.MERGING, current_stage="merging", progress_percent=80)
        merged = merge_diarization_with_transcript(segments, speakers)

        # Save results atomically
        transcript.segments_json = json.dumps(merged, ensure_ascii=False)
        transcript.status = TranscriptStatus.DONE
        transcript.current_stage = "done"
        transcript.progress_percent = 100
        transcript.error_message = None
        transcript.error_code = None
        db.commit()

        logger.info(f"✅ Diarization completed for video {video_id} — {len(set(s['speaker'] for s in speakers))} speakers found")

    except ImportError as e:
        logger.error(f"Diarization unavailable: {e}")
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
        if transcript:
            transcript.status = TranscriptStatus.FAILED
            transcript.error_message = "Speaker diarization unavailable: pyannote.audio not installed or Hugging Face token missing"
            transcript.error_code = "DIARIZATION_UNAVAILABLE"
            transcript.current_stage = "failed"
            db.commit()
    except ValueError as e:
        logger.error(f"Diarization config error: {e}")
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
        if transcript:
            transcript.status = TranscriptStatus.FAILED
            transcript.error_message = str(e)
            transcript.error_code = "DIARIZATION_CONFIG_ERROR"
            transcript.current_stage = "failed"
            db.commit()
    except Exception as e:
        logger.error(f"Diarization task failed: {e}")
        transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
        if transcript:
            error_str = str(e).lower()
            is_retryable = not any(keyword in error_str for keyword in [
                "invalid", "unauthorized", "forbidden", "not found", "token", "auth"
            ])
            
            if is_retryable and self.request.retries < self.max_retries:
                logger.info(f"Retrying diarization for {video_id} (attempt {self.request.retries + 1})")
                raise self.retry(exc=e)
            
            transcript.status = TranscriptStatus.FAILED
            transcript.error_message = str(e)
            transcript.error_code = "DIARIZATION_FAILED"
            transcript.current_stage = "failed"
            db.commit()
    finally:
        db.close()
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except OSError as e:
                logger.warning(f"Failed to remove tmp file {tmp_file}: {e}")


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


@celery_app.task(name="app.worker.cleanup_orphan_temp_files")
def cleanup_orphan_temp_files():
    """يحذف الملفات المؤقتة الأقدم من 6 ساعات في UPLOAD_DIR — بقايا رفع فشلت
    أو ملفات لم تُنظَّف بسبب انقطاع مفاجئ (crash) قبل الوصول لـ finally."""
    from datetime import datetime, timedelta, timezone
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(hours=6)).timestamp()
    deleted = 0
    try:
        if not os.path.isdir(settings.UPLOAD_DIR):
            return {"deleted": 0}
        for name in os.listdir(settings.UPLOAD_DIR):
            path = os.path.join(settings.UPLOAD_DIR, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff_ts:
                    os.remove(path)
                    deleted += 1
            except OSError as e:
                logger.warning(f"Failed to remove orphan temp file {path}: {e}")
        logger.info(f"Cleaned up {deleted} orphan temp file(s)")
        return {"deleted": deleted}
    except Exception as e:
        logger.error(f"cleanup_orphan_temp_files failed: {e}")
        return {"deleted": deleted, "error": str(e)}


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
