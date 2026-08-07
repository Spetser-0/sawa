"""
اختبارات /videos/presigned-upload — BLOCKER 1 (R2 لا يدعم presigned POST)

الاختبارات القديمة هنا كانت تُرسل الحمولة كـ query params بدل جسم JSON، وهو
ما لا يتوافق أبداً مع Pydantic body model المُعرَّف في الـ endpoint، فكانت
تفشل بـ 422 دائماً دون أن تختبر شيئاً فعلياً. أُعيدت الكتابة بالكامل.
"""
import pytest
from tests.conftest import client, auth_client, db_session


class TestPresignedUpload:
    def test_presigned_upload_returns_put_method_no_fields(self, auth_client):
        """BLOCKER 1 / التحقق #3: الاستجابة يجب أن تحتوي method='PUT' ولا
        تحتوي مفتاح 'fields' إطلاقاً (كان هذا شكل presigned POST الملغي)."""
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "clip.mp4",
            "content_type": "video/mp4",
            "title": "تسجيل تجريبي",
            "dialect": "ar",
        })
        assert res.status_code == 200
        body = res.json()

        assert "video_id" in body
        assert "url" in body and body["url"]
        assert body["method"] == "PUT"
        assert "fields" not in body
        assert body.get("headers", {}).get("Content-Type") == "video/mp4"

    def test_presigned_upload_creates_pending_video_row(self, auth_client, db_session):
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "clip.webm",
            "content_type": "video/webm",
            "title": "معلّق",
            "dialect": "ar",
        })
        video_id = res.json()["video_id"]

        from app.database import Video
        video = db_session.query(Video).filter(Video.id == video_id).first()
        assert video is not None
        assert video.status == "pending"

    def test_presigned_upload_rejects_unsupported_extension(self, auth_client):
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "malware.exe",
            "content_type": "application/octet-stream",
            "title": "ملف خطر",
            "dialect": "ar",
        })
        assert res.status_code == 400

    def test_presigned_upload_rejects_unsupported_content_type(self, auth_client):
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "clip.mp4",
            "content_type": "text/html",
            "title": "نوع خاطئ",
            "dialect": "ar",
        })
        assert res.status_code == 400

    def test_presigned_upload_normalizes_content_type_with_codec_suffix(self, auth_client):
        """MediaRecorder ينتج أنواعاً مركّبة زي video/webm;codecs=vp9,opus —
        يجب تطبيع النوع (split على ';') قبل المطابقة."""
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "rec.webm",
            "content_type": "video/webm;codecs=vp9,opus",
            "title": "تسجيل شاشة",
            "dialect": "ar",
        })
        assert res.status_code == 200
        assert res.json()["headers"]["Content-Type"] == "video/webm"

    def test_presigned_upload_requires_auth(self, client):
        res = client.post("/api/videos/presigned-upload", json={
            "filename": "clip.mp4",
            "content_type": "video/mp4",
            "title": "بلا تسجيل دخول",
            "dialect": "ar",
        })
        assert res.status_code == 401
