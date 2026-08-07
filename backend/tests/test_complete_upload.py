"""
اختبارات /videos/{id}/complete — BLOCKER 2 (حراسة الحجم/المحتوى الحقيقية)
و BLOCKER 3 (dispatch آمن لمهام Celery).

presigned PUT لا يسمح بفرض حد أقصى للحجم وقت الرفع (لا content-length-range)،
فكل التحقق الفعلي يجب أن يحدث هنا عبر head_object.
"""
import pytest
from tests.conftest import client, auth_client, db_session


class _FakeStore:
    """بديل لـ storage() يتحكم الاختبار في head_object/delete دون لمس R2 حقيقي."""

    def __init__(self, size=5 * 1024 * 1024, header=b"\x00\x00\x00\x18ftypmp42"):
        self._size = size
        self._header = header
        self.deleted_keys = []

    def head_object(self, key):
        if self._size is None:
            return None
        return {"size": self._size, "content_type": "video/mp4", "etag": "abc"}

    def delete(self, key):
        self.deleted_keys.append(key)

    def get_local_path(self, key):
        return None  # نحاكي سلوك R2Storage (سحابي) — لا مسار محلي


def _create_pending_video(auth_client, filename="clip.mp4", content_type="video/mp4"):
    res = auth_client.post("/api/videos/presigned-upload", json={
        "filename": filename,
        "content_type": content_type,
        "title": "قيد الاختبار",
        "dialect": "ar",
    })
    assert res.status_code == 200
    return res.json()["video_id"]


class TestCompleteUploadSizeGuard:
    def test_413_when_size_exceeds_max_and_video_row_deleted(self, auth_client, db_session, monkeypatch):
        """التحقق #4: 413 لو head_object أرجع حجماً أكبر من MAX_UPLOAD_BYTES،
        وصف الفيديو يُحذف من قاعدة البيانات ومن التخزين."""
        video_id = _create_pending_video(auth_client)

        from app.config import settings
        oversized = settings.MAX_UPLOAD_BYTES + 1
        fake_store = _FakeStore(size=oversized)
        monkeypatch.setattr("app.routers.videos.storage", lambda: fake_store)

        res = auth_client.post(f"/api/videos/{video_id}/complete")
        assert res.status_code == 413

        from app.database import Video
        assert db_session.query(Video).filter(Video.id == video_id).first() is None
        assert len(fake_store.deleted_keys) == 1

    def test_400_when_file_too_small(self, auth_client, db_session, monkeypatch):
        video_id = _create_pending_video(auth_client)

        fake_store = _FakeStore(size=100)  # أقل من 1024 بايت
        monkeypatch.setattr("app.routers.videos.storage", lambda: fake_store)

        res = auth_client.post(f"/api/videos/{video_id}/complete")
        assert res.status_code == 400

        from app.database import Video
        assert db_session.query(Video).filter(Video.id == video_id).first() is None

    def test_400_when_not_yet_uploaded(self, auth_client, monkeypatch):
        video_id = _create_pending_video(auth_client)

        fake_store = _FakeStore(size=None)  # head_object يرجع None = لسه ما اتحملش
        monkeypatch.setattr("app.routers.videos.storage", lambda: fake_store)

        res = auth_client.post(f"/api/videos/{video_id}/complete")
        assert res.status_code == 400

    def test_400_when_magic_bytes_mismatch(self, auth_client, db_session, monkeypatch):
        """BLOCKER 2: محتوى الملف الفعلي (magic bytes) لازم يتطابق مع الامتداد
        المُصرَّح — امتداد mp4 لكن أول بايتات الملف توقيع webm/mkv فعلي."""
        video_id = _create_pending_video(auth_client, filename="clip.mp4")

        class _MismatchStore(_FakeStore):
            def __init__(self):
                super().__init__(size=5 * 1024 * 1024)

            def get_local_path(self, key):
                return None

        fake_store = _MismatchStore()
        # نجعل get_local_path يشير لملف حقيقي بمحتوى EBML (webm) بامتداد mp4 معلن
        import tempfile, os as _os
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.write(b"\x1a\x45\xdf\xa3" + b"\x00" * 12)
        tmp.close()
        fake_store.get_local_path = lambda key: tmp.name

        monkeypatch.setattr("app.routers.videos.storage", lambda: fake_store)

        res = auth_client.post(f"/api/videos/{video_id}/complete")
        _os.remove(tmp.name)

        assert res.status_code == 400
        from app.database import Video
        assert db_session.query(Video).filter(Video.id == video_id).first() is None


class TestCompleteUploadDispatch:
    def test_dispatch_failure_marks_transcript_failed_but_still_succeeds(self, auth_client, db_session, monkeypatch):
        """BLOCKER 3: لو Celery broker غير متاح، الطلب يرجع نجاح (200) مع
        transcript.status=FAILED — وليس 500 بعد رفع ناجح فعلياً."""
        video_id = _create_pending_video(auth_client)
        fake_store = _FakeStore(size=5 * 1024 * 1024)
        monkeypatch.setattr("app.routers.videos.storage", lambda: fake_store)

        def _always_fail_dispatch(task, **kwargs):
            return False

        monkeypatch.setattr("app.worker.dispatch", _always_fail_dispatch)

        res = auth_client.post(f"/api/videos/{video_id}/complete")
        assert res.status_code == 200

        from app.database import Transcript, TranscriptStatus
        transcript = db_session.query(Transcript).filter(Transcript.video_id == video_id).first()
        assert transcript.status == TranscriptStatus.FAILED
        assert transcript.error_message == "processing queue unavailable"

    def test_successful_complete_returns_video(self, auth_client, monkeypatch):
        video_id = _create_pending_video(auth_client)
        fake_store = _FakeStore(size=5 * 1024 * 1024)
        monkeypatch.setattr("app.routers.videos.storage", lambda: fake_store)
        monkeypatch.setattr("app.worker.dispatch", lambda task, **kwargs: True)

        res = auth_client.post(f"/api/videos/{video_id}/complete")
        assert res.status_code == 200
        assert res.json()["id"] == video_id
