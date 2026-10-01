# Sawa (سوى) 🎙️

**Sawa** is a comprehensive Arabic-focused communication platform designed for seamless video sharing and intelligent AI-powered transcription. It serves as a powerful alternative for asynchronous video messaging, optimized specifically for Arabic speakers with high-accuracy speech-to-text capabilities.

---

## 🌟 Key Features

-   **Arabic-First Transcription:** Powered by advanced AI models (Whisper/Groq) to provide precise Arabic speech-to-text conversion.
-   **Seamless Video Sharing:** Upload and share videos instantly with secure public and private links.
-   **Interactive Transcripts:** View, edit, and export transcripts in multiple formats (SRT, TXT, JSON).
-   **Full-Stack Solution:** A modern React frontend coupled with a robust FastAPI backend.
-   **Secure Authentication:** JWT-based user authentication and management.

---

## 🛠️ Tech Stack

### Frontend
-   **Framework:** React 18 (Vite)
-   **Styling:** Tailwind CSS
-   **State & Routing:** React Router DOM
-   **Icons:** Lucide React
-   **Internationalization:** i18next (Arabic/English support)
-   **Video Player:** HLS.js for optimized streaming

### Backend
-   **Framework:** FastAPI (Python 3.10+)
-   **Database:** PostgreSQL with SQLAlchemy ORM & Alembic migrations
-   **AI Transcription:** OpenAI Whisper / Groq / Google Generative AI
-   **File Storage:** Local storage / AWS S3 integration
-   **Security:** Passlib (Bcrypt) & Python-Jose (JWT)

---

## 🚀 Getting Started

### 1. Prerequisites
-   Python 3.10+
-   Node.js 18+
-   FFmpeg (for audio processing)

### 2. Backend Setup
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Configure your database and API keys
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup
```bash
cd front_end
npm install
npm run dev
```

---

## 📁 Project Structure

```text
sawa/
├── backend/               # FastAPI Application
│   ├── app/               # Core logic (Auth, DB, Transcription)
│   ├── alembic/           # Database migrations
│   ├── uploads/           # Local video storage
│   └── tests/             # Backend test suites
├── front_end/             # React Application
│   ├── src/               # UI Components, Pages, and Hooks
│   ├── public/            # Static assets
│   └── vite.config.js     # Build configuration
└── Dockerfile             # Containerization support
```

---

## 🧠 AI Features: Alignment & Diarization (Optional)

The platform supports optional advanced AI features that require additional dependencies:

### Word-Level Alignment (WhisperX)
Provides word-level timestamps for transcript review.
```bash
pip install -r backend/requirements-ml.txt
```
**Requirements:**
- CPU: ~2GB RAM, ~5GB disk space
- GPU (optional): CUDA 11.8+, ~8GB VRAM for faster alignment
- Set `ALIGNMENT_PROVIDER=whisperx` in `.env` to enable

### Speaker Diarization (pyannote.audio)
Identifies speakers in multi-speaker recordings.
```bash
pip install -r backend/requirements-diarization.txt
```
**Requirements:**
- **HuggingFace Account Required:** Create account at [huggingface.co](https://huggingface.co)
- **Model Access:** Accept terms for [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
- **HuggingFace Token:** Add `HUGGINGFACE_TOKEN=your_token` to `.env`
- CPU: ~4GB RAM, ~8GB disk space (model cache)
- GPU (recommended): CUDA 11.8+, ~8GB VRAM
- Set `DIARIZATION_ENABLED=true` in `.env` to enable

**Hardware Limitations:**
- CPU-only diarization is ~10-20x slower than GPU
- Audio longer than 30 minutes may exceed memory on CPU
- Concurrent diarization jobs not recommended on CPU-only instances

**Model Terms:** By using pyannote.audio, you agree to [pyannote's model license](https://huggingface.co/pyannote/speaker-diarization-3.1) which restricts commercial use.

---

## 🔌 API Overview

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - User login
- `GET /api/auth/me` - Get current user profile

### Video Management
- `POST /api/videos/upload` - Upload video and start transcription
- `GET /api/videos/my` - List user's videos
- `GET /api/videos/{id}` - Get specific video details
- `DELETE /api/videos/{id}` - Delete a video

### Transcription Services
- `GET /api/transcripts/{video_id}` - Fetch transcript
- `PATCH /api/transcripts/{video_id}` - Manually edit transcript
- `GET /api/transcripts/{video_id}/export` - Export to SRT/TXT/JSON

---

## 🎙️ AI Models (Whisper)
The platform supports multiple Whisper models depending on your needs:
- `base`: Fast and efficient for development.
- `large-v3`: Highly accurate, recommended for production Arabic transcription.

---

## 🌐 Cloudflare R2 — إعداد CORS (مطلوب للرفع المباشر presigned PUT)

الرفع المباشر من المتصفح إلى R2 (presigned PUT) يحتاج قاعدة CORS على الـ
bucket، وإلا سيرفض المتصفح الطلب. من لوحة تحكم Cloudflare R2 → اختر الـ
bucket → **Settings → CORS Policy** → الصق القاعدة التالية (عدّل
`AllowedOrigins` لو أضفت نطاقاً جديداً):

```json
[
  {
    "AllowedOrigins": [
      "https://sawa-plum.vercel.app",
      "http://localhost:5173"
    ],
    "AllowedMethods": ["PUT", "GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

---

## 📄 License
This project is licensed under the MIT License.
