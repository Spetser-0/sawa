/**
 * مشغّل الفيديو مع النص المفرَّغ + الميزات الذكية + التعليقات + HLS
 */
import { useState, useRef, useEffect } from "react";
import { transcriptAPI, aiAPI, commentsAPI, analyticsAPI, videosAPI } from "../api/client";
import AIFeatures from "./AIFeatures";
import { useTranslation } from "react-i18next";
import { useAuth } from "../hooks/useAuth";
import {
  Eye, Clock, Calendar, Link2, Sparkles, ChevronUp, ChevronDown,
  Trash2, Check, Copy, Pencil, Loader2, AlertCircle, RotateCcw,
} from "lucide-react";
import { useToast } from "./ui/Toast";

// Optional import for HLS (we'll check dynamically or assume it's bundled if imported)
// For a standard Vite project, we just import it:
import Hls from "hls.js";

const SPEAKER_COLORS = ["#34D399","#818CF8","#F59E0B","#F472B6","#60A5FA","#C084FC"];
const speakerColor = (name) => {
  if (!name) return "var(--text-muted)";
  const idx = parseInt(name.replace(/\D/g,"")) - 1 || 0;
  return SPEAKER_COLORS[idx % SPEAKER_COLORS.length];
};

const fmtTime = (s) => `${Math.floor(s/60).toString().padStart(2,"0")}:${Math.floor(s%60).toString().padStart(2,"0")}`;

export default function VideoPlayer({ video, mediaUrl, startTime = 0, tempToken = null }) {
  const toast = useToast();
  const [transcript,   setTranscript]   = useState(null);
  const [status,       setStatus]       = useState("loading");
  const [currentTime,  setCurrentTime]  = useState(0);
  const [duration,     setDuration]     = useState(video?.duration || 0);
  const [activeIdx,    setActiveIdx]    = useState(-1);
  const [isEditing,    setIsEditing]    = useState(false);
  const [editText,     setEditText]     = useState("");
  const [copied,       setCopied]       = useState(false);
  const [showAI,       setShowAI]       = useState(false);
  const [isHlsLoaded,  setIsHlsLoaded]  = useState(false);

  // ── Feature 2: Smart Chapters ──
  const [chapters, setChapters] = useState([]);
  const [generatingChapters, setGeneratingChapters] = useState(false);

  // ── Feature 3: Comments ──
  const [comments, setComments] = useState([]);
  const [commentText, setCommentText] = useState("");
  const [authorName, setAuthorName] = useState("");
  const [activeCommentId, setActiveCommentId] = useState(null);
  const { user } = useAuth();
  const { t } = useTranslation();

  const videoRef  = useRef(null);
  const hlsRef    = useRef(null);
  const segRefs   = useRef({});
  const pollRef   = useRef(null);
  const analyticsInterval = useRef(null);
  const secondsWatched = useRef(0);

  // ── تهيئة HLS (Feature 6) ──
  useEffect(() => {
    if (!video || !videoRef.current) return;
    
    // إذا كان hls_ready جاهزًا والمشغل يدعم HLS
    if (video.hls_ready && Hls.isSupported()) {
      const hls = new Hls({ maxBufferLength: 30 });
      hlsRef.current = hls;
      // نضيف التوكن إذا كان هناك رابط مشاركة محمي (لتبسيط الأمر مع hls، نفضل تمرير التوكن عبر headers أو query params)
      // لكن Vercel/Cloudflare يتعاملون معها. في حالتنا hlsUrl في client لا تدعم توكن المشاركة المحمية،
      // لذا HLS سيكون معطلاً للروابط المحمية إلا إذا أضفناه. للتبسيط، سنستخدم hls_ready للمشاهدة العادية.
      
      const streamSrc = (tempToken) ? `${videosAPI.hlsUrl(video.id)}?access_token=${tempToken}` : videosAPI.hlsUrl(video.id);
      
      hls.loadSource(streamSrc);
      hls.attachMedia(videoRef.current);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setIsHlsLoaded(true);
        if (startTime > 0) {
          videoRef.current.currentTime = startTime;
          videoRef.current.play().catch(()=>console.log("Auto-play blocked"));
        }
      });
      hls.on(Hls.Events.ERROR, (e, data) => {
        console.warn("HLS Error:", data);
        if (data.fatal) hls.destroy();
      });
    } else {
      // Fallback
      videoRef.current.src = mediaUrl;
      if (startTime > 0) {
        videoRef.current.currentTime = startTime;
      }
    }

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
      }
    };
  }, [video, mediaUrl, startTime, tempToken]);


  // ── جلب البيانات (تفريغ، فصول، تعليقات) ──
  const fetchTranscript = async () => {
    if (!video) return;
    try {
      const data = await transcriptAPI.get(video.id);
      setTranscript(data);
      setStatus(data.status);
      if (data.full_text) setEditText(data.full_text);
      if (data.status === "pending" || data.status === "processing") {
        pollRef.current = setTimeout(fetchTranscript, 4000);
      }
    } catch { setStatus("error"); }
  };

  const fetchChapters = async () => {
    if (!video) return;
    try {
      const res = await aiAPI.getChapters(video.id);
      setChapters(res.chapters || []);
    } catch (e) { console.error("Chapters load error:", e); }
  };

  const fetchComments = async () => {
    if (!video) return;
    try {
      const res = await commentsAPI.list(video.id);
      setComments(res || []);
    } catch (e) { console.error("Comments load error:", e); }
  };

  useEffect(() => {
    fetchTranscript();
    fetchChapters();
    fetchComments();
    return () => clearTimeout(pollRef.current);
  }, [video?.id]);


  // ── مزامنة النص والتوقيت ──
  useEffect(() => {
    if (!transcript?.segments) return;
    const idx = transcript.segments.findIndex(
      (s) => currentTime >= s.start && currentTime < s.end
    );
    if (idx !== activeIdx) {
      setActiveIdx(idx);
      if (idx >= 0 && segRefs.current[idx]) {
        segRefs.current[idx].scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
  }, [currentTime, transcript]);


  // ── تحليلات المشاهدة (Feature 5) ──
  useEffect(() => {
    const isPlaying = () => videoRef.current && !videoRef.current.paused && !videoRef.current.ended;

    analyticsInterval.current = setInterval(() => {
      if (isPlaying()) {
        secondsWatched.current += 30; // نضيف 30 ثانية للعداد
        analyticsAPI.ping(video.id, secondsWatched.current).catch(console.error);
      }
    }, 30000); // كل 30 ثانية فعلياً

    return () => clearInterval(analyticsInterval.current);
  }, [video?.id]);


  const seekTo  = (t) => { if (videoRef.current) { videoRef.current.currentTime = t; videoRef.current.play(); } };
  const copyAll = () => { navigator.clipboard.writeText(transcript?.full_text || ""); setCopied(true); setTimeout(() => setCopied(false), 2000); };

  const saveEdit = async () => {
    try {
      await transcriptAPI.edit(video.id, { full_text: editText });
      setTranscript((t) => ({ ...t, full_text: editText }));
      setIsEditing(false);
    } catch (e) { toast.error(t("player.save_failed") + e.message); }
  };

  // Feature 2
  const handleGenerateChapters = async () => {
    setGeneratingChapters(true);
    try {
      const res = await aiAPI.generateChapters(video.id);
      setChapters(res.chapters);
    } catch (e) {
      toast.error(t("player.generate_chapters_failed") + e.message);
    } finally {
      setGeneratingChapters(false);
    }
  };

  // Feature 3
  const handleAddComment = async (e) => {
    e.preventDefault();
    if (!commentText.trim()) return;
    
    try {
      const c = await commentsAPI.add(video.id, {
        timestamp_seconds: currentTime,
        text: commentText,
        author_name: user?.name || authorName || t("player.guest_default")
      });
      setComments([...comments, c].sort((a,b) => a.timestamp_seconds - b.timestamp_seconds));
      setCommentText("");
    } catch (e) {
      toast.error(t("player.add_comment_failed") + e.message);
    }
  };

  const handleDeleteComment = async (id) => {
    try {
      await commentsAPI.delete(id);
      setComments(comments.filter(c => c.id !== id));
      setActiveCommentId(null);
    } catch (e) {
      toast.error(t("player.delete_comment_failed") + e.message);
    }
  };

  if (!video) return null;

  return (
    <div className="watch-grid" style={{ alignItems:"start" }}>

      {/* ── عمود الفيديو ──────────────────────────── */}
      <div>
        <div style={{ borderRadius:14, overflow:"hidden", background:"#000", border:"1px solid var(--border)", marginBottom:16, position: "relative" }}>
          
          <video ref={videoRef} controls
            style={{ width:"100%", display:"block", maxHeight:440 }}
            onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
            onLoadedMetadata={(e) => setDuration(e.target.duration)}
          />

          {/* Feature 2 & 3: Timeline Overlays (Chapters & Comments) */}
          {duration > 0 && (
            <div style={{ position: "absolute", bottom: 44, left: 16, right: 16, height: 10, pointerEvents: "none" }}>
              
              {/* فصول */}
              {chapters.map((ch, i) => {
                const left = (ch.start / duration) * 100;
                return (
                  <div key={`ch-${i}`} 
                    style={{ position: "absolute", left: `${left}%`, top: 0, bottom: 0, width: 2, background: "#818CF8", zIndex: 10 }}
                    title={ch.title}
                  />
                );
              })}

              {/* تعليقات */}
              {comments.map((c) => {
                const left = (c.timestamp_seconds / duration) * 100;
                const isActive = activeCommentId === c.id;
                return (
                  <div key={c.id} 
                    style={{ position: "absolute", left: `calc(${left}% - 5px)`, top: -2, width: 10, height: 10, borderRadius: "50%", background: isActive ? "#34D399" : "#fff", border: "2px solid #000", zIndex: 20, pointerEvents: "auto", cursor: "pointer", transition: "transform 0.2s", transform: isActive ? "scale(1.5)" : "scale(1)" }}
                    onClick={() => { setActiveCommentId(c.id); seekTo(c.timestamp_seconds); }}
                  />
                );
              })}
            </div>
          )}

          {video.hls_ready && isHlsLoaded && (
            <div style={{ position: "absolute", top: 12, left: 12, background: "rgba(0,0,0,0.6)", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 700, color: "#fff", pointerEvents: "none" }}>
              HLS
            </div>
          )}
        </div>

        {/* بيانات الفيديو */}
        <div className="card" style={{ marginBottom:16 }}>
          <h2 style={{ fontSize:18, fontWeight:700, marginBottom:8 }}>{video.title}</h2>
          <div style={{ display:"flex", gap:12, flexWrap:"wrap", marginBottom:12 }}>
            <span style={{ fontSize:12, color:"var(--text-muted)", display:"inline-flex", alignItems:"center", gap:4 }}><Eye size={12} /> {video.views_count} {t("player.views_count")}</span>
            {video.duration && <span style={{ fontSize:12, color:"var(--text-muted)", display:"inline-flex", alignItems:"center", gap:4 }}><Clock size={12} /> {fmtTime(video.duration)}</span>}
            <span style={{ fontSize:12, color:"var(--text-muted)", display:"inline-flex", alignItems:"center", gap:4 }}><Calendar size={12} /> {new Date(video.created_at).toLocaleDateString("ar")}</span>
          </div>

          {/* رابط المشاركة */}
          <div style={{ padding:"10px 14px", background:"var(--bg)", borderRadius:8, border:"1px solid var(--border)", display:"flex", gap:10, alignItems:"center" }}>
            <Link2 size={13} color="var(--text-muted)" style={{ flexShrink:0 }} />
            <span style={{ fontSize:12, color:"var(--green)", flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", direction:"ltr", textAlign:"left" }}>
              {window.location.origin}/share/{video.share_token}
            </span>
            <button className="btn btn-outline" style={{ padding:"4px 12px", fontSize:11, flexShrink:0 }}
              onClick={() => { navigator.clipboard.writeText(`${window.location.origin}/share/${video.share_token}`); setCopied(true); setTimeout(()=>setCopied(false),2000); }}>
              {copied ? t("player.copied") : t("player.copy")}
            </button>
          </div>
        </div>

        {/* ── الميزات الذكية ────────────────────────── */}
        <div className="card" style={{ marginBottom:16 }}>
          <button
            onClick={() => setShowAI(!showAI)}
            style={{ width:"100%", display:"flex", justifyContent:"space-between", alignItems:"center", background:"none", border:"none", cursor:"pointer", fontFamily:"inherit", padding:0 }}
          >
            <span style={{ fontWeight:700, fontSize:15, display:"inline-flex", alignItems:"center", gap:6 }}>
              <Sparkles size={15} color="var(--purple)" /> {t("player.smart_features")}
            </span>
            <div style={{ display:"flex", gap:6 }}>
              <span style={{ fontSize:10, background:"#34D39920", color:"#34D399", borderRadius:6, padding:"2px 8px" }}>{t("player.badge_translate")}</span>
              <span style={{ fontSize:10, background:"#818CF820", color:"#818CF8", borderRadius:6, padding:"2px 8px" }}>{t("player.badge_summarize")}</span>
              <span style={{ fontSize:10, background:"#C084FC20", color:"#C084FC", borderRadius:6, padding:"2px 8px" }}>{t("player.badge_speakers")}</span>
              <span style={{ color:"var(--text-muted)", display:"flex", alignItems:"center" }}>{showAI ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</span>
            </div>
          </button>

          {showAI && (
            <div style={{ marginTop:14, borderTop:"1px solid var(--border)", paddingTop:14 }}>
              <AIFeatures videoId={video.id} transcriptDone={status === "done"} />
            </div>
          )}
        </div>

        {/* ── Feature 2: فصول الفيديو ────────────────────────── */}
        <div className="card" style={{ marginBottom:16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700 }}>{t("player.chapters")}</h3>
            {status === "done" && chapters.length === 0 && (
              <button className="btn btn-outline" style={{ fontSize: 11, padding: "4px 12px" }} onClick={handleGenerateChapters} disabled={generatingChapters}>
                {generatingChapters ? t("player.generating") : t("player.generate_chapters")}
              </button>
            )}
          </div>

          {chapters.length > 0 ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
              {chapters.map((ch, i) => (
                <div key={i} onClick={() => seekTo(ch.start)} style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: 12, cursor: "pointer", transition: "border-color 0.2s" }} onMouseEnter={e => e.currentTarget.style.borderColor = "var(--purple)"} onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}>
                  <div style={{ fontSize: 11, color: "var(--purple)", fontWeight: 700, marginBottom: 4 }}>{fmtTime(ch.start)}</div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{ch.title}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{ch.summary}</div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: "10px 0" }}>{t("player.no_chapters")}</div>
          )}
        </div>

        {/* ── Feature 3: التعليقات ────────────────────────── */}
        <div className="card">
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>{t("player.comments")}</h3>
          
          <form onSubmit={handleAddComment} style={{ display: "flex", gap: 10, marginBottom: 20 }}>
            {!user && (
              <input type="text" placeholder={t("player.guest_name_placeholder")} value={authorName} onChange={e => setAuthorName(e.target.value)} style={{ width: 120, fontSize: 12 }} />
            )}
            <input type="text" placeholder={`${t("player.comment_placeholder")} ${fmtTime(currentTime)}...`} value={commentText} onChange={e => setCommentText(e.target.value)} style={{ flex: 1, fontSize: 13 }} />
            <button type="submit" className="btn btn-primary" style={{ padding: "0 16px" }}>{t("player.send")}</button>
          </form>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {comments.length === 0 && <div style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center" }}>{t("player.no_comments")}</div>}
            
            {comments.map(c => (
              <div key={c.id} style={{ display: "flex", gap: 12, alignItems: "flex-start", background: activeCommentId === c.id ? "#34D39910" : "transparent", padding: "8px", borderRadius: 8, transition: "background 0.2s" }}>
                <div style={{ width: 32, height: 32, borderRadius: "50%", background: "var(--border)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, flexShrink: 0 }}>
                  {c.author_name.charAt(0).toUpperCase()}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "baseline", marginBottom: 4 }}>
                    <span style={{ fontSize: 13, fontWeight: 700 }}>{c.author_name}</span>
                    <span onClick={() => seekTo(c.timestamp_seconds)} style={{ fontSize: 11, color: "var(--purple)", cursor: "pointer" }} className="badge">{fmtTime(c.timestamp_seconds)}</span>
                  </div>
                  <div style={{ fontSize: 13, color: "var(--text)" }}>{c.text}</div>
                </div>
                {/* Delete button (only for author or video owner) */}
                {(user && (user.id === c.user_id || user.id === video.owner_id)) && (
                  <button onClick={() => handleDeleteComment(c.id)} style={{ background: "none", border: "none", color: "var(--red)", cursor: "pointer", opacity: 0.5, display: "flex", padding: 2 }} title={t("player.delete_comment")}><Trash2 size={14} /></button>
                )}
              </div>
            ))}
          </div>
        </div>

      </div>

      {/* ── عمود التفريغ ──────────────────────────── */}
      <div className="card" style={{ position:"sticky", top:20, maxHeight:"85vh", display:"flex", flexDirection:"column" }}>

        {/* رأس */}
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:14, flexShrink:0 }}>
          <span style={{ fontWeight:700, fontSize:15 }}>{t("player.transcript")}</span>
          <div style={{ display:"flex", gap:6 }}>
            {status === "done" && !isEditing && (
              <>
                <button className="btn btn-outline" style={{ padding:"4px 10px" }} onClick={copyAll} title={t("player.copy")}>
                  {copied ? <Check size={13} color="var(--green)" /> : <Copy size={13} />}
                </button>
                <button className="btn btn-outline" style={{ padding:"4px 10px" }} onClick={() => setIsEditing(true)} title={t("player.save")}>
                  <Pencil size={13} />
                </button>
              </>
            )}
            {isEditing && (
              <>
                <button className="btn btn-primary" style={{ padding:"4px 10px", fontSize:11 }} onClick={saveEdit}>{t("player.save")}</button>
                <button className="btn btn-outline" style={{ padding:"4px 10px", fontSize:11 }} onClick={() => setIsEditing(false)}>{t("player.cancel")}</button>
              </>
            )}
          </div>
        </div>

        {/* حالات التفريغ */}
        {(status === "pending" || status === "processing") && (
          <div style={{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", padding:20 }}>
            <Loader2 size={28} color="var(--green)" className="spin" style={{ marginBottom:12 }} />
            <div style={{ fontWeight:600, marginBottom:6 }}>{status === "pending" ? t("player.pending") : t("player.processing")}</div>
            <div style={{ fontSize:12, color:"var(--text-muted)", marginBottom:16 }}>{t("player.auto_appear")}</div>
            <div style={{ display:"flex", gap:4 }}>
              {[0,1,2].map(i => (
                <div key={i} style={{ width:8, height:8, borderRadius:"50%", background:"var(--green)", animation:`pulse-ring 1.2s ${i*0.2}s infinite` }} />
              ))}
            </div>
          </div>
        )}

        {status === "failed" && (
          <div style={{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center" }}>
            <AlertCircle size={28} color="var(--red)" style={{ marginBottom:8 }} />
            <div style={{ color:"var(--red)", marginBottom:12, fontSize:13 }}>{t("player.failed")}</div>
            <button className="btn btn-outline" style={{ fontSize:12 }}
              onClick={() => transcriptAPI.retry(video.id).then(fetchTranscript)}>
              <RotateCcw size={13} /> {t("player.retry")}
            </button>
          </div>
        )}

        {/* وضع التعديل */}
        {status === "done" && isEditing && (
          <textarea value={editText} onChange={(e) => setEditText(e.target.value)}
            style={{ flex:1, resize:"none", lineHeight:1.8, fontSize:13 }} />
        )}

        {/* الجمل المتزامنة مع دعم المتحدثين */}
        {status === "done" && !isEditing && transcript?.segments && (
          <div style={{ flex:1, overflowY:"auto", paddingLeft:2 }}>
            {transcript.segments.map((seg, idx) => {
              const isActive  = idx === activeIdx;
              const spColor   = speakerColor(seg.speaker);
              const prevSpeaker = idx > 0 ? transcript.segments[idx-1].speaker : null;
              const showLabel = seg.speaker && seg.speaker !== prevSpeaker;

              return (
                <div key={idx} ref={(el) => segRefs.current[idx] = el}>
                  {/* اسم المتحدث عند التغيير */}
                  {showLabel && (
                    <div style={{ padding:"8px 12px 2px", fontSize:11, fontWeight:700, color:spColor }}>
                      {seg.speaker}
                    </div>
                  )}
                  <div onClick={() => seekTo(seg.start)}
                    style={{ padding:"8px 12px", borderRadius:8, marginBottom:2, cursor:"pointer",
                      background: isActive ? "#34D39920" : "transparent",
                      border:`1px solid ${isActive ? "#34D39955" : "transparent"}`,
                      transition:"all 0.2s", lineHeight:1.7,
                      borderRight: seg.speaker ? `3px solid ${spColor}` : "3px solid transparent",
                    }}
                  >
                    <span style={{ fontSize:10, color:"var(--text-muted)", display:"block", marginBottom:1 }}>
                      {fmtTime(seg.start)}
                    </span>
                    <span style={{ fontSize:13, color: isActive ? "var(--green)" : "var(--text)", fontWeight: isActive ? 600 : 400 }}>
                      {seg.text}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* تصدير */}
        {status === "done" && (
          <div style={{ borderTop:"1px solid var(--border)", paddingTop:12, marginTop:8, flexShrink:0 }}>
            <div style={{ fontSize:11, color:"var(--text-muted)", marginBottom:8 }}>{t("player.export")}</div>
            <div style={{ display:"flex", gap:5, flexWrap:"wrap" }}>
              {[
                { fmt:"txt",  label:".txt",  color:"#34D399" },
                { fmt:"srt",  label:".srt",  color:"#818CF8" },
                { fmt:"docx", label:".docx", color:"#60A5FA" },
                { fmt:"json", label:".json", color:"#F59E0B" },
              ].map(({ fmt, label, color }) => (
                <a key={fmt} href={aiAPI.exportUrl(video.id, fmt)} download
                  style={{ flex:1, minWidth:50, textAlign:"center", padding:"6px 4px", borderRadius:8,
                    border:`1px solid ${color}33`, color, fontSize:12, fontWeight:700,
                    textDecoration:"none", background:`${color}10`,
                  }}>
                  {label}
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
