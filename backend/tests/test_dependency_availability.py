"""
Test for dependency availability - verifies clear configuration errors when ML dependencies unavailable.
"""
import sys
import pytest
from unittest.mock import patch, MagicMock
from app.ai_services import diarize_audio
from app.alignment import WhisperXAlignmentProvider, get_alignment_provider, NoAlignmentProvider


class TestDependencyAvailability:
    """Tests for clear configuration errors when ML dependencies are unavailable."""

    def test_diarize_audio_missing_pyannote_audio_raises_clear_error(self):
        """diarize_audio should raise clear ImportError when pyannote.audio not installed."""
        # Set the token first to pass the token check
        import os
        os.environ["HUGGINGFACE_TOKEN"] = "test-token"
        
        with patch.dict('sys.modules', {'pyannote.audio': None, 'pyannote': None}):
            # Also need to remove from sys.modules if already imported
            modules_to_remove = [k for k in list(sys.modules.keys()) if 'pyannote' in k]
            for mod in modules_to_remove:
                del sys.modules[mod]
            
            with pytest.raises(ImportError, match="pyannote.audio غير مثبت"):
                diarize_audio("dummy_path.wav")

    def test_whisperx_provider_unavailable_returns_false(self):
        """WhisperXAlignmentProvider.is_available() should return False when whisperx not installed."""
        with patch.dict('sys.modules', {'whisperx': None, 'torch': None}):
            modules_to_remove = [k for k in list(sys.modules.keys()) if 'whisperx' in k or 'torch' in k]
            for mod in modules_to_remove:
                del sys.modules[mod]
            
            provider = WhisperXAlignmentProvider()
            assert provider.is_available() is False

    def test_get_alignment_provider_returns_whisperx_by_name(self):
        """get_alignment_provider returns WhisperXAlignmentProvider by name (availability checked at align time)."""
        provider = get_alignment_provider("whisperx")
        assert isinstance(provider, WhisperXAlignmentProvider)

    def test_get_alignment_provider_returns_none_for_unknown(self):
        """get_alignment_provider returns NoAlignmentProvider for unknown provider names."""
        provider = get_alignment_provider("unknown")
        assert isinstance(provider, NoAlignmentProvider)

    def test_diarize_endpoint_queues_task_when_pyannote_unavailable(self, auth_client, db_session):
        """API should queue diarization task even when pyannote.audio unavailable (worker handles error)."""
        from app.database import Video, Transcript, TranscriptStatus
        import uuid
        import json

        # Get the authenticated user's ID
        res = auth_client.get("/api/auth/me")
        user_id = res.json()["id"]

        # Create video with transcript in DONE status
        video_id = str(uuid.uuid4())
        video = Video(id=video_id, title="Test", file_path="test.mp4", dialect="ar", owner_id=user_id)
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

        with patch("app.worker.diarize_task.delay") as mock_delay:
            mock_result = MagicMock()
            mock_result.id = "task-123"
            mock_delay.return_value = mock_result

            res = auth_client.post(f"/api/transcripts/{video_id}/diarize")
            
            # Should return 202 (accepted) - the task is queued
            assert res.status_code == 202
            data = res.json()
            assert data["status"] == "queued"
            assert data["task_id"] == "task-123"

    def test_alignment_endpoint_fallback_when_whisperx_unavailable(self):
        """API should handle unavailable alignment gracefully."""
        from app.alignment import align_transcript, NoAlignmentProvider
        from app.transcript_schema import CanonicalTranscript, TranscriptSegment, TimestampSource

        canonical = CanonicalTranscript(
            full_text="مرحبا بكم",
            segments=[
                TranscriptSegment(text="مرحبا", start=0.0, end=1.0, timestamp_source=TimestampSource.PROVIDER),
            ],
            language_detected="ar",
            provider="gemini",
            model="gemini-1.5-flash",
            processing_time=1.0,
            segments_count=1,
        )

        with patch('app.alignment.WHISPERX_AVAILABLE', False):
            with patch('app.alignment.TORCH_AVAILABLE', False):
                # Reload the module to pick up patched values
                import importlib
                import app.alignment as alignment_module
                importlib.reload(alignment_module)
                
                result = alignment_module.align_transcript("/fake/path.wav", canonical, "ar", provider_name="whisperx")
                assert isinstance(result.segments[0].timestamp_source, TimestampSource)
                assert result.segments[0].timestamp_source == TimestampSource.APPROXIMATE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])