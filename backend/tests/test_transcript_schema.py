"""
Tests for canonical transcript schema and validation (Phase 1).
"""
import pytest
import json
from app.transcript_schema import (
    TranscriptSegment,
    WordTimestamp,
    CanonicalTranscript,
    TimestampSource,
    normalize_gemini_output,
    normalize_groq_output,
    normalize_provider_output,
)


class TestWordTimestamp:
    def test_valid_word_timestamp(self):
        w = WordTimestamp(word="مرحبا", start=0.0, end=0.5, confidence=0.9)
        assert w.word == "مرحبا"
        assert w.start == 0.0
        assert w.end == 0.5
        assert w.confidence == 0.9

    def test_negative_start_raises(self):
        with pytest.raises(ValueError, match="word start must be >= 0"):
            WordTimestamp(word="test", start=-1.0, end=0.5)

    def test_negative_end_raises(self):
        with pytest.raises(ValueError, match="word end must be >= 0"):
            WordTimestamp(word="test", start=0.0, end=-0.5)

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError, match="word end must be >= start"):
            WordTimestamp(word="test", start=1.0, end=0.5)


class TestTranscriptSegment:
    def test_valid_segment_minimal(self):
        seg = TranscriptSegment(text="مرحبا بكم", start=0.0, end=2.5)
        assert seg.text == "مرحبا بكم"
        assert seg.start == 0.0
        assert seg.end == 2.5
        assert seg.speaker is None
        assert seg.words == []
        assert seg.confidence is None
        assert seg.flags == []
        assert seg.timestamp_source == TimestampSource.UNKNOWN

    def test_valid_segment_full(self):
        seg = TranscriptSegment(
            text="مرحبا بكم",
            start=12.34,
            end=14.10,
            speaker="المتحدث 1",
            words=[WordTimestamp(word="مرحبا", start=12.34, end=12.8)],
            confidence=0.95,
            flags=["approximate"],
            timestamp_source=TimestampSource.PROVIDER,
        )
        assert seg.speaker == "المتحدث 1"
        assert len(seg.words) == 1
        assert seg.confidence == 0.95
        assert seg.flags == ["approximate"]
        assert seg.timestamp_source == TimestampSource.PROVIDER

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="segment text must be non-empty"):
            TranscriptSegment(text="", start=0.0, end=1.0)

    def test_whitespace_only_text_raises(self):
        with pytest.raises(ValueError, match="segment text must be non-empty"):
            TranscriptSegment(text="   ", start=0.0, end=1.0)

    def test_negative_start_raises(self):
        with pytest.raises(ValueError, match="segment start must be >= 0"):
            TranscriptSegment(text="test", start=-1.0, end=1.0)

    def test_negative_end_raises(self):
        with pytest.raises(ValueError, match="segment end must be >= 0"):
            TranscriptSegment(text="test", start=0.0, end=-1.0)

    def test_reversed_timestamps_raises(self):
        with pytest.raises(ValueError, match="segment end must be >= start"):
            TranscriptSegment(text="test", start=5.0, end=1.0)

    def test_word_outside_segment_raises(self):
        with pytest.raises(ValueError, match="word timestamps must be within segment boundaries"):
            TranscriptSegment(
                text="مرحبا بكم",
                start=10.0,
                end=12.0,
                words=[WordTimestamp(word="مرحبا", start=9.0, end=9.5)],
            )

    def test_word_end_outside_segment_raises(self):
        with pytest.raises(ValueError, match="word timestamps must be within segment boundaries"):
            TranscriptSegment(
                text="مرحبا بكم",
                start=10.0,
                end=12.0,
                words=[WordTimestamp(word="بكم", start=11.5, end=12.5)],
            )


class TestCanonicalTranscript:
    def test_valid_canonical_transcript(self):
        segments = [
            TranscriptSegment(text="مرحبا", start=0.0, end=1.0),
            TranscriptSegment(text="بكم", start=1.0, end=2.0),
        ]
        ct = CanonicalTranscript(
            full_text="مرحبا بكم",
            segments=segments,
            language_detected="ar",
            provider="gemini",
            model="gemini-1.5-flash",
            processing_time=1.5,
            segments_count=2,
        )
        assert ct.full_text == "مرحبا بكم"
        assert len(ct.segments) == 2
        assert ct.provider == "gemini"
        assert ct.model == "gemini-1.5-flash"

    def test_empty_full_text_raises(self):
        with pytest.raises(ValueError, match="full_text must be non-empty"):
            CanonicalTranscript(
                full_text="",
                segments=[],
                language_detected="ar",
                provider="gemini",
                processing_time=1.0,
                segments_count=0,
            )

    def test_segments_count_mismatch_raises(self):
        with pytest.raises(ValueError, match="segments_count must match"):
            CanonicalTranscript(
                full_text="test",
                segments=[TranscriptSegment(text="test", start=0.0, end=1.0)],
                language_detected="ar",
                provider="gemini",
                processing_time=1.0,
                segments_count=5,
            )

    def test_to_api_response_backward_compatible(self):
        segments = [
            TranscriptSegment(text="مرحبا", start=0.0, end=1.0, speaker="المتحدث 1"),
        ]
        ct = CanonicalTranscript(
            full_text="مرحبا",
            segments=segments,
            language_detected="ar",
            provider="gemini",
            processing_time=1.0,
            segments_count=1,
        )
        api_resp = ct.to_api_response()
        assert api_resp["full_text"] == "مرحبا"
        assert len(api_resp["segments"]) == 1
        assert api_resp["segments"][0]["text"] == "مرحبا"
        assert api_resp["segments"][0]["speaker"] == "المتحدث 1"
        assert "timestamp_source" not in api_resp["segments"][0]  # not in API response
        assert "confidence" not in api_resp["segments"][0]
        assert "flags" not in api_resp["segments"][0]

    def test_to_storage_json_roundtrip(self):
        segments = [
            TranscriptSegment(text="مرحبا", start=0.0, end=1.0, speaker="المتحدث 1"),
        ]
        ct = CanonicalTranscript(
            full_text="مرحبا",
            segments=segments,
            language_detected="ar",
            provider="gemini",
            model="gemini-1.5-flash",
            processing_time=1.0,
            segments_count=1,
        )
        storage_json = ct.to_storage_json()
        restored = CanonicalTranscript.from_storage_json(
            storage_json,
            full_text="مرحبا",
            language_detected="ar",
            provider="gemini",
            model="gemini-1.5-flash",
            processing_time=1.0,
        )
        assert restored.full_text == "مرحبا"
        assert len(restored.segments) == 1
        assert restored.segments[0].text == "مرحبا"
        assert restored.segments[0].speaker == "المتحدث 1"


class TestNormalizeGeminiOutput:
    def test_normalize_gemini_basic(self):
        raw = {
            "full_text": "مرحبا بكم في سوى",
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "مرحبا بكم"},
                {"start": 2.5, "end": 5.0, "text": "في سوى"},
            ],
            "language_detected": "ar",
            "processing_time": 2.3,
            "segments_count": 2,
        }
        canonical = normalize_gemini_output(raw)
        assert canonical.full_text == "مرحبا بكم في سوى"
        assert len(canonical.segments) == 2
        assert canonical.segments[0].timestamp_source == TimestampSource.UNKNOWN
        assert canonical.provider == "gemini"
        assert canonical.model == "gemini-1.5-flash"

    def test_normalize_gemini_empty_segment_filtered(self):
        raw = {
            "full_text": "مرحبا",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "مرحبا"},
                {"start": 1.0, "end": 2.0, "text": "   "},
            ],
            "language_detected": "ar",
            "processing_time": 1.0,
            "segments_count": 2,
        }
        canonical = normalize_gemini_output(raw)
        assert len(canonical.segments) == 1  # empty segment filtered out

    def test_normalize_gemini_preserves_extra_metadata(self):
        raw = {
            "full_text": "مرحبا",
            "segments": [{"start": 0.0, "end": 1.0, "text": "مرحبا"}],
            "language_detected": "ar",
            "processing_time": 1.0,
            "segments_count": 1,
            "custom_field": "custom_value",
        }
        canonical = normalize_gemini_output(raw)
        assert "custom_field" in canonical.metadata
        assert canonical.metadata["custom_field"] == "custom_value"

    def test_normalize_gemini_text_only_no_segments(self):
        """Gemini may return only full_text without segments."""
        raw = {
            "full_text": "مرحبا بكم",
            "segments": [],
            "language_detected": "ar",
            "processing_time": 1.0,
            "segments_count": 0,
        }
        canonical = normalize_gemini_output(raw)
        assert canonical.full_text == "مرحبا بكم"
        assert canonical.segments == []
        assert canonical.segments_count == 0


class TestNormalizeGroqOutput:
    def test_normalize_groq_basic(self):
        raw = {
            "full_text": "مرحبا بكم",
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "مرحبا بكم"},
            ],
            "language_detected": "ar",
            "processing_time": 1.2,
            "segments_count": 1,
        }
        canonical = normalize_groq_output(raw)
        assert canonical.full_text == "مرحبا بكم"
        assert len(canonical.segments) == 1
        assert canonical.segments[0].timestamp_source == TimestampSource.PROVIDER
        assert canonical.provider == "groq"
        assert canonical.model == "whisper-large-v3-turbo"


class TestNormalizeProviderOutput:
    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider: unknown"):
            normalize_provider_output({}, "unknown")


class TestSegmentSerialization:
    def test_segment_model_dump_includes_all_fields(self):
        seg = TranscriptSegment(
            text="مرحبا",
            start=0.0,
            end=1.0,
            speaker="المتحدث 1",
            words=[WordTimestamp(word="مرحبا", start=0.0, end=0.5)],
            confidence=0.9,
            flags=["test"],
            timestamp_source=TimestampSource.PROVIDER,
        )
        dumped = seg.model_dump()
        assert dumped["text"] == "مرحبا"
        assert dumped["start"] == 0.0
        assert dumped["end"] == 1.0
        assert dumped["speaker"] == "المتحدث 1"
        assert len(dumped["words"]) == 1
        assert dumped["confidence"] == 0.9
        assert dumped["flags"] == ["test"]
        assert dumped["timestamp_source"] == "provider"

    def test_canonical_model_dump_includes_all_fields(self):
        segments = [TranscriptSegment(text="مرحبا", start=0.0, end=1.0)]
        ct = CanonicalTranscript(
            full_text="مرحبا",
            segments=segments,
            language_detected="ar",
            provider="gemini",
            model="gemini-1.5-flash",
            processing_time=1.0,
            segments_count=1,
            metadata={"extra": "data"},
        )
        dumped = ct.model_dump()
        assert dumped["full_text"] == "مرحبا"
        assert dumped["provider"] == "gemini"
        assert dumped["model"] == "gemini-1.5-flash"
        assert dumped["metadata"]["extra"] == "data"


class TestPhase2TimestampProvenance:
    """Phase 2: Verify timestamp source semantics are explicit."""

    def test_gemini_segments_marked_unknown(self):
        """Gemini segment timestamps must be marked UNKNOWN, not PROVIDER."""
        raw = {
            "full_text": "مرحبا بكم",
            "segments": [{"start": 0.0, "end": 2.5, "text": "مرحبا بكم"}],
            "language_detected": "ar",
            "processing_time": 1.0,
            "segments_count": 1,
        }
        canonical = normalize_gemini_output(raw)
        assert canonical.segments[0].timestamp_source == TimestampSource.UNKNOWN

    def test_groq_segments_marked_provider(self):
        """Groq segment timestamps are verifiable and marked PROVIDER."""
        raw = {
            "full_text": "مرحبا بكم",
            "segments": [{"start": 0.0, "end": 2.5, "text": "مرحبا بكم"}],
            "language_detected": "ar",
            "processing_time": 1.0,
            "segments_count": 1,
        }
        canonical = normalize_groq_output(raw)
        assert canonical.segments[0].timestamp_source == TimestampSource.PROVIDER

    def test_gemini_fallback_to_groq_preserves_groq_timestamps(self):
        """When Gemini fails and Groq succeeds, Groq timestamps are PROVIDER."""
        raw = {
            "full_text": "مرحبا بكم",
            "segments": [{"start": 1.5, "end": 3.0, "text": "مرحبا بكم"}],
            "language_detected": "ar",
            "processing_time": 1.0,
            "segments_count": 1,
        }
        canonical = normalize_groq_output(raw, provider="groq", model="whisper-large-v3-turbo")
        assert canonical.provider == "groq"
        assert canonical.segments[0].timestamp_source == TimestampSource.PROVIDER

    def test_gemini_malformed_json_raises_clear_error(self):
        """Malformed JSON from Gemini fails safely with clear error."""
        # This tests the transcription.py layer, not the schema directly
        # The schema validation would catch invalid segment data
        raw = {
            "full_text": "مرحبا",
            "segments": [{"start": "invalid", "end": 1.0, "text": "test"}],
            "language_detected": "ar",
            "processing_time": 1.0,
            "segments_count": 1,
        }
        with pytest.raises(ValueError, match="could not convert string to float"):
            normalize_gemini_output(raw)

    def test_gemini_reversed_timestamps_raises(self):
        """Reversed timestamps in Gemini output are rejected."""
        raw = {
            "full_text": "مرحبا",
            "segments": [{"start": 5.0, "end": 1.0, "text": "مرحبا"}],
            "language_detected": "ar",
            "processing_time": 1.0,
            "segments_count": 1,
        }
        with pytest.raises(ValueError, match="segment end must be >= start"):
            normalize_gemini_output(raw)

    def test_gemini_negative_timestamp_raises(self):
        """Negative timestamps in Gemini output are rejected."""
        raw = {
            "full_text": "مرحبا",
            "segments": [{"start": -1.0, "end": 1.0, "text": "مرحبا"}],
            "language_detected": "ar",
            "processing_time": 1.0,
            "segments_count": 1,
        }
        with pytest.raises(ValueError, match="segment start must be >= 0"):
            normalize_gemini_output(raw)