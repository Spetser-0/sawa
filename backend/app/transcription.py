"""
خدمة التفريغ الصوتي بالذكاء الاصطناعي
Gemini (رئيسي) → Groq (بديل)
"""
import time
import json
import logging
import os
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════
#  Gemini (المزود الرئيسي — يدعم العربية بشكل ممتاز)
# ══════════════════════════════════════════════════════
def transcribe_with_gemini(file_path: str, language: str = "ar") -> dict:
    """
    يفرّغ الملف الصوتي باستخدام Gemini 1.5 Flash.
    يدعم العربية ومختلف اللغات واللهجات.
    """
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY غير موجود في .env")

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    logger.info(f"🎙️ [Gemini] بدء تفريغ: {file_path} (language={language})")

    # اقرأ الملف كبيانات خام
    file_ext = Path(file_path).suffix.lower()
    mime_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }
    mime_type = mime_map.get(file_ext, "audio/wav")

    with open(file_path, "rb") as f:
        audio_data = f.read()

    # حدد لغة البرومبت حسب اللغة المطلوبة
    base_lang = language.split("-")[0] if "-" in language else language
    if base_lang == "ar":
        prompt_lang = "العربية"
    elif base_lang == "en":
        prompt_lang = "English"
    elif base_lang == "es":
        prompt_lang = "Spanish"
    elif base_lang == "fr":
        prompt_lang = "French"
    elif base_lang == "de":
        prompt_lang = "German"
    elif base_lang == "ru":
        prompt_lang = "Russian"
    elif base_lang == "zh":
        prompt_lang = "Chinese"
    elif base_lang == "ja":
        prompt_lang = "Japanese"
    elif base_lang == "ko":
        prompt_lang = "Korean"
    elif base_lang == "pt":
        prompt_lang = "Portuguese"
    elif base_lang == "it":
        prompt_lang = "Italian"
    elif base_lang == "tr":
        prompt_lang = "Turkish"
    elif base_lang == "hi":
        prompt_lang = "Hindi"
    else:
        prompt_lang = "the audio's language"

    prompt = f"""You are an expert transcription assistant. Transcribe the attached audio file accurately.

Return the result EXACTLY as this JSON (no extra text outside the JSON):
{{
  "full_text": "The complete transcribed text",
  "segments": [
    {{"start": 0.0, "end": 2.5, "text": "First sentence"}},
    {{"start": 2.5, "end": 5.1, "text": "Second sentence"}}
  ],
  "language_detected": "detected language code"
}}

Instructions:
- The audio language is {prompt_lang}
- Preserve timestamps (start/end) in seconds accurately
- Split text into short segments (3-10 seconds each)
- Do not invent timestamps — use real timestamps from the audio
- Detect the language and dialect if different from expected"""

    start_time = time.time()

    try:
        response = model.generate_content([
            prompt,
            {"mime_data": {"data": audio_data, "mime_type": mime_type}},
        ])

        raw_text = response.text.strip()
        # نظّف الـ JSON
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

        result = json.loads(raw_text)
        processing_time = round(time.time() - start_time, 2)

        # تحقق من صحة البنية
        if "full_text" not in result:
            raise ValueError("استجابة Gemini لا تحتوي على full_text")
        if "segments" not in result:
            result["segments"] = []

        result["processing_time"] = processing_time
        result.setdefault("language_detected", language)
        result.setdefault("segments_count", len(result["segments"]))

        logger.info(f"✅ [Gemini] اكتمل التفريغ في {processing_time}s — {len(result['segments'])} مقطع")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"❌ [Gemini] فشل تحليل JSON: {e}")
        raise ValueError(f"فشل تحليل استجابة Gemini: {e}")
    except Exception as e:
        logger.error(f"❌ [Gemini] خطأ: {e}")
        raise


# ══════════════════════════════════════════════════════
#  Groq (المزود البديل — سريع جداً)
# ══════════════════════════════════════════════════════
def transcribe_with_groq(file_path: str, language: str = "ar") -> dict:
    """
    يفرّغ الملف باستخدام Groq Whisper API.
    سريع جداً ويدعم عشرات اللغات.
    """
    api_key = settings.GROQ_API_KEY
    if not api_key:
        raise ValueError("GROQ_API_KEY غير موجود في .env")

    from groq import Groq

    client = Groq(api_key=api_key)
    base_lang = language.split("-")[0] if "-" in language else language
    logger.info(f"🎙️ [Groq] بدء تفريغ: {file_path} (language={base_lang})")

    start_time = time.time()

    with open(file_path, "rb") as f:
        result = client.audio.transcriptions.create(
            file=(Path(file_path).name, f.read()),
            model="whisper-large-v3-turbo",
            language=base_lang,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    processing_time = round(time.time() - start_time, 2)

    segments = []
    full_parts = []
    for seg in result.segments:
        text = seg.text.strip()
        if text:
            segments.append({
                "start": round(seg.start, 2),
                "end":   round(seg.end, 2),
                "text":  text,
            })
            full_parts.append(text)

    output = {
        "full_text":         " ".join(full_parts),
        "segments":          segments,
        "language_detected": getattr(result, "language", language),
        "processing_time":   processing_time,
        "segments_count":    len(segments),
    }

    logger.info(f"✅ [Groq] اكتمل التفريغ في {processing_time}s — {len(segments)} مقطع")
    return output


# ══════════════════════════════════════════════════════
#  الدالة الرئيسية — سلسلة التخفيض (Fallback Chain)
# ══════════════════════════════════════════════════════
def transcribe_audio(
    file_path: str,
    language: str = "ar",
    dialect_hint: Optional[str] = None,
) -> dict:
    """
    تفرّغ ملف صوتي أو فيديو — يجرّب المزودات بالترتيب:
    1. Gemini (الرئيسي)
    2. Groq (بديل)
    """
    if not Path(file_path).exists():
        raise FileNotFoundError(f"الملف غير موجود: {file_path}")

    provider = settings.TRANSCRIPTION_PROVIDER.lower()
    providers = []

    if provider == "gemini":
        providers = [
            ("gemini", transcribe_with_gemini),
            ("groq", transcribe_with_groq),
        ]
    elif provider == "groq":
        providers = [
            ("groq", transcribe_with_groq),
            ("gemini", transcribe_with_gemini),
        ]
    else:
        providers = [
            ("gemini", transcribe_with_gemini),
            ("groq", transcribe_with_groq),
        ]

    errors = []
    for name, func in providers:
        try:
            logger.info(f"🔄 محاولة التفريغ عبر: {name}")
            result = func(file_path, language=language)
            result["provider"] = name
            return result
        except Exception as e:
            logger.warning(f"⚠️ فشل {name}: {e}")
            errors.append(f"{name}: {str(e)}")
            continue

    raise RuntimeError(
        f"فشلت جميع مزودات التفريغ:\n" + "\n".join(errors)
    )


# ══════════════════════════════════════════════════════
#  تقليل الضوضاء بـ ffmpeg afftdn
# ══════════════════════════════════════════════════════
def denoise_audio(input_path: str) -> str:
    """
    ينظف الصوت باستخدام فلتر afftdn في ffmpeg.
    يُنشئ ملفاً جديداً بجانب الأصلي ويعيد مساره.
    """
    import subprocess

    input_p = Path(input_path)
    denoised_path = input_p.with_name(f"{input_p.stem}_denoised{input_p.suffix}")

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", "afftdn=nf=-25,highpass=f=80,lowpass=f=12000",
        "-ar", "16000",
        str(denoised_path),
    ]

    logger.info(f"🔇 بدء تنظيف الصوت: {input_path}")
    result = subprocess.run(cmd, capture_output=True, timeout=600)

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")
        logger.error(f"❌ فشل تنظيف الصوت: {stderr[-500:]}")
        raise RuntimeError(f"ffmpeg denoise failed: {stderr[-200:]}")

    logger.info(f"✅ تم تنظيف الصوت: {denoised_path}")
    return str(denoised_path)


# ══════════════════════════════════════════════════════
#  استخراج الصوت من الفيديو
# ══════════════════════════════════════════════════════
def extract_audio_if_needed(video_path: str) -> str:
    path = Path(video_path)
    if path.suffix.lower() in [".mp3", ".wav", ".m4a", ".flac"]:
        return video_path
    return video_path
