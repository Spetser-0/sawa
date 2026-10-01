# Arabic Transcription Benchmark & Regression Suite

## Overview

This document describes the benchmarking framework for evaluating Arabic transcription quality across model/provider changes. The suite provides objective quality gates without requiring production data or secrets.

---

## Benchmark Categories

| Category | Description | Expected Difficulty |
|----------|-------------|---------------------|
| **Clean MSA** | Modern Standard Arabic, studio quality, single speaker | Low |
| **Egyptian Dialect** | Egyptian Arabic, conversational | Medium |
| **Gulf Dialect** | Gulf Arabic (KSA/UAE/Qatar), conversational | Medium |
| **Levantine Dialect** | Levantine Arabic (Syria/Lebanon/Jordan/Palestine) | Medium |
| **Maghrebi Dialect** | North African Arabic (Morocco/Algeria/Tunisia) | High |
| **Noisy Phone Audio** | Phone call quality with background noise | High |
| **Single Speaker** | One speaker, clear audio | Low |
| **Multiple Speakers** | 2-4 speakers, clear turn-taking | Medium |
| **Rapid Turn-taking** | Fast speaker switches (< 1s) | High |
| **Overlapping Speech** | Simultaneous speakers | Very High |
| **Arabic-English Code Switching** | Mixed language content | Medium |

---

## Metrics

### Transcription Quality
- **WER (Word Error Rate)**: Standard word-level accuracy metric
- **CER (Character Error Rate)**: Character-level accuracy (important for Arabic)
- **Segment Timestamp Error**: Mean absolute error of segment boundaries (seconds)

### Word-Level Timing
- **Word Timestamp Coverage**: % of words with timestamps
- **Word Timestamp Error**: Mean absolute error of word boundaries (seconds)

### Speaker Attribution
- **Speaker Attribution Accuracy**: % of segments assigned correct speaker
- **Diarization Error Rate (DER)**: Standard diarization metric
- **Ambiguous Segment Rate**: % of segments with low speaker coverage

### Performance
- **Processing Time**: End-to-end transcription time (seconds)
- **RTF (Real-Time Factor)**: Processing time / audio duration
- **Memory Usage**: Peak RAM during processing (MB)
- **Failure Rate**: % of jobs that fail
- **Retry Rate**: % of jobs requiring retries

---

## Fixtures

### Audio Fixtures Location
```
backend/tests/fixtures/audio/
├── clean_msa_01.wav           # 30s, single speaker, studio MSA
├── egyptian_01.wav            # 30s, single speaker, Egyptian
├── gulf_01.wav                # 30s, single speaker, Gulf
├── levantine_01.wav           # 30s, single speaker, Levantine
├── maghrebi_01.wav            # 30s, single speaker, Maghrebi
├── noisy_phone_01.wav         # 30s, phone quality with noise
├── multi_speaker_01.wav       # 60s, 3 speakers, clear turns
├── rapid_turns_01.wav         # 60s, 2 speakers, rapid switching
├── overlapping_01.wav         # 60s, 2 speakers, overlaps
└── code_switch_01.wav         # 60s, Arabic-English mixing
```

### Reference Transcripts
```
backend/tests/fixtures/reference/
├── clean_msa_01.json          # Canonical transcript with word timestamps
├── egyptian_01.json
├── gulf_01.json
├── levantine_01.json
├── maghrebi_01.json
├── noisy_phone_01.json
├── multi_speaker_01.json
├── rapid_turns_01.json
├── overlapping_01.json
└── code_switch_01.json
```

### Reference Format
```json
{
  "audio_file": "clean_msa_01.wav",
  "duration": 30.5,
  "language": "ar",
  "dialect": "msa",
  "speakers": 1,
  "segments": [
    {
      "start": 0.0,
      "end": 3.2,
      "text": "مرحبا بكم في منصة سوى",
      "speaker": "المتحدث 1",
      "words": [
        {"word": "مرحبا", "start": 0.0, "end": 0.8, "confidence": 0.98},
        {"word": "بكم", "start": 0.8, "end": 1.2, "confidence": 0.95},
        {"word": "في", "start": 1.2, "end": 1.4, "confidence": 0.99},
        {"word": "منصة", "start": 1.4, "end": 2.1, "confidence": 0.97},
        {"word": "سوى", "start": 2.1, "end": 3.2, "confidence": 0.96}
      ]
    }
  ],
  "metadata": {
    "source": "synthetic",
    "quality": "clean",
    "speaker_count": 1
  }
}
```

---

## Benchmark Scripts

### Main Benchmark Runner
```bash
# Run full benchmark suite
cd backend
python -m tests.benchmarks.run_benchmark --provider=gemini --model=gemini-1.5-flash

# Run specific category
python -m tests.benchmarks.run_benchmark --category=clean_msa --provider=groq

# Compare two providers
python -m tests.benchmarks.compare --provider-a=gemini --provider-b=groq

# Generate regression report
python -m tests.benchmarks.report --baseline=baseline.json --current=current.json
```

### Output Format
```json
{
  "benchmark_run": {
    "timestamp": "2026-10-01T12:00:00Z",
    "provider": "gemini",
    "model": "gemini-1.5-flash",
    "total_audio_duration": 480.5,
    "categories_tested": 10
  },
  "results": {
    "clean_msa": {
      "wer": 0.042,
      "cer": 0.018,
      "segment_timestamp_mae": 0.23,
      "word_timestamp_coverage": 0.98,
      "word_timestamp_mae": 0.15,
      "speaker_accuracy": 1.0,
      "processing_time": 12.3,
      "rtf": 0.41
    },
    "egyptian": { ... },
    ...
  },
  "summary": {
    "avg_wer": 0.067,
    "avg_cer": 0.028,
    "avg_segment_mae": 0.31,
    "avg_word_coverage": 0.95,
    "avg_speaker_accuracy": 0.92,
    "total_processing_time": 156.7,
    "failures": 0,
    "retries": 2
  }
}
```

---

## Regression Detection

### Thresholds (Alert if Exceeded)
| Metric | Warning Threshold | Critical Threshold |
|--------|-------------------|-------------------|
| WER increase | > 10% relative | > 25% relative |
| CER increase | > 10% relative | > 25% relative |
| Segment MAE increase | > 0.5s | > 1.0s |
| Word coverage decrease | > 5% | > 15% |
| Speaker accuracy decrease | > 5% | > 15% |
| RTF increase | > 20% | > 50% |
| Failure rate | > 1% | > 5% |

### Baseline Management
```bash
# Save current results as baseline
python -m tests.benchmarks.save_baseline --name=baseline_v1

# List baselines
python -m tests.benchmarks.list_baselines

# Compare against baseline
python -m tests.benchmarks.compare --baseline=baseline_v1
```

---

## CI Integration

### GitHub Actions Example
```yaml
name: Transcription Benchmark

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
          pip install -r backend/requirements-benchmark.txt
      - name: Download fixtures
        run: python -m tests.benchmarks.download_fixtures
      - name: Run benchmark
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
        run: python -m tests.benchmarks.run_benchmark --provider=gemini
      - name: Regression check
        run: python -m tests.benchmarks.check_regression --baseline=baseline_v1
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: backend/tests/benchmarks/results/
```

---

## Requirements

### Dependencies
```text
# requirements-benchmark.txt
jiwer==3.0.3          # WER/CER calculation
pydub==0.25.1         # Audio processing
numpy==1.26.0         # Numerical operations
pandas==2.1.0         # Results tabulation
matplotlib==3.8.0     # Visualization (optional)
pytest-benchmark==4.0.0  # Benchmark framework
```

### System Requirements
- FFmpeg (for audio format conversion)
- Python 3.10+
- 4GB+ RAM for benchmark runs

---

## Security Notes

- **No real user audio** in fixtures - all synthetic or CC0-licensed
- **No API keys** in fixtures or scripts - loaded from environment
- **No PII** in reference transcripts
- Benchmark runs should use test API keys with rate limits

---

## Extending the Suite

To add a new benchmark category:
1. Add audio file to `tests/fixtures/audio/`
2. Add reference transcript to `tests/fixtures/reference/`
3. Register category in `tests/benchmarks/categories.py`
4. Add expected thresholds in `tests/benchmarks/thresholds.py`
5. Update this documentation