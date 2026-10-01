"""
Word-level alignment providers.
Keeps alignment behind an interface — providers can be swapped or disabled.
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from pathlib import Path

# Optional imports — may not be installed
try:
    import whisperx
    WHISPERX_AVAILABLE = True
except ImportError:
    whisperx = None
    WHISPERX_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False

from app.transcript_schema import (
    TranscriptSegment,
    WordTimestamp,
    TimestampSource,
    CanonicalTranscript,
)

logger = logging.getLogger(__name__)


class AlignmentProvider(ABC):
    """Abstract interface for word-level alignment providers."""

    @abstractmethod
    def align(
        self,
        audio_path: str,
        segments: List[TranscriptSegment],
        language: str,
    ) -> List[TranscriptSegment]:
        """
        Align transcript segments to audio, producing word-level timestamps.

        Args:
            audio_path: Path to audio file
            segments: Transcript segments with text and segment-level timestamps
            language: Language code (e.g., "ar", "en")

        Returns:
            Segments with word-level timestamps added, timestamp_source updated
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the alignment provider is available (dependencies installed, model loaded)."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging/metadata."""
        ...

    @property
    @abstractmethod
    def model(self) -> str:
        """Model identifier for metadata."""
        ...


class NoAlignmentProvider(AlignmentProvider):
    """Disabled alignment provider — returns segments unchanged with UNKNOWN timestamp_source."""

    name = "none"
    model = "none"

    def is_available(self) -> bool:
        return True

    def align(
        self,
        audio_path: str,
        segments: List[TranscriptSegment],
        language: str,
    ) -> List[TranscriptSegment]:
        logger.info("Alignment disabled — preserving segment-level timestamps")
        # Mark existing segments as approximate since no alignment was performed
        for seg in segments:
            if seg.timestamp_source == TimestampSource.PROVIDER:
                seg.timestamp_source = TimestampSource.APPROXIMATE
        return segments


class WhisperXAlignmentProvider(AlignmentProvider):
    """
    WhisperX-based word-level alignment.
    Requires: pip install whisperx torch
    GPU recommended but CPU fallback available.
    """

    name = "whisperx"
    model = "whisperx"

    def __init__(self, device: str = "cpu", compute_type: str = "int8"):
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._align_model = None
        self._metadata = None

    def is_available(self) -> bool:
        return WHISPERX_AVAILABLE and TORCH_AVAILABLE

    def _load_model(self):
        """Lazy-load WhisperX models."""
        if self._model is not None:
            return

        logger.info(f"Loading WhisperX alignment model on {self.device}...")

        # Load alignment model for the language
        # Note: WhisperX uses wav2vec2 for alignment
        try:
            self._model = whisperx.load_align_model(
                language_code="ar",  # Default to Arabic; will reload per language if needed
                device=self.device,
            )
            self._align_model, self._metadata = self._model
        except Exception as e:
            logger.warning(f"Failed to load Arabic alignment model, trying multilingual: {e}")
            # Fallback to multilingual alignment model
            self._align_model, self._metadata = whisperx.load_align_model(
                language_code="multilingual",
                device=self.device,
            )

    def align(
        self,
        audio_path: str,
        segments: List[TranscriptSegment],
        language: str,
    ) -> List[TranscriptSegment]:
        if not segments:
            return segments

        if not self.is_available():
            logger.warning("WhisperX not available — falling back to no alignment")
            return NoAlignmentProvider().align(audio_path, segments, language)

        try:
            self._load_model()

            # Load audio
            audio = whisperx.load_audio(audio_path)

            # Convert segments to WhisperX format
            whisperx_segments = [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                }
                for seg in segments
            ]

            # Run alignment
            logger.info(f"Running WhisperX alignment for {len(segments)} segments...")
            
            # Reload alignment model for the specific language if needed
            try:
                align_model, metadata = whisperx.load_align_model(
                    language_code=language,
                    device=self.device,
                )
            except Exception:
                # Use already loaded model as fallback
                align_model, metadata = self._align_model, self._metadata

            result = whisperx.align(
                whisperx_segments,
                align_model,
                metadata,
                audio,
                self.device,
                return_char_alignments=False,
            )

            # Convert back to our segment format with word timestamps
            aligned_segments = []
            for i, (orig_seg, aligned_seg) in enumerate(zip(segments, result["segments"])):
                words = []
                for w in aligned_seg.get("words", []):
                    words.append(WordTimestamp(
                        word=w.get("word", "").strip(),
                        start=float(w.get("start", 0)),
                        end=float(w.get("end", 0)),
                        confidence=w.get("score"),
                    ))

                # Filter out empty words
                words = [w for w in words if w.word]

                aligned_seg_obj = TranscriptSegment(
                    text=orig_seg.text,
                    start=orig_seg.start,
                    end=orig_seg.end,
                    speaker=orig_seg.speaker,
                    words=words,
                    confidence=orig_seg.confidence,
                    flags=orig_seg.flags,
                    timestamp_source=TimestampSource.ALIGNMENT,
                )
                aligned_segments.append(aligned_seg_obj)

            logger.info(f"✅ WhisperX alignment completed — {sum(len(s.words) for s in aligned_segments)} words aligned")
            return aligned_segments

        except Exception as e:
            logger.error(f"WhisperX alignment failed: {e}")
            # Preserve original segments on failure
            for seg in segments:
                seg.flags = list(seg.flags) + ["alignment_failed"]
                if seg.timestamp_source == TimestampSource.PROVIDER:
                    seg.timestamp_source = TimestampSource.APPROXIMATE
            return segments


# Provider registry
_ALIGNMENT_PROVIDERS: Dict[str, AlignmentProvider] = {
    "none": NoAlignmentProvider(),
    "whisperx": WhisperXAlignmentProvider(),
}


def get_alignment_provider(name: str) -> AlignmentProvider:
    """Get alignment provider by name."""
    provider = _ALIGNMENT_PROVIDERS.get(name.lower())
    if provider is None:
        logger.warning(f"Unknown alignment provider '{name}', using 'none'")
        return _ALIGNMENT_PROVIDERS["none"]
    return provider


def list_alignment_providers() -> List[str]:
    """List available alignment provider names."""
    return list(_ALIGNMENT_PROVIDERS.keys())


def align_transcript(
    audio_path: str,
    canonical: CanonicalTranscript,
    language: str,
    provider_name: str = "none",
) -> CanonicalTranscript:
    """
    Run word-level alignment on a canonical transcript.

    Args:
        audio_path: Path to audio file
        canonical: Canonical transcript with segment-level timestamps
        language: Language code
        provider_name: Alignment provider to use ("none", "whisperx")

    Returns:
        Updated CanonicalTranscript with word-level timestamps
    """
    provider = get_alignment_provider(provider_name)

    if not provider.is_available():
        logger.warning(f"Alignment provider '{provider_name}' not available, using 'none'")
        provider = get_alignment_provider("none")

    logger.info(f"Running alignment with provider: {provider.name}")

    aligned_segments = provider.align(audio_path, canonical.segments, language)

    # Create new canonical transcript with aligned segments
    return CanonicalTranscript(
        full_text=canonical.full_text,
        segments=aligned_segments,
        language_detected=canonical.language_detected,
        provider=canonical.provider,
        model=canonical.model,
        processing_time=canonical.processing_time,
        segments_count=len(aligned_segments),
        metadata={
            **canonical.metadata,
            "alignment_provider": provider.name,
            "alignment_model": provider.model,
        },
    )