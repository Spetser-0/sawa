"""
Main benchmark runner for Arabic transcription evaluation.
"""
import argparse
import json
import time
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
import subprocess

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import settings
from app.transcription import transcribe_audio
from app.transcript_schema import CanonicalTranscript
from tests.benchmarks.categories import CATEGORIES, get_fixture_paths


@dataclass
class BenchmarkResult:
    category: str
    audio_duration: float
    processing_time: float
    rtf: float  # Real-time factor
    wer: float
    cer: float
    segment_timestamp_mae: float
    word_timestamp_coverage: float
    word_timestamp_mae: float
    speaker_accuracy: float
    success: bool
    error: Optional[str] = None


@dataclass
class BenchmarkSummary:
    benchmark_run: Dict[str, Any]
    results: Dict[str, Any]
    summary: Dict[str, Any]


def compute_wer(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate using jiwer if available, else simple diff."""
    try:
        import jiwer
        return jiwer.wer(reference, hypothesis)
    except ImportError:
        # Fallback: simple word-level diff
        ref_words = reference.split()
        hyp_words = hypothesis.split()
        if not ref_words:
            return 1.0 if hyp_words else 0.0
        
        # Levenshtein distance
        m, n = len(ref_words), len(hyp_words)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if ref_words[i - 1] == hyp_words[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return dp[m][n] / m


def compute_cer(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate."""
    try:
        import jiwer
        return jiwer.cer(reference, hypothesis)
    except ImportError:
        ref_chars = list(reference.replace(" ", ""))
        hyp_chars = list(hypothesis.replace(" ", ""))
        if not ref_chars:
            return 1.0 if hyp_chars else 0.0
        
        m, n = len(ref_chars), len(hyp_chars)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if ref_chars[i - 1] == hyp_chars[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return dp[m][n] / m


def load_reference(reference_path: Path) -> Dict[str, Any]:
    """Load reference transcript from JSON file."""
    with open(reference_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_text_from_segments(segments: List[Dict]) -> str:
    """Extract full text from segments."""
    return " ".join(seg.get("text", "").strip() for seg in segments if seg.get("text", "").strip())


def extract_speakers_from_segments(segments: List[Dict]) -> List[str]:
    """Extract unique speakers from segments."""
    speakers = []
    for seg in segments:
        spk = seg.get("speaker")
        if spk and spk not in speakers:
            speakers.append(spk)
    return speakers


def compute_segment_timestamp_error(ref_segments: List[Dict], hyp_segments: List[Dict]) -> float:
    """Compute mean absolute error of segment boundaries."""
    if not ref_segments or not hyp_segments:
        return 10.0  # Large error
    
    # Match segments by text similarity (simple approach)
    errors = []
    for ref in ref_segments:
        ref_start, ref_end = ref.get("start", 0), ref.get("end", 0)
        ref_text = ref.get("text", "").strip()
        
        best_match = None
        best_overlap = 0
        for hyp in hyp_segments:
            hyp_text = hyp.get("text", "").strip()
            # Simple text overlap
            ref_words = set(ref_text.split())
            hyp_words = set(hyp_text.split())
            if ref_words and hyp_words:
                overlap = len(ref_words & hyp_words) / len(ref_words | hyp_words)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = hyp
        
        if best_match:
            errors.append(abs(ref_start - best_match.get("start", 0)))
            errors.append(abs(ref_end - best_match.get("end", 0)))
    
    return sum(errors) / len(errors) if errors else 10.0


def compute_word_timestamp_coverage(hyp_segments: List[Dict]) -> float:
    """Compute percentage of words with timestamps."""
    total_words = 0
    words_with_timestamps = 0
    for seg in hyp_segments:
        words = seg.get("words", [])
        total_words += len(words) if words else len(seg.get("text", "").split())
        if words:
            words_with_timestamps += sum(1 for w in words if w.get("start") is not None and w.get("end") is not None)
    return words_with_timestamps / total_words if total_words > 0 else 0.0


def compute_word_timestamp_mae(ref_segments: List[Dict], hyp_segments: List[Dict]) -> float:
    """Compute mean absolute error of word timestamps."""
    errors = []
    for ref_seg in ref_segments:
        ref_words = ref_seg.get("words", [])
        if not ref_words:
            continue
        ref_text = ref_seg.get("text", "").strip()
        
        for hyp_seg in hyp_segments:
            hyp_text = hyp_seg.get("text", "").strip()
            if ref_text == hyp_text:
                hyp_words = hyp_seg.get("words", [])
                for ref_w, hyp_w in zip(ref_words, hyp_words):
                    if ref_w.get("start") is not None and hyp_w.get("start") is not None:
                        errors.append(abs(ref_w["start"] - hyp_w["start"]))
                        errors.append(abs(ref_w["end"] - hyp_w["end"]))
                break
    return sum(errors) / len(errors) if errors else 0.0


def compute_speaker_accuracy(ref_segments: List[Dict], hyp_segments: List[Dict]) -> float:
    """Compute speaker attribution accuracy."""
    if not ref_segments or not hyp_segments:
        return 0.0
    
    # Build mapping from text to speaker for reference
    ref_speakers = {seg.get("text", "").strip(): seg.get("speaker") for seg in ref_segments if seg.get("text", "").strip()}
    
    correct = 0
    total = 0
    for hyp in hyp_segments:
        hyp_text = hyp.get("text", "").strip()
        hyp_speaker = hyp.get("speaker")
        if hyp_text in ref_speakers:
            total += 1
            if ref_speakers[hyp_text] == hyp_speaker:
                correct += 1
    return correct / total if total > 0 else 0.0


def run_benchmark_category(
    category_name: str,
    provider: str = "gemini",
    language: str = "ar",
    run_alignment: bool = False,
) -> BenchmarkResult:
    """Run benchmark for a single category."""
    category = CATEGORIES[category_name]
    paths = get_fixture_paths()
    paths_cat = paths[category_name]
    
    audio_path = paths_cat["audio"]
    reference_path = paths_cat["reference"]
    
    if not audio_path.exists():
        return BenchmarkResult(
            category=category_name,
            audio_duration=category.duration,
            processing_time=0,
            rtf=0,
            wer=1.0,
            cer=1.0,
            segment_timestamp_mae=10.0,
            word_timestamp_coverage=0.0,
            word_timestamp_mae=10.0,
            speaker_accuracy=0.0,
            success=False,
            error=f"Audio file not found: {audio_path}",
        )
    
    if not reference_path.exists():
        return BenchmarkResult(
            category=category_name,
            audio_duration=category.duration,
            processing_time=0,
            rtf=0,
            wer=1.0,
            cer=1.0,
            segment_timestamp_mae=10.0,
            word_timestamp_coverage=0.0,
            word_timestamp_mae=10.0,
            speaker_accuracy=0.0,
            success=False,
            error=f"Reference file not found: {reference_path}",
        )
    
    # Load reference
    reference = load_reference(reference_path)
    ref_segments = reference.get("segments", [])
    ref_full_text = extract_text_from_segments(ref_segments)
    ref_speakers = extract_speakers_from_segments(ref_segments)
    
    # Run transcription
    start_time = time.time()
    try:
        result = transcribe_audio(
            str(audio_path),
            language=language,
            run_alignment=run_alignment,
        )
        processing_time = time.time() - start_time
    except Exception as e:
        return BenchmarkResult(
            category=category_name,
            audio_duration=category.duration,
            processing_time=time.time() - start_time,
            rtf=(time.time() - start_time) / category.duration,
            wer=1.0,
            cer=1.0,
            segment_timestamp_mae=10.0,
            word_timestamp_coverage=0.0,
            word_timestamp_mae=10.0,
            speaker_accuracy=0.0,
            success=False,
            error=str(e),
        )
    
    rtf = processing_time / category.duration
    
    # Extract hypothesis
    hyp_segments = result.get("segments", [])
    hyp_full_text = extract_text_from_segments(hyp_segments)
    hyp_speakers = extract_speakers_from_segments(hyp_segments)
    
    # Compute metrics
    wer = compute_wer(ref_full_text, hyp_full_text)
    cer = compute_cer(ref_full_text, hyp_full_text)
    segment_mae = compute_segment_timestamp_error(ref_segments, hyp_segments)
    word_coverage = compute_word_timestamp_coverage(hyp_segments)
    word_mae = compute_word_timestamp_mae(ref_segments, hyp_segments)
    speaker_acc = compute_speaker_accuracy(ref_segments, hyp_segments)
    
    return BenchmarkResult(
        category=category_name,
        audio_duration=category.duration,
        processing_time=processing_time,
        rtf=rtf,
        wer=wer,
        cer=cer,
        segment_timestamp_mae=segment_mae,
        word_timestamp_coverage=word_coverage,
        word_timestamp_mae=word_mae,
        speaker_accuracy=speaker_acc,
        success=True,
    )


def run_full_benchmark(
    provider: str = "gemini",
    categories: Optional[List[str]] = None,
    language: str = "ar",
    run_alignment: bool = False,
    output_dir: Optional[Path] = None,
) -> BenchmarkSummary:
    """Run full benchmark suite."""
    if categories is None:
        categories = list(CATEGORIES.keys())
    
    results = {}
    total_processing_time = 0.0
    failures = 0
    
    for cat_name in categories:
        if cat_name not in CATEGORIES:
            print(f"Unknown category: {cat_name}")
            continue
        
        print(f"Running benchmark: {cat_name} ({CATEGORIES[cat_name].name})...")
        result = run_benchmark_category(cat_name, provider, language, run_alignment)
        results[cat_name] = asdict(result)
        
        if result.success:
            total_processing_time += result.processing_time
            print(f"  WER: {result.wer:.3f}, CER: {result.cer:.3f}, RTF: {result.rtf:.2f}")
        else:
            failures += 1
            print(f"  FAILED: {result.error}")
    
    # Compute summary
    successful = [r for r in results.values() if r.get("success")]
    if successful:
        avg_wer = sum(r["wer"] for r in successful) / len(successful)
        avg_cer = sum(r["cer"] for r in successful) / len(successful)
        avg_segment_mae = sum(r["segment_timestamp_mae"] for r in successful) / len(successful)
        avg_word_coverage = sum(r["word_timestamp_coverage"] for r in successful) / len(successful)
        avg_speaker_acc = sum(r["speaker_accuracy"] for r in successful) / len(successful)
    else:
        avg_wer = avg_cer = avg_segment_mae = avg_word_coverage = avg_speaker_acc = 0.0
    
    benchmark_run = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": provider,
        "model": settings.TRANSCRIPTION_PROVIDER if provider == "gemini" else "whisper-large-v3-turbo",
        "total_audio_duration": sum(CATEGORIES[c].duration for c in categories if c in CATEGORIES),
        "categories_tested": len(categories),
    }
    
    summary = {
        "avg_wer": avg_wer,
        "avg_cer": avg_cer,
        "avg_segment_mae": avg_segment_mae,
        "avg_word_coverage": avg_word_coverage,
        "avg_speaker_accuracy": avg_speaker_acc,
        "total_processing_time": total_processing_time,
        "failures": failures,
        "retries": 0,  # Not tracked in this simple runner
    }
    
    return BenchmarkSummary(
        benchmark_run=benchmark_run,
        results=results,
        summary=summary,
    )


def save_results(summary: BenchmarkSummary, output_dir: Path):
    """Save benchmark results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"benchmark_{summary.benchmark_run['provider']}_{timestamp}.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(asdict(summary), f, ensure_ascii=False, indent=2)
    
    print(f"\nResults saved to: {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(description="Arabic Transcription Benchmark Runner")
    parser.add_argument("--provider", choices=["gemini", "groq"], default="gemini")
    parser.add_argument("--categories", nargs="+", help="Categories to test (default: all)")
    parser.add_argument("--language", default="ar")
    parser.add_argument("--alignment", action="store_true", help="Enable word-level alignment")
    parser.add_argument("--output-dir", default="tests/benchmarks/results")
    parser.add_argument("--baseline", help="Baseline file for comparison")
    
    args = parser.parse_args()
    
    categories = args.categories if args.categories else list(CATEGORIES.keys())
    output_dir = Path(args.output_dir)
    
    print(f"Starting benchmark: provider={args.provider}, categories={categories}")
    print(f"Alignment: {args.alignment}")
    print("-" * 60)
    
    summary = run_full_benchmark(
        provider=args.provider,
        categories=categories,
        language=args.language,
        run_alignment=args.alignment,
        output_dir=output_dir,
    )
    
    output_file = save_results(summary, output_dir)
    
    # Print summary
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Provider: {summary.benchmark_run['provider']}")
    print(f"Categories: {summary.benchmark_run['categories_tested']}")
    print(f"Total Audio: {summary.benchmark_run['total_audio_duration']:.1f}s")
    print(f"Failures: {summary.summary['failures']}")
    print(f"Avg WER: {summary.summary['avg_wer']:.3f}")
    print(f"Avg CER: {summary.summary['avg_cer']:.3f}")
    print(f"Avg Segment MAE: {summary.summary['avg_segment_mae']:.3f}s")
    print(f"Avg Word Coverage: {summary.summary['avg_word_coverage']:.1%}")
    print(f"Avg Speaker Acc: {summary.summary['avg_speaker_accuracy']:.1%}")
    print(f"Total Time: {summary.summary['total_processing_time']:.1f}s")
    
    # Regression check if baseline provided
    if args.baseline and Path(args.baseline).exists():
        with open(args.baseline, "r") as f:
            baseline = json.load(f)
        
        print("\n" + "=" * 60)
        print("REGRESSION CHECK")
        print("=" * 60)
        
        for cat_name, current in summary.results.items():
            if cat_name in baseline.get("results", {}) and current.get("success"):
                base = baseline["results"][cat_name]
                if base.get("success"):
                    wer_diff = current["wer"] - base["wer"]
                    wer_pct = (wer_diff / base["wer"] * 100) if base["wer"] > 0 else 0
                    if wer_pct > 25:
                        print(f"  ⚠️ CRITICAL: {cat_name} WER increased {wer_pct:.1f}% ({base['wer']:.3f} -> {current['wer']:.3f})")
                    elif wer_pct > 10:
                        print(f"  ⚠️ WARNING: {cat_name} WER increased {wer_pct:.1f}% ({base['wer']:.3f} -> {current['wer']:.3f})")
                    else:
                        print(f"  ✅ {cat_name} WER: {current['wer']:.3f} (Δ{wer_pct:+.1f}%)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())