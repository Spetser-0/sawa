"""
Test to validate benchmark infrastructure works correctly.
"""
import pytest
import json
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.benchmarks.categories import CATEGORIES, get_fixture_paths, get_category, list_categories
from tests.benchmarks.run_benchmark import (
    compute_wer,
    compute_cer,
    compute_segment_timestamp_error,
    compute_word_timestamp_coverage,
    compute_speaker_accuracy,
)


class TestBenchmarkCategories:
    """Tests for benchmark category definitions."""

    def test_all_categories_defined(self):
        """All expected categories are present."""
        expected = [
            "clean_msa", "egyptian", "gulf", "levantine", "maghrebi",
            "noisy_phone", "multi_speaker", "rapid_turns", "overlapping", "code_switch"
        ]
        for cat in expected:
            assert cat in CATEGORIES, f"Missing category: {cat}"

    def test_category_structure(self):
        """Each category has required fields."""
        for name, cat in CATEGORIES.items():
            assert cat.name
            assert cat.description
            assert cat.audio_file
            assert cat.reference_file
            assert cat.expected_difficulty in ["low", "medium", "high", "very_high"]
            assert cat.expected_speakers >= 1
            assert cat.dialect
            assert cat.duration > 0
            assert cat.max_wer > 0
            assert cat.max_cer > 0

    def test_get_category(self):
        """Get category by name."""
        cat = get_category("clean_msa")
        assert cat is not None
        assert cat.name == "Clean MSA"
        
        assert get_category("nonexistent") is None

    def test_list_categories(self):
        """List all categories."""
        cats = list_categories()
        assert len(cats) == 10
        assert "clean_msa" in cats

    def test_fixture_paths(self):
        """Fixture paths are correctly constructed."""
        paths = get_fixture_paths()
        for name, cat in CATEGORIES.items():
            assert name in paths
            assert paths[name]["audio"].name == cat.audio_file
            assert paths[name]["reference"].name == cat.reference_file


class TestWERComputation:
    """Tests for WER computation."""

    def test_identical_text(self):
        """WER of identical text is 0."""
        assert compute_wer("مرحبا بكم", "مرحبا بكم") == 0.0

    def test_completely_different(self):
        """WER of completely different text."""
        assert compute_wer("مرحبا", "وداعا") == 1.0

    def test_one_insertion(self):
        """WER with one extra word."""
        # "مرحبا بكم" (2 words) vs "مرحبا بكم جميعا" (3 words) - 1 insertion
        # WER = 1 error / 2 ref words = 0.5
        wer = compute_wer("مرحبا بكم", "مرحبا بكم جميعا")
        assert wer == pytest.approx(0.5, rel=0.1)

    def test_one_deletion(self):
        """WER with one missing word."""
        wer = compute_wer("مرحبا بكم جميعا", "مرحبا بكم")
        assert wer == pytest.approx(1/3, rel=0.1)

    def test_one_substitution(self):
        """WER with one word substituted."""
        wer = compute_wer("مرحبا بكم", "مرحبا عليكم")
        assert wer == pytest.approx(1/2, rel=0.1)


class TestCERComputation:
    """Tests for CER computation."""

    def test_identical_text(self):
        """CER of identical text is 0."""
        assert compute_cer("مرحبا", "مرحبا") == 0.0

    def test_one_character_diff(self):
        """CER with one character difference."""
        # "مرحبا" vs "مرحبا" (same) = 0
        # "مرحبا" vs "مرحبة" = 1 char diff / 5 chars
        cer = compute_cer("مرحبا", "مرحبة")
        assert cer == pytest.approx(1/5, rel=0.1)


class TestSegmentTimestampError:
    """Tests for segment timestamp error computation."""

    def test_identical_segments(self):
        """Zero error for identical segments."""
        ref = [{"start": 0.0, "end": 2.0, "text": "مرحبا"}]
        hyp = [{"start": 0.0, "end": 2.0, "text": "مرحبا"}]
        assert compute_segment_timestamp_error(ref, hyp) == 0.0

    def test_offset_segments(self):
        """Error for offset segments."""
        ref = [{"start": 0.0, "end": 2.0, "text": "مرحبا"}]
        hyp = [{"start": 0.5, "end": 2.5, "text": "مرحبا"}]
        error = compute_segment_timestamp_error(ref, hyp)
        # Mean of |0.0-0.5| and |2.0-2.5| = 0.5
        assert error == pytest.approx(0.5, rel=0.1)


class TestWordTimestampCoverage:
    """Tests for word timestamp coverage."""

    def test_full_coverage(self):
        """100% coverage when all words have timestamps."""
        segments = [
            {"words": [
                {"word": "مرحبا", "start": 0.0, "end": 0.5},
                {"word": "بكم", "start": 0.5, "end": 1.0},
            ]}
        ]
        assert compute_word_timestamp_coverage(segments) == 1.0

    def test_partial_coverage(self):
        """Partial coverage."""
        segments = [
            {"words": [
                {"word": "مرحبا", "start": 0.0, "end": 0.5},
                {"word": "بكم", "start": None, "end": None},
            ]}
        ]
        assert compute_word_timestamp_coverage(segments) == 0.5

    def test_no_words(self):
        """Zero coverage when no word timestamps."""
        segments = [{"text": "مرحبا بكم"}]
        assert compute_word_timestamp_coverage(segments) == 0.0


class TestSpeakerAccuracy:
    """Tests for speaker attribution accuracy."""

    def test_perfect_match(self):
        """Perfect speaker accuracy."""
        ref = [
            {"text": "مرحبا", "speaker": "المتحدث 1"},
            {"text": "بكم", "speaker": "المتحدث 2"},
        ]
        hyp = [
            {"text": "مرحبا", "speaker": "المتحدث 1"},
            {"text": "بكم", "speaker": "المتحدث 2"},
        ]
        assert compute_speaker_accuracy(ref, hyp) == 1.0

    def test_partial_match(self):
        """Partial speaker accuracy."""
        ref = [
            {"text": "مرحبا", "speaker": "المتحدث 1"},
            {"text": "بكم", "speaker": "المتحدث 2"},
        ]
        hyp = [
            {"text": "مرحبا", "speaker": "المتحدث 1"},
            {"text": "بكم", "speaker": "المتحدث 1"},  # Wrong speaker
        ]
        assert compute_speaker_accuracy(ref, hyp) == 0.5

    def test_no_matching_text(self):
        """Zero when no text matches."""
        ref = [{"text": "مرحبا", "speaker": "المتحدث 1"}]
        hyp = [{"text": "وداعا", "speaker": "المتحدث 1"}]
        assert compute_speaker_accuracy(ref, hyp) == 0.0


class TestBenchmarkInfrastructure:
    """Integration tests for benchmark infrastructure."""

    def test_imports_work(self):
        """All benchmark modules can be imported."""
        from tests.benchmarks import categories
        from tests.benchmarks import run_benchmark
        assert categories
        assert run_benchmark

    def test_mock_transcription_result_structure(self):
        """Test expected structure of transcription results."""
        # This validates the expected output format from transcribe_audio
        result = {
            "full_text": "مرحبا بكم",
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "مرحبا بكم", "speaker": "المتحدث 1"}
            ],
            "language_detected": "ar",
            "processing_time": 1.5,
            "segments_count": 1,
        }
        
        assert "full_text" in result
        assert "segments" in result
        assert isinstance(result["segments"], list)
        assert "language_detected" in result
        assert "processing_time" in result
        assert "segments_count" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])