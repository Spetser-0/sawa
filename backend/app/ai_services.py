"""
خدمات الذكاء الاصطناعي — ترجمة، تلخيص، تحديد المتحدثين
"""
import json
import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

# ── Gemini Client ────────────────────────────────────
def get_gemini():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY غير موجود في ملف .env")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.0-flash")


# ══════════════════════════════════════════════════════
#  الترجمة العربية → إنجليزية
# ══════════════════════════════════════════════════════
def translate_to_english(arabic_text: str, segments: list = None) -> dict:
    """
    يترجم النص العربي للإنجليزية مع الحفاظ على الطوابع الزمنية
    """
    model = get_gemini()

    if segments:
        # ترجمة الجمل مع الحفاظ على التوقيت
        segments_text = "\n".join([
            f"[{s['start']:.1f}s - {s['end']:.1f}s]: {s['text']}"
            for s in segments
        ])
        prompt = f"""ترجم هذه الجمل العربية للإنجليزية. أرجع فقط JSON بهذا الشكل بدون أي نص إضافي:
{{"segments": [{{"start": 0.0, "end": 2.0, "text": "English text here"}}, ...], "full_text": "Complete English translation"}}

الجمل:
{segments_text}"""
    else:
        prompt = f"""ترجم هذا النص العربي للإنجليزية. أرجع فقط JSON:
{{"full_text": "English translation here"}}

النص:
{arabic_text}"""

    response = model.generate_content(prompt)

    raw = response.text.strip()
    # نظّف الـ JSON إذا جاء بـ backticks
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # fallback إذا فشل الـ JSON
        return {"full_text": raw, "segments": []}


# ══════════════════════════════════════════════════════
#  التلخيص الذكي
# ══════════════════════════════════════════════════════
def summarize_transcript(full_text: str, language: str = "ar") -> dict:
    """
    يُلخّص النص المفرَّغ في نقاط رئيسية
    """
    model = get_gemini()

    lang_instruction = "باللغة العربية" if language == "ar" else "in English"

    prompt = f"""أنت مساعد ذكي. لديك نص مفرَّغ من تسجيل صوتي أو فيديو.
قم بتلخيصه {lang_instruction} بشكل منظم.

أرجع JSON بهذا الشكل بالضبط بدون أي نص إضافي:
{{
  "title": "عنوان مقترح للتسجيل",
  "summary": "ملخص في 2-3 جمل",
  "key_points": ["نقطة 1", "نقطة 2", "نقطة 3"],
  "action_items": ["مهمة 1", "مهمة 2"],
  "duration_estimate": "تقدير مدة التسجيل بالدقائق"
}}

النص:
{full_text[:8000]}"""  # حد 8000 حرف لتجنب تجاوز الـ context

    response = model.generate_content(prompt)

    raw = response.text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "title": "ملخص التسجيل",
            "summary": raw,
            "key_points": [],
            "action_items": [],
            "duration_estimate": "غير محدد"
        }


# ══════════════════════════════════════════════════════
#  تحديد المتحدثين (Speaker Diarization)
# ══════════════════════════════════════════════════════
def diarize_audio(file_path: str, num_speakers: int = None) -> list:
    """
    يحدد من يتكلم في كل لحظة
    يتطلب: pip install pyannote.audio
    ويتطلب: HUGGINGFACE_TOKEN في .env
    """
    hf_token = os.getenv("HUGGINGFACE_TOKEN")
    if not hf_token:
        raise ValueError(
            "HUGGINGFACE_TOKEN مطلوب لتحديد المتحدثين.\n"
            "1. سجّل في huggingface.co\n"
            "2. اقبل شروط نموذج pyannote/speaker-diarization-3.1\n"
            "3. أضف التوكن في .env"
        )

    try:
        from pyannote.audio import Pipeline
        import torch

        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )

        # استخدم GPU إذا متوفر
        if torch.cuda.is_available():
            pipeline = pipeline.to(torch.device("cuda"))

        kwargs = {}
        if num_speakers:
            kwargs["num_speakers"] = num_speakers

        diarization = pipeline(file_path, **kwargs)

        # حوّل النتائج لقائمة
        speakers = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speakers.append({
                "start":   round(turn.start, 2),
                "end":     round(turn.end,   2),
                "speaker": speaker,  # "SPEAKER_00", "SPEAKER_01"...
            })

        return speakers

    except ImportError:
        raise ImportError(
            "pyannote.audio غير مثبت.\n"
            "شغّل: pip install pyannote.audio"
        )


def merge_diarization_with_transcript(segments: list, speakers: list) -> list:
    """
    يدمج نتائج التفريغ مع تحديد المتحدثين
    كل جملة تحصل على اسم المتحدث
    """
    merged = []
    for seg in segments:
        seg_mid = (seg["start"] + seg["end"]) / 2

        # ابحث عن المتحدث في هذه اللحظة
        speaker = "متحدث غير معروف"
        for sp in speakers:
            if sp["start"] <= seg_mid <= sp["end"]:
                # حوّل "SPEAKER_00" → "المتحدث 1"
                num = int(sp["speaker"].split("_")[-1]) + 1
                speaker = f"المتحدث {num}"
                break

        merged.append({**seg, "speaker": speaker})

    return merged
