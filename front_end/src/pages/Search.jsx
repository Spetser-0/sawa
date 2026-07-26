/**
 * صفحة البحث العميق في الصوت
 * ابحث في كل تسجيلاتك بكلمة واحدة
 */
import { useState, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  Search as SearchIcon, Mic, MonitorPlay, Play,
  ChevronDown, ChevronUp, SearchX, AlertCircle,
} from "lucide-react";

function fmtTime(s) {
  const m = Math.floor(s / 60).toString().padStart(2, "0");
  return `${m}:${Math.floor(s % 60).toString().padStart(2, "0")}`;
}

export default function Search() {
  const { t } = useTranslation();
  const [query,       setQuery]       = useState("");
  const [results,     setResults]     = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [expanded,    setExpanded]    = useState({});

  const inputRef     = useRef(null);
  const debounceRef  = useRef(null);
  const navigate     = useNavigate();

  // ── البحث الرئيسي ─────────────────────────────────
  const doSearch = async (q) => {
    if (!q.trim()) { setResults(null); return; }
    setLoading(true);
    setError("");
    setSuggestions([]);

    try {
      const token = localStorage.getItem("sawa_token");
      const res   = await fetch(
        `/api/search?q=${encodeURIComponent(q.trim())}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) throw new Error((await res.json()).detail || t("search.search_failed"));
      setResults(await res.json());
      // افتح أول نتيجة تلقائياً
      const first = await res.clone().json();
      if (first.results[0]) setExpanded({ [first.results[0].video_id]: true });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // ── اقتراحات فورية ────────────────────────────────
  const fetchSuggestions = useCallback((q) => {
    clearTimeout(debounceRef.current);
    if (q.length < 2) { setSuggestions([]); return; }
    debounceRef.current = setTimeout(async () => {
      try {
        const token = localStorage.getItem("sawa_token");
        const res   = await fetch(
          `/api/search/suggest?q=${encodeURIComponent(q)}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (res.ok) setSuggestions((await res.json()).suggestions);
      } catch { /* تجاهل */ }
    }, 300);
  }, []);

  const handleChange = (e) => {
    setQuery(e.target.value);
    fetchSuggestions(e.target.value);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setSuggestions([]);
    doSearch(query);
  };

  // ── الانتقال للتسجيل عند اللحظة المحددة ──────────
  const goToMatch = (videoId, start) => {
    navigate(`/watch/${videoId}?t=${start}`);
  };

  // ══════════════════════════════════════════════════
  //  Render
  // ══════════════════════════════════════════════════
  return (
    <div style={{ maxWidth: 800, margin: "0 auto", padding: "32px 20px" }}>

      {/* ── رأس الصفحة ──────────────────────────────── */}
      <div style={{ textAlign: "center", marginBottom: 32 }}>
        <div style={{
          width: 64, height: 64, borderRadius: 18, margin: "0 auto 16px",
          background: "rgba(52,211,153,0.1)", border: "1px solid rgba(52,211,153,0.25)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <SearchIcon size={28} color="var(--green)" />
        </div>
          <h1 style={{ fontSize: 26, fontWeight: 900, marginBottom: 8 }}>
            {t("search.title")}
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
            {t("search.desc")}
          </p>
      </div>

      {/* ── شريط البحث ──────────────────────────────── */}
      <form onSubmit={handleSubmit} style={{ position: "relative", marginBottom: 24 }}>
        <div style={{ position: "relative" }}>
          <input
            ref={inputRef}
            value={query}
            onChange={handleChange}
            placeholder={t("search.placeholder")}
            style={{
              width: "100%", padding: "16px 20px", paddingInlineEnd: 56,
              fontSize: 16, borderRadius: 14,
              border: "2px solid var(--border)",
              background: "var(--bg-card)",
              color: "var(--text)", fontFamily: "inherit",
              outline: "none", boxSizing: "border-box",
              transition: "border-color 0.2s",
            }}
            onFocus={(e) => e.target.style.borderColor = "#34D399"}
            onBlur={(e) => e.target.style.borderColor = "var(--border)"}
          />
          <button type="submit" aria-label={t("search.title")}
            style={{
              position: "absolute", insetInlineEnd: 12, top: "50%", transform: "translateY(-50%)",
              background: "var(--green)", border: "none", borderRadius: 10,
              width: 36, height: 36, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
            {loading
              ? <span className="spin" style={{ width: 16, height: 16, border: "2px solid #000", borderTopColor: "transparent", borderRadius: "50%", display: "inline-block" }} />
              : <SearchIcon size={17} color="#04120c" strokeWidth={2.5} />
            }
          </button>
        </div>

        {/* اقتراحات */}
        {suggestions.length > 0 && (
          <div style={{
            position: "absolute", top: "calc(100% + 4px)", right: 0, left: 0,
            background: "var(--bg-card)", border: "1px solid var(--border)",
            borderRadius: 12, zIndex: 50, overflow: "hidden",
          }}>
            {suggestions.map((s) => (
              <div key={s}
                style={{ padding: "10px 16px", cursor: "pointer", fontSize: 14, transition: "background 0.1s" }}
                onMouseEnter={(e) => e.currentTarget.style.background = "var(--bg-hover)"}
                onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                onClick={() => { setQuery(s); setSuggestions([]); doSearch(s); }}
              >
                <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                  <SearchIcon size={13} color="var(--text-muted)" /> {s}
                </span>
              </div>
            ))}
          </div>
        )}
      </form>

      {/* خطأ */}
      {error && (
        <div style={{ padding: "12px 16px", background: "#F8717115", border: "1px solid #F8717133", borderRadius: 10, color: "var(--red)", fontSize: 13, marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
          <AlertCircle size={15} style={{ flexShrink: 0 }} />
          {error}
        </div>
      )}

      {/* ── ملخص النتائج ────────────────────────────── */}
      {results && (
        <div style={{ marginBottom: 20 }}>
          {results.total_matches === 0 ? (
            <div style={{ textAlign: "center", padding: "48px 20px", background: "var(--bg-card)", border: "1px dashed var(--border)", borderRadius: 14 }}>
              <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
                <SearchX size={36} color="var(--text-muted)" />
              </div>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>{t("search.no_results")}</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
                {t("search.no_results_desc", { query: results.query })}
              </div>
            </div>
          ) : (
            <div style={{
              display: "flex", gap: 12, flexWrap: "wrap",
              padding: "12px 16px", background: "#34D39910",
              border: "1px solid #34D39933", borderRadius: 12,
            }}>
              {[
                { label: t("search.total_results"), value: results.total_matches, color: "#34D399" },
                { label: t("search.recordings_found"), value: results.videos_found, color: "#818CF8" },
              ].map(s => (
                <div key={s.label} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ fontSize: 20, fontWeight: 900, color: s.color }}>{s.value}</span>
                  <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{s.label}</span>
                </div>
              ))}
              <span style={{ fontSize: 13, color: "var(--text-muted)", marginRight: "auto" }}>
                "{results.query}"
              </span>
            </div>
          )}
        </div>
      )}

      {/* ── النتائج ─────────────────────────────────── */}
      {results?.results.map((result) => (
        <div key={result.video_id} className="card fade-in"
          style={{ marginBottom: 12, border: expanded[result.video_id] ? "1px solid #34D39933" : "1px solid var(--border)" }}>

          {/* رأس الفيديو */}
          <div
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
            onClick={() => setExpanded(p => ({ ...p, [result.video_id]: !p[result.video_id] }))}
          >
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <span style={{
                width: 38, height: 38, borderRadius: 10, flexShrink: 0,
                background: "rgba(52,211,153,0.1)", border: "1px solid rgba(52,211,153,0.2)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <MonitorPlay size={18} color="var(--green)" />
              </span>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{result.video_title}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                  {result.created_at}
                  {result.duration && ` · ${fmtTime(result.duration)}`}
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ background: "#34D39920", color: "#34D399", borderRadius: 20, padding: "3px 12px", fontSize: 12, fontWeight: 700 }}>
                {result.match_count} {t("search.result_count")}
              </span>
              <span style={{ color: "var(--text-muted)", display: "flex" }}>
                {expanded[result.video_id] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </span>
            </div>
          </div>

          {/* قائمة التطابقات */}
          {expanded[result.video_id] && (
            <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 14 }}>
              {result.matches.map((match, i) => (
                <div key={i}
                  onClick={() => goToMatch(result.video_id, match.start)}
                  style={{
                    display: "flex", gap: 12, alignItems: "flex-start",
                    padding: "10px 12px", borderRadius: 10, marginBottom: 6,
                    cursor: "pointer", background: "var(--bg)",
                    border: "1px solid var(--border)", transition: "all 0.15s",
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = "#34D39966"; e.currentTarget.style.background = "#34D39908"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.background = "var(--bg)"; }}
                >
                  {/* التوقيت */}
                  <div style={{
                    flexShrink: 0, background: "#34D39920", color: "#34D399",
                    borderRadius: 8, padding: "4px 10px", fontSize: 12, fontWeight: 800,
                    fontFamily: "monospace", lineHeight: 1.6,
                  }}>
                    {fmtTime(match.start)}
                  </div>

                  {/* النص */}
                  <div style={{ flex: 1 }}>
                    {match.speaker && (
                      <div style={{ fontSize: 10, color: "#818CF8", marginBottom: 3, fontWeight: 700 }}>
                        {match.speaker}
                      </div>
                    )}
                    <div
                      style={{ fontSize: 13, lineHeight: 1.7, color: "var(--text)" }}
                      dangerouslySetInnerHTML={{ __html: match.context }}
                    />
                  </div>

                  {/* زر الانتقال */}
                  <div style={{ flexShrink: 0, color: "var(--text-muted)", display: "flex", alignItems: "center" }}>
                    <Play size={15} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {/* ── نقطة فارغة ──────────────────────────────── */}
      {!results && !loading && (
        <div style={{ textAlign: "center", padding: "48px 20px", color: "var(--text-muted)" }}>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 16, opacity: 0.35 }}>
            <Mic size={48} />
          </div>
          <div style={{ fontSize: 14 }}>{t("search.empty_state")}</div>
          <div style={{ fontSize: 12, marginTop: 8, opacity: 0.7 }}>
            {t("search.empty_example")}
          </div>
        </div>
      )}
    </div>
  );
}
