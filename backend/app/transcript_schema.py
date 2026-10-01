"""
Canonical transcript schema and validation.
All providers must normalize their output through this module.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


class TimestampSource(str, Enum):
    PROVIDER = "provider"
    ALIGNMENT = "alignment"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float
    confidence: Optional[float] = None

    @field_validator("start")
    @classmethod
    def validate_start(cls, v: float) -> float:
        if v < 0:
            raise ValueError("word start must be >= 0")
        return v

    @field_validator("end")
    @classmethod
    def validate_end(cls, v: float) -> float:
        if v < 0:
            raise ValueError("word end must be >= 0")
        return v

    @model_validator(mode="after")
    def validate_word_order(self) -> "WordTimestamp":
        if self.end < self.start:
            raise ValueError("word end must be >= start")
        return self


class TranscriptSegment(BaseModel):
    text: str
    start: float
    end: float
    speaker: Optional[str] = None
    words: List[WordTimestamp] = Field(default_factory=list)
    confidence: Optional[float] = None
    flags: List[str] = Field(default_factory=list)
    timestamp_source: TimestampSource = TimestampSource.UNKNOWN

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        normalized = v.strip()
        if not normalized:
            raise ValueError("segment text must be non-empty after normalization")
        return normalized

    @field_validator("start")
    @classmethod
    def validate_start(cls, v: float) -> float:
        if v < 0:
            raise ValueError("segment start must be >= 0")
        return v

    @field_validator("end")
    @classmethod
    def validate_end(cls, v: float) -> float:
        if v < 0:
            raise ValueError("segment end must be >= 0")
        return v

    @model_validator(mode="after")
    def validate_segment_order(self) -> "TranscriptSegment":
        if self.end < self.start:
            raise ValueError("segment end must be >= start")
        return self

    @model_validator(mode="after")
    def validate_word_timestamps(self) -> "TranscriptSegment":
        if self.words:
            for w in self.words:
                if w.start < self.start or w.end > self.end:
                    raise ValueError("word timestamps must be within segment boundaries")
        return self


class CanonicalTranscript(BaseModel):
    full_text: str
    segments: List[TranscriptSegment]
    language_detected: str
    provider: str
    model: Optional[str] = None
    processing_time: float
    segments_count: int
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("full_text")
    @classmethod
    def validate_full_text(cls, v: str) -> str:
        normalized = v.strip()
        if not normalized:
            raise ValueError("full_text must be non-empty after normalization")
        return normalized

    @model_validator(mode="after")
    def validate_segments_count(self) -> "CanonicalTranscript":
        if self.segments_count != len(self.segments):
            raise ValueError("segments_count must match actual segments length")
        return self

    def to_api_response(self) -> dict:
        """Convert to the existing API response format (backward compatible)."""
        return {
            "full_text": self.full_text,
            "segments": [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                    "speaker": seg.speaker,
                    "words": [w.model_dump() for w in seg.words] if seg.words else None,
                }
                for seg in self.segments
            ],
            "language_detected": self.language_detected,
            "processing_time": self.processing_time,
            "segments_count": self.segments_count,
        }

    def to_storage_json(self) -> str:
        """Serialize segments for database storage (JSON text column)."""
        import json
        return json.dumps(
            [seg.model_dump() for seg in self.segments],
            ensure_ascii=False
        )

    @classmethod
    def from_storage_json(cls, json_str: str, full_text: str, language_detected: str,
                          provider: str, model: Optional[str], processing_time: float) -> "CanonicalTranscript":
        """Deserialize from database storage format."""
        import json
        segments_data = json.loads(json_str) if json_str else []
        segments = [TranscriptSegment(**seg) for seg in segments_data]
        return cls(
            full_text=full_text,
            segments=segments,
            language_detected=language_detected,
            provider=provider,
            model=model,
            processing_time=processing_time,
            segments_count=len(segments),
        )


def normalize_gemini_output(raw: dict, provider: str = "gemini", model: str = "gemini-1.5-flash") -> CanonicalTranscript:
    """Normalize Gemini provider output to canonical schema.

    Gemini does not provide verifiable audio-aligned timestamps. The model generates
    segment boundaries as part of its text output, but these are not grounded in
    actual audio timing. We mark them as UNKNOWN to prevent downstream consumers
    from treating them as precise timestamps.
    """
    segments = []
    for seg in raw.get("segments", []):
        if not seg.get("text", "").strip():
            continue
        segments.append(TranscriptSegment(
            text=seg["text"].strip(),
            start=float(seg["start"]),
            end=float(seg["end"]),
            speaker=seg.get("speaker"),
            words=[WordTimestamp(**w) for w in seg.get("words", [])] if seg.get("words") else [],
            confidence=seg.get("confidence"),
            flags=seg.get("flags", []),
            timestamp_source=TimestampSource.UNKNOWN,
        ))

    return CanonicalTranscript(
        full_text=raw["full_text"].strip(),
        segments=segments,
        language_detected=raw.get("language_detected", "ar"),
        provider=provider,
        model=model,
        processing_time=raw.get("processing_time", 0.0),
        segments_count=len(segments),
        metadata={k: v for k, v in raw.items() if k not in {
            "full_text", "segments", "language_detected", "processing_time", "segments_count", "provider"
        }},
    )


def normalize_groq_output(raw: dict, provider: str = "groq", model: str = "whisper-large-v3-turbo") -> CanonicalTranscript:
    """Normalize Groq provider output to canonical schema."""
    segments = []
    for seg in raw.get("segments", []):
        if not seg.get("text", "").strip():
            continue
        segments.append(TranscriptSegment(
            text=seg["text"].strip(),
            start=float(seg["start"]),
            end=float(seg["end"]),
            speaker=seg.get("speaker"),
            words=[WordTimestamp(**w) for w in seg.get("words", [])] if seg.get("words") else [],
            confidence=seg.get("confidence"),
            flags=seg.get("flags", []),
            timestamp_source=TimestampSource.PROVIDER,
        ))

    return CanonicalTranscript(
        full_text=raw["full_text"].strip(),
        segments=segments,
        language_detected=raw.get("language_detected", "ar"),
        provider=provider,
        model=model,
        processing_time=raw.get("processing_time", 0.0),
        segments_count=len(segments),
        metadata={k: v for k, v in raw.items() if k not in {
            "full_text", "segments", "language_detected", "processing_time", "segments_count", "provider"
        }},
    )


def normalize_provider_output(raw: dict, provider: str, model: Optional[str] = None) -> CanonicalTranscript:
    """Dispatch to provider-specific normalizer."""
    if provider == "gemini":
        return normalize_gemini_output(raw, provider, model or "gemini-1.5-flash")
    elif provider == "groq":
        return normalize_groq_output(raw, provider, model or "whisper-large-v3-turbo")
    else:
        raise ValueError(f"Unknown provider: {provider}")