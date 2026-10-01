"""
Benchmark categories and configuration.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path


@dataclass
class BenchmarkCategory:
    name: str
    description: str
    audio_file: str
    reference_file: str
    expected_difficulty: str  # low, medium, high, very_high
    expected_speakers: int
    dialect: str
    duration: float  # seconds
    # Quality thresholds for regression detection
    max_wer: float = 0.15
    max_cer: float = 0.08
    max_segment_mae: float = 1.0
    min_word_coverage: float = 0.80
    min_speaker_accuracy: float = 0.70
    max_rtf: float = 2.0


# Category definitions
CATEGORIES: Dict[str, BenchmarkCategory] = {
    "clean_msa": BenchmarkCategory(
        name="Clean MSA",
        description="Modern Standard Arabic, studio quality, single speaker",
        audio_file="clean_msa_01.wav",
        reference_file="clean_msa_01.json",
        expected_difficulty="low",
        expected_speakers=1,
        dialect="msa",
        duration=30.0,
        max_wer=0.08,
        max_cer=0.03,
        max_segment_mae=0.3,
        min_word_coverage=0.95,
        min_speaker_accuracy=0.98,
        max_rtf=1.0,
    ),
    "egyptian": BenchmarkCategory(
        name="Egyptian Dialect",
        description="Egyptian Arabic, conversational",
        audio_file="egyptian_01.wav",
        reference_file="egyptian_01.json",
        expected_difficulty="medium",
        expected_speakers=1,
        dialect="ar-EG",
        duration=30.0,
        max_wer=0.12,
        max_cer=0.05,
        max_segment_mae=0.5,
        min_word_coverage=0.90,
        min_speaker_accuracy=0.95,
        max_rtf=1.5,
    ),
    "gulf": BenchmarkCategory(
        name="Gulf Dialect",
        description="Gulf Arabic (KSA/UAE/Qatar), conversational",
        audio_file="gulf_01.wav",
        reference_file="gulf_01.json",
        expected_difficulty="medium",
        expected_speakers=1,
        dialect="ar-AE",
        duration=30.0,
        max_wer=0.12,
        max_cer=0.05,
        max_segment_mae=0.5,
        min_word_coverage=0.90,
        min_speaker_accuracy=0.95,
        max_rtf=1.5,
    ),
    "levantine": BenchmarkCategory(
        name="Levantine Dialect",
        description="Levantine Arabic (Syria/Lebanon/Jordan/Palestine)",
        audio_file="levantine_01.wav",
        reference_file="levantine_01.json",
        expected_difficulty="medium",
        expected_speakers=1,
        dialect="ar-SY",
        duration=30.0,
        max_wer=0.12,
        max_cer=0.05,
        max_segment_mae=0.5,
        min_word_coverage=0.90,
        min_speaker_accuracy=0.95,
        max_rtf=1.5,
    ),
    "maghrebi": BenchmarkCategory(
        name="Maghrebi Dialect",
        description="North African Arabic (Morocco/Algeria/Tunisia)",
        audio_file="maghrebi_01.wav",
        reference_file="maghrebi_01.json",
        expected_difficulty="high",
        expected_speakers=1,
        dialect="ar-MA",
        duration=30.0,
        max_wer=0.18,
        max_cer=0.08,
        max_segment_mae=0.8,
        min_word_coverage=0.85,
        min_speaker_accuracy=0.90,
        max_rtf=2.0,
    ),
    "noisy_phone": BenchmarkCategory(
        name="Noisy Phone Audio",
        description="Phone call quality with background noise",
        audio_file="noisy_phone_01.wav",
        reference_file="noisy_phone_01.json",
        expected_difficulty="high",
        expected_speakers=1,
        dialect="ar",
        duration=30.0,
        max_wer=0.25,
        max_cer=0.12,
        max_segment_mae=1.5,
        min_word_coverage=0.75,
        min_speaker_accuracy=0.85,
        max_rtf=2.0,
    ),
    "multi_speaker": BenchmarkCategory(
        name="Multiple Speakers",
        description="2-4 speakers, clear turn-taking",
        audio_file="multi_speaker_01.wav",
        reference_file="multi_speaker_01.json",
        expected_difficulty="medium",
        expected_speakers=3,
        dialect="ar",
        duration=60.0,
        max_wer=0.15,
        max_cer=0.06,
        max_segment_mae=0.8,
        min_word_coverage=0.85,
        min_speaker_accuracy=0.80,
        max_rtf=2.0,
    ),
    "rapid_turns": BenchmarkCategory(
        name="Rapid Turn-taking",
        description="Fast speaker switches (< 1s)",
        audio_file="rapid_turns_01.wav",
        reference_file="rapid_turns_01.json",
        expected_difficulty="high",
        expected_speakers=2,
        dialect="ar",
        duration=60.0,
        max_wer=0.20,
        max_cer=0.08,
        max_segment_mae=1.2,
        min_word_coverage=0.80,
        min_speaker_accuracy=0.75,
        max_rtf=2.5,
    ),
    "overlapping": BenchmarkCategory(
        name="Overlapping Speech",
        description="Simultaneous speakers",
        audio_file="overlapping_01.wav",
        reference_file="overlapping_01.json",
        expected_difficulty="very_high",
        expected_speakers=2,
        dialect="ar",
        duration=60.0,
        max_wer=0.30,
        max_cer=0.15,
        max_segment_mae=2.0,
        min_word_coverage=0.70,
        min_speaker_accuracy=0.65,
        max_rtf=3.0,
    ),
    "code_switch": BenchmarkCategory(
        name="Arabic-English Code Switching",
        description="Mixed language content",
        audio_file="code_switch_01.wav",
        reference_file="code_switch_01.json",
        expected_difficulty="medium",
        expected_speakers=1,
        dialect="ar-EN",
        duration=60.0,
        max_wer=0.15,
        max_cer=0.06,
        max_segment_mae=0.8,
        min_word_coverage=0.85,
        min_speaker_accuracy=0.95,
        max_rtf=2.0,
    ),
}


def get_category(name: str) -> Optional[BenchmarkCategory]:
    """Get category by name."""
    return CATEGORIES.get(name)


def list_categories() -> List[str]:
    """List all category names."""
    return list(CATEGORIES.keys())


def get_fixture_paths() -> Dict[str, Dict[str, Path]]:
    """Get paths to all fixture files."""
    base_audio = Path(__file__).parent.parent / "fixtures" / "audio"
    base_ref = Path(__file__).parent.parent / "fixtures" / "reference"
    
    paths = {}
    for cat_name, cat in CATEGORIES.items():
        paths[cat_name] = {
            "audio": base_audio / cat.audio_file,
            "reference": base_ref / cat.reference_file,
        }
    return paths