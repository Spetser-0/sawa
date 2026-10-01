# Sawa Transcription Baseline Document

Generated on: 2026-09-30
Repository: Spetser-0/sawa (main branch, commit HEAD)

---

## 1. Current Providers

### Primary: Gemini (Google Generative AI)
- **Model**: `gemini-1.5-flash`
- **API**: `google.generativeai`
- **Input**: Raw audio/video bytes + MIME type
- **Prompt**: Explicit JSON schema requesting `full_text`, `segments[]` with `start`/`end`/`text`, `language_detected`
- **Output handling**: Parses JSON from model response; cleans markdown code fences
- **Fallback**: Falls back to Groq on failure

### Fallback: Groq (Whisper API)
- **Model**: `whisper-large-v3-turbo`
- **API**: `groq` Python client
- **Input**: File upload with `response_format="verbose_json"`, `timestamp_granularities=["segment"]`
- **Output**: Native Whisper `verbose_json` with segment-level timestamps
- **Processing**: Converts to internal `{start, end, text}` format

### Configuration
- `TRANSCRIPTION_PROVIDER` env var: `"gemini"` | `"groq"` | `"local"` (default: `"gemini"`)
- Provider chain order depends on this setting
- No local Whisper implementation currently active (code references exist but not wired)

---

## 2. Current Transcript JSON Shape

### Database Storage (`transcripts.segments_json`)
```json
[
  {"start": 0.0, "end": 2.5, "text": "First sentence"},
  {"start": 2.5, "end": 5.1, "text": "Second sentence"}
]
```

### API Response (`GET /api/transcripts/{video_id}`)
```json
{
  "id": "transcript-uuid",
  "video_id": "video-uuid",
  "full_text": "Complete transcribed text",
  "segments": [
    {"start": 0.0, "end": 2.5, "text": "First sentence", "speaker": null, "words": null}
  ],
  "status": "done",
  "language_detected": "ar",
  "processing_time": 12.34,
  "error_message": null,
  "updated_at": "2026-09-30T10:00:00"
}
```

### SegmentSchema (Pydantic, `transcripts.py:20-25`)
```python
class SegmentSchema(BaseModel):
    start:   float
    end:     float
    text:    str
    speaker: Optional[str] = None
    words:   Optional[list] = None
```

### Notable Gaps
- No `confidence` field
- No `timestamp_source` field (provider/alignment/approximate/unknown)
- No `flags` array
- `speaker` only populated after explicit diarization call
- `words` always `null` (no word-level timestamps)
- Provider/model metadata not stored

---

## 3. Current Transcript Status Values

### Enum (`database.py:39-44`)
```python
class TranscriptStatus(str, enum.Enum):
    PENDING     = "pending"
    DENOISING   = "denoising"
    PROCESSING  = "processing"
    DONE        = "done"
    FAILED      = "failed"
```

### Worker State Transitions (`worker.py:51-88`)
1. `PENDING` → (task starts)
2. `DENOISING` (if `noise_reduction=True`) →
3. `PROCESSING` →
4. `DONE` (success) OR `FAILED` (error)

### Status in VideoResponse (`videos.py:129`)
- `transcript_status` mirrors `Transcript.status`

---

## 4. Current Diarization Behavior

### Endpoint: `POST /api/transcripts/{video_id}/diarize` (`transcripts.py:213-247`)
- **Synchronous HTTP request** — blocks until complete
- **No background job** — runs `pyannote.audio` directly in request handler
- **Requires**: `HUGGINGFACE_TOKEN`, `pyannote.audio`, `torch`
- **Model**: `pyannote/speaker-diarization-3.1`
- **GPU**: Uses CUDA if available

### Algorithm (`ai_services.py:158-177`): Midpoint Assignment
```python
seg_mid = (seg["start"] + seg["end"]) / 2
for sp in speakers:
    if sp["start"] <= seg_mid <= sp["end"]:
        speaker = f"المتحدث {int(sp['speaker'].split('_')[-1]) + 1}"
        break
else:
    speaker = "متحدث غير معروف"
```

### Issues
1. **Midpoint-only** — ignores segment duration and overlap coverage
2. **Synchronous** — times out on long files
3. **No idempotency** — duplicate requests create duplicate work
4. **No status tracking** — transcript stays `DONE` during diarization
5. **No retry/cleanup** — failures leave partial state

### Output
- Updates `transcript.segments_json` with `speaker` field per segment
- Returns `{"message", "speakers_found", "segments"}`

---

## 5. Current API Endpoints (Transcript-Related)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/transcripts/{video_id}` | Fetch transcript (with segments) |
| PATCH | `/api/transcripts/{video_id}` | Edit transcript (full_text + segments) |
| POST | `/api/transcripts/{video_id}/retry` | Re-queue transcription |
| POST | `/api/transcripts/{video_id}/translate` | Translate to English (Gemini) |
| POST | `/api/transcripts/{video_id}/summarize` | AI summary (Gemini) |
| POST | `/api/transcripts/{video_id}/diarize` | Speaker diarization (sync, pyannote) |
| POST | `/api/transcripts/{video_id}/chapters` | Generate chapters (Claude) |
| GET | `/api/transcripts/{video_id}/chapters` | Fetch saved chapters |
| GET | `/api/transcripts/{video_id}/export` | Export (txt/srt/json/docx) |

---

## 6. Current Tests and Their Status

### Backend Tests (`backend/tests/`)
- **47 tests total** — **ALL PASSING** (41.32s)
- `test_auth_flow.py` — 25 tests (register, login, logout, refresh, password reset, settings)
- `test_presigned_upload.py` — 6 tests (R2 presigned PUT, validation)
- `test_complete_upload.py` — 6 tests (size guard, magic bytes, Celery dispatch)
- `test_webhook.py` — 7 tests (Cryptomus signature verification)
- `conftest.py` — SQLite in-memory, TestClient, auto-create/drop tables

### Frontend Build
- `npm run build` — **SUCCESS** (31.20s)
- Chunk size warnings (hls.js 524kB, charts 378kB) — non-blocking

### Missing Test Coverage
- No tests for `transcription.py` provider logic
- No tests for `ai_services.py` (translation, summarization, diarization)
- No tests for `worker.py` Celery tasks
- No transcript schema validation tests
- No diarization algorithm tests

---

## 7. Current Deployment Limitations

### Infrastructure (`render.yaml`)
- **Web service**: Python, `starter` plan (2GB RAM) — runs FastAPI + Alembic migration on startup
- **Celery Worker**: Separate service, same `starter` plan
- **Celery Beat**: Separate service for periodic tasks
- **Database**: External (Supabase PostgreSQL, via `DATABASE_URL`)
- **Redis**: External (via `REDIS_URL`) — required for Celery broker/result backend
- **Storage**: Local disk (`/tmp/uploads`, 5GB persistent disk) OR Cloudflare R2
- **Secrets**: All API keys via Render env vars (not in repo)

### Dependency Concerns
- **Heavy ML deps NOT in requirements.txt**: `pyannote.audio`, `torch`, `whisperx`
- Diarization currently requires manual `pip install pyannote.audio` + Hugging Face token
- No separate worker image for ML workloads — worker shares web image
- `WHISPER_MODEL=base` configured but local Whisper path not wired

### Known Runtime Warnings (from test run)
- Pydantic v2 deprecation: class-based `Config` → `ConfigDict` (multiple files)
- SQLAlchemy 2.0: `declarative_base()` import path
- `send_otp_email` coroutine never awaited in auth tests (fire-and-forget)

---

## 8. Key Files Inspected

| File | Purpose |
|------|---------|
| `backend/app/config.py` | Central settings (Pydantic Settings) |
| `backend/app/database.py` | SQLAlchemy models, enums, session |
| `backend/app/transcription.py` | Provider adapters (Gemini, Groq), fallback chain, denoise |
| `backend/app/ai_services.py` | Translation, summarization, diarization, merge |
| `backend/app/worker.py` | Celery tasks (transcribe, HLS, thumbnail, cleanup) |
| `backend/app/routers/transcripts.py` | Transcript API endpoints |
| `backend/app/routers/videos.py` | Upload, presigned, complete, streaming, HLS |
| `backend/app/storage.py` | Abstract storage (Local + R2) |
| `backend/requirements.txt` | Python dependencies |
| `backend/render.yaml` | Render.com deployment config |
| `front_end/src/components/VideoPlayer.jsx` | Main player + transcript UI + polling |
| `front_end/src/components/AIFeatures.jsx` | AI feature tabs (translate, summarize, diarize) |
| `front_end/src/api/client.js` | API client with CSRF, Bearer, retry |

---

## 9. Verification Results Summary

| Check | Result |
|-------|--------|
| `git status` | Clean, on `main`, up to date with `origin/main` |
| Backend tests (`pytest`) | **47 passed**, 10 warnings (deprecations only) |
| Frontend build (`npm run build`) | **Success**, chunk size warnings only |
| No production code changes made | ✅ Verified |

---

## 10. Known Limitations & Blockers for Future Phases

1. **Gemini timestamps unverified** — Model prompted for timestamps but no verification; may hallucinate boundaries
2. **No canonical schema** — Provider outputs differ; no validation/normalization layer
3. **Diarization is synchronous** — Will timeout on Render (30s limit) for files > few minutes
4. **No word-level alignment** — `words` field always null
5. **No pipeline observability** — Only 5 status values; no progress, stage, retry count
6. **Heavy ML deps missing** — `pyannote.audio` + `torch` not in requirements; GPU not available on Render starter
7. **No Arabic dialect handling** — `dialect` field exists on Video but not passed to providers
8. **Frontend polling naive** — 4s fixed interval, no cleanup on unmount for diarization
9. **No VTT export** — Only txt/srt/json/docx
10. **No benchmark suite** — Cannot measure regression on model/pipeline changes

---

## 11. Recommended Commit Message

```text
chore: document transcription baseline and verification status
```