// ── صفحة التسجيل ────────────────────────────────────
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Recorder from "../components/Recorder";
import { VideoOff, Lock, AlertTriangle, ArrowRight, Settings2 } from "lucide-react";

export function RecordPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  return (
    <div style={{ maxWidth: 700, margin: "0 auto", padding: "40px 20px" }}>
      <div style={{ textAlign: "center", marginBottom: 32 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 8 }}>{t("pages.record_title")}</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
          {t("pages.record_desc")}
        </p>
      </div>
      <Recorder onUploadDone={(video) => navigate(`/watch/${video.id}`)} />
    </div>
  );
}


// ── صفحة المشاهدة ───────────────────────────────────
import { useState, useEffect, useRef } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { videosAPI } from "../api/client";
import VideoPlayer from "../components/VideoPlayer";
import { useAuth } from "../hooks/useAuth";

export function WatchPage() {
  const { id }               = useParams();
  const { t } = useTranslation();
  const [searchParams]       = useSearchParams();
  const startTime            = parseFloat(searchParams.get("t") || "0");
  const [video,  setVideo]   = useState(null);
  const [error,  setError]   = useState("");
  const [loading,setLoading] = useState(true);

  // إعدادات المشاركة
  const [showSettings, setShowSettings] = useState(false);
  const [sharePassword, setSharePassword] = useState("");
  const [shareExpiry, setShareExpiry] = useState("");
  const [settingsMsg, setSettingsMsg] = useState("");
  
  const { user } = useAuth();

  const fetchVideo = () => {
    setLoading(true);
    videosAPI.getVideo(id)
      .then(setVideo)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchVideo();
  }, [id]);

  const handleUpdateShare = async (e) => {
    e.preventDefault();
    setSettingsMsg(t("pages.updating"));
    try {
      await videosAPI.updateShareSettings(id, {
        password: sharePassword || "",
        expires_in_days: shareExpiry ? parseInt(shareExpiry) : 0
      });
      setSettingsMsg(t("pages.update_success"));
      setTimeout(() => setShowSettings(false), 2000);
      fetchVideo(); // Reload to get updated state
    } catch (err) {
      setSettingsMsg(t("pages.update_failed") + err.message);
    }
  };

  if (loading) return (
    <div style={{ textAlign: "center", padding: "80px 20px" }}>
      <div className="spin" style={{ width: 36, height: 36, border: "3px solid var(--border)", borderTopColor: "var(--green)", borderRadius: "50%", margin: "0 auto" }} />
    </div>
  );

  if (error) return (
    <div style={{ textAlign: "center", padding: "80px 20px" }}>
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
        <VideoOff size={44} color="var(--red)" />
      </div>
      <h2 style={{ marginBottom: 8 }}>{t("pages.video_not_found")}</h2>
      <p style={{ color: "var(--text-muted)", marginBottom: 20 }}>{error}</p>
      <Link to="/dashboard" className="btn btn-outline">{t("pages.back_to_dashboard")}</Link>
    </div>
  );

  const mediaUrl = videosAPI.streamUrl(video.id);
  const isOwner = user && video.owner_id === user.id;

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <Link to="/dashboard" style={{ color: "var(--text-muted)", fontSize: 13, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6 }}>
          <ArrowRight size={14} />
          {t("pages.back")}
        </Link>
        {isOwner && (
          <button className="btn btn-outline btn-sm" onClick={() => setShowSettings(!showSettings)}>
            <Settings2 size={13} />
            {t("pages.protected_share_settings")}
          </button>
        )}
      </div>

      {showSettings && (
        <div className="card fade-in" style={{ marginBottom: 20, background: "var(--bg)", border: "1px solid var(--purple)" }}>
          <h3 style={{ fontSize: 16, marginBottom: 16 }}>{t("pages.share_protect_title")}</h3>
          <form onSubmit={handleUpdateShare} style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label>{t("pages.new_password_label")}</label>
              <input type="password" value={sharePassword} onChange={e => setSharePassword(e.target.value)} placeholder="••••••••" />
            </div>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label>{t("pages.link_expiry_label")}</label>
              <input type="number" min="0" value={shareExpiry} onChange={e => setShareExpiry(e.target.value)} placeholder={t("pages.expiry_placeholder")} />
            </div>
            <button type="submit" className="btn btn-primary">{t("pages.save_settings")}</button>
          </form>
          {settingsMsg && <div style={{ marginTop: 12, fontSize: 13, color: "var(--green)" }}>{settingsMsg}</div>}
        </div>
      )}

      <VideoPlayer video={video} mediaUrl={mediaUrl} startTime={startTime} />
    </div>
  );
}


// ── صفحة المشاركة العامة (بدون تسجيل دخول) ──────────
export function SharePage() {
  const { token }            = useParams();
  const { t } = useTranslation();
  const [video,  setVideo]   = useState(null);
  const [error,  setError]   = useState("");
  const [loading,setLoading] = useState(true);
  
  // Feature 4: Password state
  const [needsPassword, setNeedsPassword] = useState(false);
  const [password, setPassword] = useState("");
  const [unlockError, setUnlockError] = useState("");
  const [unlocking, setUnlocking] = useState(false);
  const [tempToken, setTempToken] = useState(null);

  const fetchShared = async (authToken = null) => {
    try {
      setLoading(true);
      // إذا كان لدينا توكن مؤقت، سنحتاج لتمريره (client.js سيحتاج لتعديل طفيف، أو نضعه في هيدر)
      // للتبسيط: API_BASE/videos/share/{token} تقبل Header
      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};
      
      const res = await fetch(`${import.meta.env.VITE_API_URL ? import.meta.env.VITE_API_URL+'/api' : '/api'}/videos/share/${token}`, { headers });
      if (!res.ok) {
        const err = await res.json().catch(()=>({}));
        if (res.status === 401 && err.detail === "requires_password") {
          setNeedsPassword(true);
          setLoading(false);
          return;
        }
        throw new Error(err.detail || t("pages.share_not_available"));
      }
      const data = await res.json();
      setVideo(data);
      setNeedsPassword(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchShared(tempToken);
  }, [token, tempToken]);

  const handleUnlock = async (e) => {
    e.preventDefault();
    setUnlocking(true);
    setUnlockError("");
    try {
      const res = await videosAPI.unlockShare(token, password);
      setTempToken(res.access_token);
      // fetchShared will re-run
    } catch (err) {
      setUnlockError(err.message || t("pages.share_wrong_password"));
    } finally {
      setUnlocking(false);
    }
  };

  if (loading) return (
    <div style={{ textAlign: "center", padding: "80px" }}>
      <div className="spin" style={{ width: 36, height: 36, border: "3px solid var(--border)", borderTopColor: "var(--green)", borderRadius: "50%", margin: "0 auto" }} />
    </div>
  );

  if (needsPassword) return (
    <div style={{ maxWidth: 400, margin: "80px auto", padding: "40px 20px", textAlign: "center" }} className="card fade-in">
      <div style={{
        width: 64, height: 64, borderRadius: 18, margin: "0 auto 16px",
        background: "rgba(192,132,252,0.1)", border: "1px solid rgba(192,132,252,0.25)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <Lock size={26} color="var(--purple)" />
      </div>
      <h2 style={{ marginBottom: 12 }}>{t("pages.share_password_title")}</h2>
      <p style={{ color: "var(--text-muted)", marginBottom: 24, fontSize: 14 }}>{t("pages.share_password_desc")}</p>
      
      <form onSubmit={handleUnlock}>
        <input 
          type="password" 
          placeholder={t("pages.share_password_placeholder")} 
          value={password}
          onChange={e => setPassword(e.target.value)}
          style={{ marginBottom: 16, textAlign: "center" }}
          autoFocus
        />
        {unlockError && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 16 }}>{unlockError}</div>}
        <button type="submit" className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={unlocking}>
          {unlocking ? t("pages.share_verifying") : t("pages.share_unlock")}
        </button>
      </form>
    </div>
  );

  if (error) return (
    <div style={{ textAlign: "center", padding: "80px 20px" }}>
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
        <AlertTriangle size={40} color="#FCD34D" />
      </div>
      <h2>{t("pages.share_not_available")}</h2>
      <p style={{ color: "var(--text-muted)" }}>{error}</p>
    </div>
  );

  let mediaUrl = videosAPI.shareStreamUrl(token);
  if (tempToken) {
    mediaUrl += `?access_token=${tempToken}`; // You can pass token in query param for <video src>
  }

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 20px" }}>
      {/* شعار صغير */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <Link to="/" style={{ textDecoration: "none", fontSize: 20, fontWeight: 900, background: "linear-gradient(135deg, #34D399, #818CF8)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
          {t("app_name")}
        </Link>
        <Link to="/auth" className="btn btn-primary" style={{ fontSize: 12, padding: "6px 14px" }}>
          {t("pages.share_create_cta")}
        </Link>
      </div>
      <VideoPlayer video={video} mediaUrl={mediaUrl} tempToken={tempToken} />
    </div>
  );
}
