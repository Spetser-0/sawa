"""
Tests for ai_services module — speaker diarization merge algorithm (Phase 3).
"""
import pytest
from app.ai_services import merge_diarization_with_transcript


class TestMergeDiarizationWithTranscript:
    """Tests for the interval overlap coverage speaker assignment algorithm."""

    def test_full_coverage_by_one_speaker(self):
        """Single speaker fully covers segment → assigned with high coverage."""
        segments = [{"start": 10.0, "end": 20.0, "text": "Hello world"}]
        speakers = [{"start": 0.0, "end": 30.0, "speaker": "SPEAKER_00"}]

        result = merge_diarization_with_transcript(segments, speakers)

        assert len(result) == 1
        assert result[0]["speaker"] == "المتحدث 1"
        assert result[0]["speaker_coverage"] == 1.0
        assert result[0]["flags"] == []

    def test_two_speakers_second_higher_coverage(self):
        """Second speaker has higher coverage → assigned to second speaker."""
        segments = [{"start": 10.0, "end": 20.0, "text": "Hello world"}]
        speakers = [
            {"start": 0.0, "end": 12.0, "speaker": "SPEAKER_00"},   # 2s overlap
            {"start": 12.0, "end": 30.0, "speaker": "SPEAKER_01"},  # 8s overlap
        ]

        result = merge_diarization_with_transcript(segments, speakers)

        assert result[0]["speaker"] == "المتحدث 2"
        assert result[0]["speaker_coverage"] == 0.8
        # First speaker has exactly 20% coverage (2s/10s), second has 80%
        # Both >= 20% → overlapping_speech flag is correctly added
        assert "overlapping_speech" in result[0]["flags"]

    def test_coverage_below_threshold(self):
        """Best coverage below threshold → unknown speaker with ambiguous flag."""
        segments = [{"start": 10.0, "end": 20.0, "text": "Hello world"}]
        speakers = [
            {"start": 0.0, "end": 11.0, "speaker": "SPEAKER_00"},   # 1s overlap = 10%
            {"start": 19.0, "end": 30.0, "speaker": "SPEAKER_01"},  # 1s overlap = 10%
        ]

        result = merge_diarization_with_transcript(segments, speakers, coverage_threshold=0.5)

        assert result[0]["speaker"] == "متحدث غير معروف"
        assert result[0]["speaker_coverage"] == 0.1
        assert "ambiguous_speaker" in result[0]["flags"]

    def test_no_speaker_match(self):
        """No overlapping speakers → unknown speaker, zero coverage."""
        segments = [{"start": 10.0, "end": 20.0, "text": "Hello world"}]
        speakers = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 25.0, "end": 30.0, "speaker": "SPEAKER_01"},
        ]

        result = merge_diarization_with_transcript(segments, speakers)

        assert result[0]["speaker"] == "متحدث غير معروف"
        assert result[0]["speaker_coverage"] == 0.0
        assert result[0]["flags"] == []

    def test_overlapping_speech_detected(self):
        """Two speakers with significant overlap → overlapping_speech flag."""
        segments = [{"start": 10.0, "end": 20.0, "text": "Hello world"}]
        speakers = [
            {"start": 8.0, "end": 16.0, "speaker": "SPEAKER_00"},   # 6s overlap = 60%
            {"start": 14.0, "end": 22.0, "speaker": "SPEAKER_01"},  # 6s overlap = 60%
        ]

        result = merge_diarization_with_transcript(segments, speakers, coverage_threshold=0.5)

        # First speaker has 60%, second has 60% - first wins (iteration order)
        assert result[0]["speaker"] == "المتحدث 1"
        assert "overlapping_speech" in result[0]["flags"]

    def test_zero_length_segment(self):
        """Zero or negative duration segment → invalid_segment flag."""
        segments = [{"start": 10.0, "end": 10.0, "text": "Empty"}]
        speakers = [{"start": 0.0, "end": 30.0, "speaker": "SPEAKER_00"}]

        result = merge_diarization_with_transcript(segments, speakers)

        assert result[0]["speaker"] == "متحدث غير معروف"
        assert result[0]["speaker_coverage"] == 0.0
        assert "invalid_segment" in result[0]["flags"]

    def test_speaker_interval_touching_no_overlap(self):
        """Speaker interval touches but doesn't overlap → no coverage."""
        segments = [{"start": 10.0, "end": 20.0, "text": "Hello"}]
        speakers = [{"start": 0.0, "end": 10.0, "speaker": "SPEAKER_00"}]  # ends exactly at segment start

        result = merge_diarization_with_transcript(segments, speakers)

        assert result[0]["speaker"] == "متحدث غير معروف"
        assert result[0]["speaker_coverage"] == 0.0

    def test_multiple_segments_different_speakers(self):
        """Multiple segments correctly assigned to different speakers."""
        segments = [
            {"start": 0.0, "end": 10.0, "text": "First segment"},
            {"start": 10.0, "end": 20.0, "text": "Second segment"},
            {"start": 20.0, "end": 30.0, "text": "Third segment"},
        ]
        speakers = [
            {"start": 0.0, "end": 15.0, "speaker": "SPEAKER_00"},
            {"start": 15.0, "end": 30.0, "speaker": "SPEAKER_01"},
        ]

        result = merge_diarization_with_transcript(segments, speakers)

        assert result[0]["speaker"] == "المتحدث 1"  # 100% coverage
        assert result[1]["speaker"] == "المتحدث 1"  # 5s/10s = 50% coverage (threshold met)
        assert result[2]["speaker"] == "المتحدث 2"  # 100% coverage

    def test_short_segment_partial_overlap(self):
        """Very short segment with partial overlap."""
        segments = [{"start": 10.0, "end": 10.5, "text": "Hi"}]  # 0.5s segment
        speakers = [{"start": 10.0, "end": 10.2, "speaker": "SPEAKER_00"}]  # 0.2s overlap = 40%

        result = merge_diarization_with_transcript(segments, speakers, coverage_threshold=0.5)

        assert result[0]["speaker"] == "متحدث غير معروف"
        assert result[0]["speaker_coverage"] == 0.4
        assert "ambiguous_speaker" in result[0]["flags"]

    def test_empty_segments_list(self):
        """Empty segments list returns empty result."""
        result = merge_diarization_with_transcript([], [])
        assert result == []

    def test_empty_speakers_list(self):
        """Empty speakers list → all segments get unknown speaker."""
        segments = [{"start": 0.0, "end": 10.0, "text": "Hello"}]
        result = merge_diarization_with_transcript(segments, [])

        assert result[0]["speaker"] == "متحدث غير معروف"
        assert result[0]["speaker_coverage"] == 0.0
        assert result[0]["flags"] == []

    def test_speaker_label_conversion(self):
        """Raw speaker labels converted to display names."""
        segments = [{"start": 0.0, "end": 10.0, "text": "Test"}]
        speakers = [
            {"start": 0.0, "end": 10.0, "speaker": "SPEAKER_00"},
            {"start": 10.0, "end": 20.0, "speaker": "SPEAKER_01"},
            {"start": 20.0, "end": 30.0, "speaker": "SPEAKER_02"},
        ]

        result = merge_diarization_with_transcript(segments, speakers)
        assert result[0]["speaker"] == "المتحدث 1"

    def test_coverage_precision(self):
        """Coverage is rounded to 3 decimal places."""
        segments = [{"start": 0.0, "end": 3.0, "text": "Test"}]  # 3s
        speakers = [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}]  # 1s = 33.333...%

        result = merge_diarization_with_transcript(segments, speakers, coverage_threshold=0.0)

        assert result[0]["speaker_coverage"] == 0.333

    def test_preserves_original_segment_fields(self):
        """All original segment fields preserved in output."""
        segments = [{
            "start": 0.0,
            "end": 10.0,
            "text": "Hello",
            "speaker": "old_speaker",
            "words": [{"word": "Hello", "start": 0.0, "end": 1.0}],
            "confidence": 0.9,
        }]
        speakers = [{"start": 0.0, "end": 10.0, "speaker": "SPEAKER_00"}]

        result = merge_diarization_with_transcript(segments, speakers)

        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 10.0
        assert result[0]["text"] == "Hello"
        assert result[0]["words"] == [{"word": "Hello", "start": 0.0, "end": 1.0}]
        assert result[0]["confidence"] == 0.9
        # speaker is overwritten, speaker_coverage and flags added
        assert "speaker_coverage" in result[0]
        assert "flags" in result[0]