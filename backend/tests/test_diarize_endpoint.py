"""
Tests for async diarization endpoint (Phase 5).
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from tests.conftest import auth_client, db_session, client


class TestDiarizeEndpoint:
    """Tests for POST /api/transcripts/{video_id}/diarize async endpoint."""

    def test_diarize_returns_202_accepted(self, auth_client, db_session):
        """Endpoint should return 202 and enqueue task."""
        from app.database import Video, Transcript, TranscriptStatus
        import uuid
        
        # Get the authenticated user's ID
        res = auth_client.get("/api/auth/me")
        user_id = res.json()["id"]
        
        video_id = str(uuid.uuid4())
        video = Video(
            id=video_id,
            title="Test Video",
            file_path=f"test/{video_id}.mp4",
            dialect="ar",
            owner_id=user_id,
        )
        db_session.add(video)
        
        transcript = Transcript(
            video_id=video_id,
            full_text="Test transcript",
            segments_json=json.dumps([{"start": 0.0, "end": 5.0, "text": "Test"}]),
            language_detected="ar",
            status=TranscriptStatus.DONE,
        )
        db_session.add(transcript)
        db_session.commit()
        
        # Now test the endpoint
        with patch("app.worker.diarize_task.delay") as mock_delay:
            mock_result = MagicMock()
            mock_result.id = "task-123"
            mock_delay.return_value = mock_result
            
            res = auth_client.post(f"/api/transcripts/{video_id}/diarize")
            
            assert res.status_code == 202
            data = res.json()
            assert data["status"] == "queued"
            assert data["video_id"] == video_id
            assert data["task_id"] == "task-123"
            mock_delay.assert_called_once()

    def test_diarize_404_video_not_found(self, auth_client):
        """Should return 404 for non-existent video."""
        res = auth_client.post("/api/transcripts/nonexistent/diarize")
        assert res.status_code == 404

    def test_diarize_404_no_transcript(self, auth_client, db_session):
        """Should return 404 if video exists but no transcript."""
        from app.database import Video
        import uuid
        
        res = auth_client.get("/api/auth/me")
        user_id = res.json()["id"]
        
        video_id = str(uuid.uuid4())
        video = Video(
            id=video_id,
            title="Test Video",
            file_path=f"test/{video_id}.mp4",
            dialect="ar",
            owner_id=user_id,
        )
        db_session.add(video)
        db_session.commit()
        
        res = auth_client.post(f"/api/transcripts/{video_id}/diarize")
        assert res.status_code == 404
        assert "لا يوجد تفريغ" in res.json()["detail"]

    def test_diarize_400_transcript_not_done(self, auth_client, db_session):
        """Should return 400 if transcript not in DONE status."""
        from app.database import Video, Transcript, TranscriptStatus
        import uuid
        
        res = auth_client.get("/api/auth/me")
        user_id = res.json()["id"]
        
        video_id = str(uuid.uuid4())
        video = Video(
            id=video_id,
            title="Test Video",
            file_path=f"test/{video_id}.mp4",
            dialect="ar",
            owner_id=user_id,
        )
        transcript = Transcript(
            video_id=video_id,
            status=TranscriptStatus.PROCESSING,
        )
        db_session.add(video)
        db_session.add(transcript)
        db_session.commit()
        
        res = auth_client.post(f"/api/transcripts/{video_id}/diarize")
        assert res.status_code == 400
        assert "التفريغ لم يكتمل" in res.json()["detail"]

    def test_diarize_idempotent_already_diarizing(self, auth_client, db_session):
        """Should return current status if already diarizing."""
        from app.database import Video, Transcript, TranscriptStatus
        import uuid
        
        res = auth_client.get("/api/auth/me")
        user_id = res.json()["id"]
        
        video_id = str(uuid.uuid4())
        video = Video(
            id=video_id,
            title="Test Video",
            file_path=f"test/{video_id}.mp4",
            dialect="ar",
            owner_id=user_id,
        )
        transcript = Transcript(
            video_id=video_id,
            full_text="Test",
            segments_json=json.dumps([{"start": 0.0, "end": 5.0, "text": "Test"}]),
            language_detected="ar",
            status=TranscriptStatus.DIARIZING,
        )
        db_session.add(video)
        db_session.add(transcript)
        db_session.commit()
        
        res = auth_client.post(f"/api/transcripts/{video_id}/diarize")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "diarizing"
        assert "قيد المعالجة بالفعل" in data["message"]

    def test_diarize_idempotent_already_has_speakers(self, auth_client, db_session):
        """Should return done if transcript already has speaker labels."""
        from app.database import Video, Transcript, TranscriptStatus
        import uuid
        
        res = auth_client.get("/api/auth/me")
        user_id = res.json()["id"]
        
        video_id = str(uuid.uuid4())
        video = Video(
            id=video_id,
            title="Test Video",
            file_path=f"test/{video_id}.mp4",
            dialect="ar",
            owner_id=user_id,
        )
        transcript = Transcript(
            video_id=video_id,
            full_text="Test",
            segments_json=json.dumps([{"start": 0.0, "end": 5.0, "text": "Test", "speaker": "المتحدث 1"}]),
            language_detected="ar",
            status=TranscriptStatus.DONE,
        )
        db_session.add(video)
        db_session.add(transcript)
        db_session.commit()
        
        res = auth_client.post(f"/api/transcripts/{video_id}/diarize")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "done"
        assert "محددون بالفعل" in data["message"]

    def test_diarize_requires_auth(self, client):
        """Should return 401 without authentication."""
        res = client.post("/api/transcripts/some-id/diarize")
        assert res.status_code == 401

    def test_diarize_forbidden_not_owner(self, client, db_session):
        """Should return 403 if user doesn't own the video."""
        from app.database import Video, Transcript, TranscriptStatus, User
        from app.auth import hash_password
        import uuid
        
        # Create two users
        user1 = User(id="user1", email="user1@test.com", name="User1", hashed_password=hash_password("Pass1234!"))
        user2 = User(id="user2", email="user2@test.com", name="User2", hashed_password=hash_password("Pass1234!"))
        db_session.add(user1)
        db_session.add(user2)
        
        video_id = str(uuid.uuid4())
        video = Video(id=video_id, title="Test", file_path="test.mp4", dialect="ar", owner_id="user1")
        transcript = Transcript(video_id=video_id, status=TranscriptStatus.DONE, full_text="Test", 
                               segments_json=json.dumps([{"start": 0, "end": 5, "text": "Test"}]), language_detected="ar")
        db_session.add(video)
        db_session.add(transcript)
        db_session.commit()
        
        # Login as user2
        res = client.post("/api/auth/login", json={"email": "user2@test.com", "password": "Pass1234!"})
        assert res.status_code == 200
        
        res = client.post(f"/api/transcripts/{video_id}/diarize")
        assert res.status_code == 404  # Not found because ownership check fails

    def test_diarize_dispatch_failure_returns_503(self, auth_client, db_session):
        """Should return 503 if Celery dispatch fails."""
        from app.database import Video, Transcript, TranscriptStatus
        import uuid
        
        res = auth_client.get("/api/auth/me")
        user_id = res.json()["id"]
        
        video_id = str(uuid.uuid4())
        video = Video(id=video_id, title="Test", file_path="test.mp4", dialect="ar", owner_id=user_id)
        transcript = Transcript(video_id=video_id, status=TranscriptStatus.DONE, full_text="Test",
                               segments_json=json.dumps([{"start": 0, "end": 5, "text": "Test"}]), language_detected="ar")
        db_session.add(video)
        db_session.add(transcript)
        db_session.commit()
        
        with patch("app.worker.diarize_task.delay") as mock_delay:
            mock_delay.side_effect = Exception("Broker unavailable")
            
            res = auth_client.post(f"/api/transcripts/{video_id}/diarize")
            assert res.status_code == 503
            assert "طابور المعالجة غير متاح" in res.json()["detail"]