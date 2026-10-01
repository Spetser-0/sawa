"""Regression tests for the final security and dispatch fixes."""

import json
import uuid
from unittest.mock import patch

from app.auth import hash_password
from app.database import Transcript, TranscriptStatus, Video


class _FakeLocalStorage:
    def __init__(self, media_path):
        self.media_path = str(media_path)

    def get_presigned_read_url(self, key, expires=3600, is_public=True):
        return None

    def get_local_path(self, key):
        return self.media_path


def _add_protected_video(db_session, owner_id, media_path, title="Shared video"):
    video_id = str(uuid.uuid4())
    video = Video(
        id=video_id,
        title=title,
        file_path=f"test/{video_id}.mp4",
        mime_type="video/mp4",
        dialect="ar",
        owner_id=owner_id,
        share_token=f"share-{video_id}",
        share_password_hash=hash_password("SharePass123!"),
    )
    db_session.add(video)
    db_session.commit()
    return video


class TestFinalSecurityFixes:
    def test_retry_dispatch_failure_restores_previous_transcript_state(
        self, auth_client, db_session
    ):
        user_id = auth_client.get("/api/auth/me").json()["id"]
        video_id = str(uuid.uuid4())
        video = Video(
            id=video_id,
            title="Retry test",
            file_path=f"test/{video_id}.mp4",
            dialect="ar",
            owner_id=user_id,
        )
        transcript = Transcript(
            video_id=video_id,
            status=TranscriptStatus.FAILED,
            error_message="previous failure",
            full_text="Existing transcript",
            segments_json=json.dumps([]),
        )
        db_session.add(video)
        db_session.add(transcript)
        db_session.commit()

        with patch("app.worker.dispatch", return_value=None):
            response = auth_client.post(f"/api/transcripts/{video_id}/retry")

        assert response.status_code == 503
        db_session.expire_all()
        restored = db_session.query(Transcript).filter(
            Transcript.video_id == video_id
        ).one()
        assert restored.status == TranscriptStatus.FAILED
        assert restored.error_message == "previous failure"

    def test_unlocked_share_token_only_streams_matching_video(
        self, auth_client, db_session, tmp_path, monkeypatch
    ):
        user_id = auth_client.get("/api/auth/me").json()["id"]
        media_path = tmp_path / "shared.mp4"
        media_path.write_bytes(b"fake video bytes")
        first = _add_protected_video(db_session, user_id, media_path, "First")
        second = _add_protected_video(db_session, user_id, media_path, "Second")

        unlock = auth_client.post(
            f"/api/videos/share/{first.share_token}/unlock",
            json={"password": "SharePass123!"},
        )
        assert unlock.status_code == 200
        share_token = unlock.json()["access_token"]

        monkeypatch.setattr(
            "app.routers.videos.storage",
            lambda: _FakeLocalStorage(media_path),
        )

        matching = auth_client.get(
            f"/api/videos/share/{first.share_token}/stream",
            headers={"Authorization": f"Bearer {share_token}"},
        )
        assert matching.status_code == 200
        assert matching.content == b"fake video bytes"

        wrong_video = auth_client.get(
            f"/api/videos/share/{second.share_token}/stream",
            headers={"Authorization": f"Bearer {share_token}"},
        )
        assert wrong_video.status_code == 401
