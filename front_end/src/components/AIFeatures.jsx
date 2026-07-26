import { useState } from "react";
import { useTranslation } from "react-i18next";
import { aiAPI } from "../api/client";
import { Globe, Sparkles, Users, AlertCircle } from "lucide-react";

export default function AIFeatures({ videoId, transcriptDone }) {
  const { t } = useTranslation();
  const [tab,         setTab]         = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState("");
  const [translation, setTranslation] = useState(null);
  const [summary,     setSummary]     = useState(null);
  const [diarResult,  setDiarResult]  = useState(null);
  const [numSpeakers, setNumSpeakers] = useState("");
  const [copied,      setCopied]      = useState(false);

  if (!transcriptDone) return null;

  const run = async (action) => {
    setLoading(true);
    setError("");
    setTab(action);
    try {
      if (action === "translate") {
        const r = await aiAPI.translate(videoId);
        setTranslation(r);
      } else if (action === "summarize") {
        const r = await aiAPI.summarize(videoId);
        setSummary(r);
      } else if (action === "diarize") {
        const r = await aiAPI.diarize(videoId, numSpeakers ? parseInt(numSpeakers) : null);
        setDiarResult(r);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const copyText = (text) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ marginTop: 16 }}>

      {/* ── أزرار الميزات ─────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 14 }}>

        {/* الترجمة */}
        <button
          onClick={() => tab === "translate" ? setTab(null) : run("translate")}
          disabled={loading}
          style={{
            padding: "10px 8px", borderRadius: 10, border: `1px solid ${tab === "translate" ? "#60A5FA66" : "#1e1e30"}`,
            background: tab === "translate" ? "#60A5FA15" : "#0c0c18",
            color: tab === "translate" ? "#60A5FA" : "#888",
            cursor: "pointer", fontSize: 12, fontFamily: "inherit",
            display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
          }}
        >
          <Globe size={20} />
          <span style={{ fontWeight: 600 }}>{t("ai_features.translate")}</span>
          <span style={{ fontSize: 10, opacity: 0.7 }}>{t("ai_features.translate_desc")}</span>
        </button>

        {/* التلخيص */}
        <button
          onClick={() => tab === "summarize" ? setTab(null) : run("summarize")}
          disabled={loading}
          style={{
            padding: "10px 8px", borderRadius: 10, border: `1px solid ${tab === "summarize" ? "#34D39966" : "#1e1e30"}`,
            background: tab === "summarize" ? "#34D39915" : "#0c0c18",
            color: tab === "summarize" ? "#34D399" : "#888",
            cursor: "pointer", fontSize: 12, fontFamily: "inherit",
            display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
          }}
        >
          <Sparkles size={20} />
          <span style={{ fontWeight: 600 }}>{t("ai_features.summarize")}</span>
          <span style={{ fontSize: 10, opacity: 0.7 }}>{t("ai_features.summarize_desc")}</span>
        </button>

        {/* تحديد المتحدثين */}
        <button
          onClick={() => tab === "diarize" ? setTab(null) : setTab("diarize")}
          disabled={loading}
          style={{
            padding: "10px 8px", borderRadius: 10, border: `1px solid ${tab === "diarize" ? "#C084FC66" : "#1e1e30"}`,
            background: tab === "diarize" ? "#C084FC15" : "#0c0c18",
            color: tab === "diarize" ? "#C084FC" : "#888",
            cursor: "pointer", fontSize: 12, fontFamily: "inherit",
            display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
          }}
        >
          <Users size={20} />
          <span style={{ fontWeight: 600 }}>{t("ai_features.speakers")}</span>
          <span style={{ fontSize: 10, opacity: 0.7 }}>{t("ai_features.speakers_desc")}</span>
        </button>
      </div>

      {/* ── حالة التحميل ──────────────────────────── */}
      {loading && (
        <div style={{ textAlign: "center", padding: "20px", background: "#0c0c18", borderRadius: 12, border: "1px solid #1e1e30" }}>
          <div className="spin" style={{ width: 28, height: 28, border: "3px solid #1e1e30", borderTopColor: "#34D399", borderRadius: "50%", margin: "0 auto 10px" }} />
          <div style={{ fontSize: 13, color: "#888" }}>
            {tab === "translate" && t("ai_features.translating")}
            {tab === "summarize" && t("ai_features.summarizing")}
            {tab === "diarize"  && t("ai_features.diarizing")}
          </div>
        </div>
      )}

      {/* ── خطأ ───────────────────────────────────── */}
      {error && (
        <div style={{ padding: "12px 14px", background: "#F8717115", border: "1px solid #F8717133", borderRadius: 10, fontSize: 12, color: "#F87171", whiteSpace: "pre-wrap", display: "flex", alignItems: "center", gap: 8 }}>
          <AlertCircle size={14} style={{ flexShrink: 0 }} /> {error}
        </div>
      )}

      {/* ── نتيجة الترجمة ─────────────────────────── */}
      {!loading && translation && tab === "translate" && (
        <div style={{ background: "#060610", border: "1px solid #60A5FA33", borderRadius: 12, padding: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
            <span style={{ fontSize: 12, color: "#60A5FA", fontWeight: 700 }}>{t("ai_features.english_translation")}</span>
            <button onClick={() => copyText(translation.full_text_en)}
              style={{ background: "none", border: "1px solid #60A5FA33", color: "#60A5FA", borderRadius: 6, padding: "2px 10px", fontSize: 11, cursor: "pointer", fontFamily: "inherit" }}>
              {copied ? t("ai_features.copied") : t("ai_features.copy")}
            </button>
          </div>
          <div style={{ fontSize: 13, color: "#ddd", lineHeight: 1.8, direction: "ltr", textAlign: "left" }}>
            {translation.full_text_en}
          </div>
        </div>
      )}

      {/* ── نتيجة التلخيص ─────────────────────────── */}
      {!loading && summary && tab === "summarize" && (
        <div style={{ background: "#060610", border: "1px solid #34D39933", borderRadius: 12, padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontSize: 12, color: "#34D399", fontWeight: 700 }}>{t("ai_features.smart_summary")}</div>

          {summary.title && (
            <div>
              <div style={{ fontSize: 10, color: "#555", marginBottom: 4 }}>{t("ai_features.suggested_title")}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>{summary.title}</div>
            </div>
          )}

          {summary.summary && (
            <div>
              <div style={{ fontSize: 10, color: "#555", marginBottom: 4 }}>{t("ai_features.summary_label")}</div>
              <div style={{ fontSize: 13, color: "#ccc", lineHeight: 1.7 }}>{summary.summary}</div>
            </div>
          )}

          {summary.key_points?.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: "#555", marginBottom: 6 }}>{t("ai_features.key_points")}</div>
              {summary.key_points.map((p, i) => (
                <div key={i} style={{ display: "flex", gap: 8, marginBottom: 5 }}>
                  <span style={{ color: "#34D399", flexShrink: 0 }}>•</span>
                  <span style={{ fontSize: 13, color: "#ddd" }}>{p}</span>
                </div>
              ))}
            </div>
          )}

          {summary.action_items?.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: "#555", marginBottom: 6 }}>{t("ai_features.action_items")}</div>
              {summary.action_items.map((a, i) => (
                <div key={i} style={{ display: "flex", gap: 8, marginBottom: 5 }}>
                  <span style={{ color: "#FCD34D", flexShrink: 0 }}>☐</span>
                  <span style={{ fontSize: 13, color: "#ddd" }}>{a}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── واجهة تحديد المتحدثين ─────────────────── */}
      {!loading && tab === "diarize" && !diarResult && (
        <div style={{ background: "#060610", border: "1px solid #C084FC33", borderRadius: 12, padding: 14 }}>
          <div style={{ fontSize: 12, color: "#C084FC", fontWeight: 700, marginBottom: 10 }}>{t("ai_features.diarization_title")}</div>
          <div style={{ fontSize: 12, color: "#888", marginBottom: 12, lineHeight: 1.6 }}>
            {t("ai_features.diarization_requires")} <code style={{ color: "#FCD34D" }}>pip install pyannote.audio</code> {t("ai_features.diarization_env")} <code style={{ color: "#FCD34D" }}>.env</code>
          </div>
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 11, color: "#555", display: "block", marginBottom: 6 }}>
              {t("ai_features.num_speakers_label")}
            </label>
            <input
              type="number" min="1" max="10"
              value={numSpeakers}
              onChange={(e) => setNumSpeakers(e.target.value)}
              placeholder={t("ai_features.num_speakers_placeholder")}
              style={{ width: "100%", padding: "8px 12px", background: "#0c0c18", border: "1px solid #1e1e30", borderRadius: 8, color: "#fff", fontFamily: "inherit", fontSize: 13 }}
            />
          </div>
          <button onClick={() => run("diarize")}
            style={{ width: "100%", padding: "10px", background: "#C084FC", border: "none", borderRadius: 8, color: "#000", fontWeight: 700, cursor: "pointer", fontFamily: "inherit", fontSize: 13 }}>
            {t("ai_features.start_diarization")}
          </button>
        </div>
      )}

      {/* ── نتيجة تحديد المتحدثين ─────────────────── */}
      {!loading && diarResult && tab === "diarize" && (
        <div style={{ background: "#060610", border: "1px solid #C084FC33", borderRadius: 12, padding: 14 }}>
          <div style={{ fontSize: 12, color: "#C084FC", fontWeight: 700, marginBottom: 10 }}>
            👥 {t("ai_features.diarization_result", { count: diarResult.speakers_found })}
          </div>
          <div style={{ fontSize: 11, color: "#555" }}>
            {t("ai_features.diarization_update_note")}
          </div>
        </div>
      )}
    </div>
  );
}
