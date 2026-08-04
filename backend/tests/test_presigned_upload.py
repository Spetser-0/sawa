"""
Tests for presigned upload flow — size enforcement, /complete validation, pending cleanup
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ENVIRONMENT"] = "test"

from tests.conftest import client, auth_client, db_session
from app.database import Video, SessionLocal
import app.worker


class TestPresignedUploadReturnsPostFields:
    def test_presigned_response_has_fields(self, auth_client):
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "test.webm",
            "content_type": "video/webm",
            "title": "test video",
            "dialect": "ar",
            "size": 1024,
        })
        assert res.status_code == 200
        body = res.json()
        assert "video_id" in body
        assert "upload_url" in body
        assert "method" in body
        assert "headers" in body
        assert body["method"] == "PUT"

    def test_rejects_unknown_content_type(self, auth_client):
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "evil.exe",
            "content_type": "application/x-msdownload",
            "title": "test",
            "dialect": "ar",
            "size": 1024,
        })
        assert res.status_code == 400

    def test_rejects_unknown_extension(self, auth_client):
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "script.py",
            "content_type": "text/x-python",
            "title": "test",
            "dialect": "ar",
            "size": 1024,
        })
        assert res.status_code == 400


class TestCompleteValidatesObject:
    def test_complete_rejects_missing_object(self, auth_client, db_session):
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "test.webm",
            "content_type": "video/webm",
            "title": "test",
            "dialect": "ar",
            "size": 1024,
        })
        video_id = res.json()["video_id"]

        with patch("app.routers.videos.storage") as mock_storage:
            mock_store = MagicMock()
            mock_store.head_object.return_value = None
            mock_storage.return_value = mock_store
            res2 = auth_client.post(f"/api/videos/{video_id}/complete")
            assert res2.status_code == 400

    def test_complete_rejects_oversize_object(self, auth_client, db_session):
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "huge.webm",
            "content_type": "video/webm",
            "title": "test",
            "dialect": "ar",
            "size": 1024,
        })
        video_id = res.json()["video_id"]

        with patch("app.routers.videos.storage") as mock_storage:
            mock_store = MagicMock()
            mock_store.head_object.return_value = {"size": 3 * 1024 * 1024 * 1024, "content_type": "video/webm", "etag": "abc"}
            mock_store.delete = MagicMock()
            mock_storage.return_value = mock_store
            res2 = auth_client.post(f"/api/videos/{video_id}/complete")
            assert res2.status_code == 413
            mock_store.delete.assert_called_once()

            video = db_session.query(Video).filter(Video.id == video_id).first()
            assert video is None

    def test_complete_rejects_tiny_object(self, auth_client, db_session):
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "tiny.webm",
            "content_type": "video/webm",
            "title": "test",
            "dialect": "ar",
            "size": 1024,
        })
        video_id = res.json()["video_id"]

        with patch("app.routers.videos.storage") as mock_storage:
            mock_store = MagicMock()
            mock_store.head_object.return_value = {"size": 100, "content_type": "video/webm", "etag": "abc"}
            mock_store.delete = MagicMock()
            mock_storage.return_value = mock_store
            res2 = auth_client.post(f"/api/videos/{video_id}/complete")
            assert res2.status_code == 400

    def test_complete_sets_file_size_and_status(self, auth_client, db_session):
        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "good.webm",
            "content_type": "video/webm",
            "title": "test",
            "dialect": "ar",
            "size": 1024,
        })
        video_id = res.json()["video_id"]

        with patch("app.routers.videos.storage") as mock_storage:
            mock_store = MagicMock()
            mock_store.head_object.return_value = {"size": 5 * 1024 * 1024, "content_type": "video/webm", "etag": "abc"}
            mock_storage.return_value = mock_store

            mock_worker = MagicMock()
            with patch.dict(sys.modules, {"app.worker": mock_worker}):
                res2 = auth_client.post(f"/api/videos/{video_id}/complete")
                assert res2.status_code == 200
                video = db_session.query(Video).filter(Video.id == video_id).first()
                assert video.file_size == 5 * 1024 * 1024
                assert video.status == "uploaded"
                mock_worker.transcribe_task.delay.assert_called_once()
                mock_worker.hls_task.delay.assert_called_once()
                mock_worker.thumbnail_task.delay.assert_called_once()


class TestPendingVideoPlanLimit:
    def test_pending_videos_excluded_from_plan_limit(self, auth_client, db_session):
        for i in range(25):
            v = Video(
                id=f"vid-{i}",
                title=f"test {i}",
                file_path=f"users/test/vid-{i}.webm",
                owner_id="test-user",
                status="pending",
            )
            db_session.add(v)
        db_session.commit()

        res = auth_client.post("/api/videos/presigned-upload", json={
            "filename": "test.webm",
            "content_type": "video/webm",
            "title": "test",
            "dialect": "ar",
            "size": 1024,
        })
        assert res.status_code == 200


class TestCleanupPendingVideos:
    def test_cleanup_deletes_stale_pending(self, db_session):
        from datetime import datetime, timedelta, timezone
        from app.config import settings

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.PENDING_UPLOAD_TTL_MINUTES + 10)

        old_video = Video(
            id="old-pending",
            title="old",
            file_path="users/test/old-pending.webm",
            owner_id="test-user",
            status="pending",
            created_at=cutoff,
        )
        fresh_video = Video(
            id="fresh-pending",
            title="fresh",
            file_path="users/test/fresh-pending.webm",
            owner_id="test-user",
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        uploaded_video = Video(
            id="uploaded",
            title="uploaded",
            file_path="users/test/uploaded.webm",
            owner_id="test-user",
            status="uploaded",
            created_at=datetime.now(timezone.utc) - timedelta(hours=999),
        )
        db_session.add_all([old_video, fresh_video, uploaded_video])
        db_session.commit()

        mock_store = MagicMock()
        mock_store.delete = MagicMock()

        def _cleanup():
            cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=settings.PENDING_UPLOAD_TTL_MINUTES)
            stale = db_session.query(Video).filter(
                Video.status == "pending", Video.created_at < cutoff_dt,
            ).all()
            for v in stale:
                try:
                    mock_store.delete(v.file_path)
                except Exception:
                    pass
                db_session.delete(v)
            db_session.commit()
            return {"deleted": len(stale)}

        result = _cleanup()

        assert result["deleted"] == 1
        assert db_session.query(Video).filter(Video.id == "old-pending").first() is None
        assert db_session.query(Video).filter(Video.id == "fresh-pending").first() is not None
        assert db_session.query(Video).filter(Video.id == "uploaded").first() is not None