"""
Tests for word-level alignment (Phase 6).
"""
import pytest
from unittest.mock import patch, MagicMock
from app.alignment import (
    AlignmentProvider,
    NoAlignmentProvider,
    WhisperXAlignmentProvider,
    get_alignment_provider,
    list_alignment_providers,
    align_transcript,
)
from app.transcript_schema import (
    TranscriptSegment,
    WordTimestamp,
    CanonicalTranscript,
    TimestampSource,
)


class TestNoAlignmentProvider:
    """Tests for the disabled alignment provider."""

    def test_name_and_model(self):
        provider = NoAlignmentProvider()
        assert provider.name == "none"
        assert provider.model == "none"

    def test_is_available(self):
        provider = NoAlignmentProvider()
        assert provider.is_available() is True

    def test_align_preserves_segments(self):
        provider = NoAlignmentProvider()
        segments = [
            TranscriptSegment(text="مرحبا", start=0.0, end=1.0, timestamp_source=TimestampSource.PROVIDER),
            TranscriptSegment(text="بكم", start=1.0, end=2.0, timestamp_source=TimestampSource.PROVIDER),
        ]
        result = provider.align("/fake/path.wav", segments, "ar")

        assert len(result) == 2
        assert result[0].text == "مرحبا"
        # Should mark as APPROXIMATE since no alignment was performed
        assert result[0].timestamp_source == TimestampSource.APPROXIMATE
        assert result[1].timestamp_source == TimestampSource.APPROXIMATE

    def test_align_empty_segments(self):
        provider = NoAlignmentProvider()
        result = provider.align("/fake/path.wav", [], "ar")
        assert result == []


class TestWhisperXAlignmentProvider:
    """Tests for the WhisperX alignment provider."""

    def test_name_and_model(self):
        provider = WhisperXAlignmentProvider()
        assert provider.name == "whisperx"
        assert provider.model == "whisperx"

    def test_is_available_without_dependencies(self):
        """Should return False when whisperx not installed."""
        # We can't easily test this without actually uninstalling whisperx
        # Just verify the method exists and returns a bool
        provider = WhisperXAlignmentProvider()
        assert isinstance(provider.is_available(), bool)

    @patch("app.alignment.WHISPERX_AVAILABLE", True)
    @patch("app.alignment.TORCH_AVAILABLE", True)
    @patch("app.alignment.whisperx")
    @patch("app.alignment.torch")
    def test_align_success(self, mock_torch, mock_whisperx):
        """Test successful alignment with mocked WhisperX."""
        # Setup mocks
        mock_align_model = MagicMock()
        mock_metadata = {}
        mock_whisperx.load_align_model.return_value = (mock_align_model, mock_metadata)
        mock_whisperx.load_audio.return_value = [0.0] * 16000  # 1 second of silence
        mock_whisperx.align.return_value = {
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "مرحبا",
                    "words": [
                        {"word": "مرحبا", "start": 0.0, "end": 0.5, "score": 0.95},
                    ],
                }
            ]
        }

        provider = WhisperXAlignmentProvider(device="cpu")
        segments = [
            TranscriptSegment(text="مرحبا", start=0.0, end=1.0),
        ]

        result = provider.align("/fake/path.wav", segments, "ar")

        assert len(result) == 1
        assert result[0].timestamp_source == TimestampSource.ALIGNMENT
        assert len(result[0].words) == 1
        assert result[0].words[0].word == "مرحبا"
        assert result[0].words[0].confidence == 0.95

    @patch("app.alignment.WHISPERX_AVAILABLE", True)
    @patch("app.alignment.TORCH_AVAILABLE", True)
    @patch("app.alignment.whisperx")
    @patch("app.alignment.torch")
    def test_align_filters_empty_words(self, mock_torch, mock_whisperx):
        """Test that empty words are filtered out."""
        mock_align_model = MagicMock()
        mock_metadata = {}
        mock_whisperx.load_align_model.return_value = (mock_align_model, mock_metadata)
        mock_whisperx.load_audio.return_value = [0.0] * 16000
        mock_whisperx.align.return_value = {
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "مرحبا بكم",
                    "words": [
                        {"word": "مرحبا", "start": 0.0, "end": 0.5, "score": 0.95},
                        {"word": "", "start": 0.5, "end": 0.6, "score": 0.1},  # Empty word
                        {"word": "بكم", "start": 0.6, "end": 1.0, "score": 0.9},
                    ],
                }
            ]
        }

        provider = WhisperXAlignmentProvider(device="cpu")
        segments = [TranscriptSegment(text="مرحبا بكم", start=0.0, end=1.0)]

        result = provider.align("/fake/path.wav", segments, "ar")

        assert len(result[0].words) == 2  # Empty word filtered
        assert result[0].words[0].word == "مرحبا"
        assert result[0].words[1].word == "بكم"

    @patch("app.alignment.WHISPERX_AVAILABLE", True)
    @patch("app.alignment.TORCH_AVAILABLE", True)
    @patch("app.alignment.whisperx")
    @patch("app.alignment.torch")
    def test_align_failure_preserves_segments(self, mock_torch, mock_whisperx):
        """Test that alignment failure preserves original segments with flag."""
        mock_whisperx.load_align_model.side_effect = Exception("Model load failed")

        provider = WhisperXAlignmentProvider(device="cpu")
        segments = [
            TranscriptSegment(text="مرحبا", start=0.0, end=1.0, timestamp_source=TimestampSource.PROVIDER),
        ]

        result = provider.align("/fake/path.wav", segments, "ar")

        assert len(result) == 1
        assert result[0].timestamp_source == TimestampSource.APPROXIMATE
        assert "alignment_failed" in result[0].flags


class TestAlignmentProviderRegistry:
    """Tests for the alignment provider registry."""

    def test_get_known_provider(self):
        provider = get_alignment_provider("none")
        assert isinstance(provider, NoAlignmentProvider)

        provider = get_alignment_provider("whisperx")
        assert isinstance(provider, WhisperXAlignmentProvider)

    def test_get_unknown_provider_fallback(self):
        provider = get_alignment_provider("unknown")
        assert isinstance(provider, NoAlignmentProvider)

    def test_list_providers(self):
        providers = list_alignment_providers()
        assert "none" in providers
        assert "whisperx" in providers


class TestAlignTranscript:
    """Tests for the high-level align_transcript function."""

    def test_align_disabled_returns_unchanged(self):
        """When provider is 'none', should return segments unchanged but marked approximate."""
        canonical = CanonicalTranscript(
            full_text="مرحبا بكم",
            segments=[
                TranscriptSegment(text="مرحبا", start=0.0, end=1.0, timestamp_source=TimestampSource.PROVIDER),
                TranscriptSegment(text="بكم", start=1.0, end=2.0, timestamp_source=TimestampSource.PROVIDER),
            ],
            language_detected="ar",
            provider="gemini",
            model="gemini-1.5-flash",
            processing_time=1.0,
            segments_count=2,
        )

        result = align_transcript("/fake/path.wav", canonical, "ar", provider_name="none")

        assert result.full_text == "مرحبا بكم"
        assert len(result.segments) == 2
        assert result.segments[0].timestamp_source == TimestampSource.APPROXIMATE
        assert result.metadata["alignment_provider"] == "none"

    def test_align_preserves_metadata(self):
        """Alignment should preserve and extend metadata."""
        canonical = CanonicalTranscript(
            full_text="مرحبا",
            segments=[TranscriptSegment(text="مرحبا", start=0.0, end=1.0)],
            language_detected="ar",
            provider="gemini",
            model="gemini-1.5-flash",
            processing_time=1.0,
            segments_count=1,
            metadata={"custom": "value"},
        )

        result = align_transcript("/fake/path.wav", canonical, "ar", provider_name="none")

        assert result.metadata["custom"] == "value"
        assert result.metadata["alignment_provider"] == "none"

    @patch("app.alignment.get_alignment_provider")
    def test_align_delegates_to_provider(self, mock_get_provider):
        """Should delegate to the provider's align method."""
        mock_provider = MagicMock()
        mock_provider.align.return_value = [
            TranscriptSegment(text="مرحبا", start=0.0, end=1.0, timestamp_source=TimestampSource.ALIGNMENT),
        ]
        mock_get_provider.return_value = mock_provider

        canonical = CanonicalTranscript(
            full_text="مرحبا",
            segments=[TranscriptSegment(text="مرحبا", start=0.0, end=1.0)],
            language_detected="ar",
            provider="gemini",
            model="gemini-1.5-flash",
            processing_time=1.0,
            segments_count=1,
        )

        result = align_transcript("/fake/path.wav", canonical, "ar", provider_name="whisperx")

        mock_provider.align.assert_called_once_with("/fake/path.wav", canonical.segments, "ar")
        assert result.segments[0].timestamp_source == TimestampSource.ALIGNMENT


class TestAlignmentIntegration:
    """Integration-style tests for alignment with canonical transcript schema."""

    def test_canonical_transcript_with_words_serialization(self):
        """Verify CanonicalTranscript with word timestamps serializes correctly."""
        canonical = CanonicalTranscript(
            full_text="مرحبا بكم",
            segments=[
                TranscriptSegment(
                    text="مرحبا",
                    start=0.0,
                    end=1.0,
                    words=[
                        WordTimestamp(word="مرحبا", start=0.0, end=0.5, confidence=0.9),
                    ],
                    timestamp_source=TimestampSource.ALIGNMENT,
                ),
            ],
            language_detected="ar",
            provider="gemini",
            model="gemini-1.5-flash",
            processing_time=1.0,
            segments_count=1,
        )

        # Test to_api_response (backward compatible)
        api_resp = canonical.to_api_response()
        assert "words" in api_resp["segments"][0]
        assert len(api_resp["segments"][0]["words"]) == 1

        # Test to_storage_json
        storage_json = canonical.to_storage_json()
        assert '"word": "مرحبا"' in storage_json
        assert '"timestamp_source": "alignment"' in storage_json

    def test_canonical_transcript_from_storage_json_with_words(self):
        """Verify round-trip through storage JSON preserves word timestamps."""
        import json
        original = CanonicalTranscript(
            full_text="مرحبا",
            segments=[
                TranscriptSegment(
                    text="مرحبا",
                    start=0.0,
                    end=1.0,
                    words=[WordTimestamp(word="مرحبا", start=0.0, end=0.5, confidence=0.9)],
                    timestamp_source=TimestampSource.ALIGNMENT,
                ),
            ],
            language_detected="ar",
            provider="gemini",
            model="gemini-1.5-flash",
            processing_time=1.0,
            segments_count=1,
        )

        storage_json = original.to_storage_json()
        restored = CanonicalTranscript.from_storage_json(
            storage_json,
            full_text="مرحبا",
            language_detected="ar",
            provider="gemini",
            model="gemini-1.5-flash",
            processing_time=1.0,
        )

        assert len(restored.segments) == 1
        assert len(restored.segments[0].words) == 1
        assert restored.segments[0].words[0].word == "مرحبا"
        assert restored.segments[0].timestamp_source == TimestampSource.ALIGNMENT