import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { videosAPI } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import Analytics from "../components/Analytics";
import Uploader from "../components/Uploader";
import { useToast } from "../components/ui/Toast";
import { VideoCardSkeleton, EmptyState, ConfirmDialog } from "../components/ui/Primitives";
import {
  Video, Mic, BarChart3, Link2, Trash2, Check,
  Clock, HardDrive, Film, MonitorPlay, Upload,
} from "lucide-react";

export default function Dashboard() {
  const { t, i18n } = useTranslation();
  const [videos,      setVideos]      = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [deleting,    setDeleting]    = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [copied,      setCopied]      = useState(null);
  const [analyticsId, setAnalyticsId] = useState(null);
  const [showUploader, setShowUploader] = useState(false);

  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();

  const STATUS_MAP = {
    pending:    { label: t("dashboard.status_pending"),    color: "#FCD34D" },
    processing: { label: t("dashboard.status_processing"), color: "#818CF8" },
    done:       { label: t("dashboard.status_done"),       color: "#34D399" },
    failed:     { label: t("dashboard.status_failed"),     color: "#F87171" },
  };

  function formatSize(bytes) {
    if (!bytes) return "";
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatDur(sec) {
    if (!sec) return "";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }

  useEffect(() => {
    videosAPI.getMyVideos()
      .then(setVideos)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await videosAPI.deleteVideo(deleteTarget.id);
      setVideos((v) => v.filter((x) => x.id !== deleteTarget.id));
      toast.success(t("dashboard.deleted_success"));
    } catch (e) {
      toast.error(t("dashboard.delete_failed") + " " + e.message);
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  };

  const copyShare = (video) => {
    const url = `${window.location.origin}/share/${video.share_token}`;
    navigator.clipboard.writeText(url);
    setCopied(video.id);
    toast.success(t("dashboard.copy_link_title"));
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="page page-medium">
      {/* رأس الصفحة */}
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 className="page-title">{t("dashboard.title")}</h1>
          <p className="page-subtitle">
            {videos.length} {t("dashboard.recording")} · {t("dashboard.plan_label")}{" "}
            <span style={{ color: "var(--green)", fontWeight: 700 }}>
              {user?.plan === "free" ? t("dashboard.plan_free") : "Pro"}
            </span>
            {user?.plan === "free" && ` (${videos.length}/25)`}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn btn-outline" onClick={() => setShowUploader(!showUploader)}>
            <Upload size={16} />
            {t("dashboard.upload_button", "رفع ملف")}
          </button>
          <Link to="/record" className="btn btn-primary">
            <Video size={16} />
            {t("dashboard.new_recording")}
          </Link>
        </div>
      </div>

      {/* مرفّع الملفات */}
      {showUploader && (
        <Uploader onSuccess={(id) => { setShowUploader(false); navigate(`/watch/${id}`); }} />
      )}

      {/* تحميل — skeletons */}
      {loading && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[0, 1, 2].map((i) => <VideoCardSkeleton key={i} />)}
        </div>
      )}

      {/* فارغة */}
      {!loading && videos.length === 0 && (
        <EmptyState
          icon={<Mic size={30} color="var(--green)" />}
          title={t("dashboard.empty")}
          description={t("dashboard.empty_desc")}
          action={<Link to="/record" className="btn btn-primary btn-lg">{t("dashboard.start_first")}</Link>}
        />
      )}

      {/* قائمة التسجيلات */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {!loading && videos.map((v) => {
          const ts = STATUS_MAP[v.transcript_status] || STATUS_MAP.pending;
          return (
            <div
              key={v.id}
              className="card card-hover fade-in"
              style={{ display: "flex", gap: 14, alignItems: "center", cursor: "pointer", padding: "16px 20px" }}
              onClick={() => navigate(`/watch/${v.id}`)}
            >
              {/* ثامبنيل */}
              <div style={{
                width: 80, height: 50, borderRadius: 10, flexShrink: 0,
                background: "linear-gradient(135deg, rgba(52,211,153,0.14), rgba(129,140,248,0.14))",
                border: "1px solid var(--border)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                {v.hls_ready
                  ? <Film size={20} color="var(--blue)" />
                  : <MonitorPlay size={20} color="var(--green)" />}
              </div>

              {/* معلومات */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="text-truncate" style={{ fontWeight: 700, fontSize: 14, marginBottom: 6 }}>
                  {v.title}
                </div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {new Date(v.created_at).toLocaleDateString(i18n.language === "ar" ? "ar" : "en")}
                  </span>
                  {v.duration > 0 && (
                    <span style={{ fontSize: 11, color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: 3 }}>
                      <Clock size={11} /> {formatDur(v.duration)}
                    </span>
                  )}
                  {v.file_size > 0 && (
                    <span style={{ fontSize: 11, color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: 3 }}>
                      <HardDrive size={11} /> {formatSize(v.file_size)}
                    </span>
                  )}
                  <span className="chip" style={{ background: ts.color + "18", color: ts.color }}>
                    <span style={{ width: 5, height: 5, borderRadius: "50%", background: ts.color, animation: v.transcript_status === "processing" ? "pulse-dot 1.2s infinite" : "none" }} />
                    {ts.label}
                  </span>
                  {v.hls_ready && (
                    <span className="chip" style={{ background: "rgba(96,165,250,0.12)", color: "var(--blue)" }}>
                      HLS
                    </span>
                  )}
                </div>
              </div>

              {/* أزرار */}
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
                <button
                  className="btn btn-outline btn-icon"
                  onClick={() => setAnalyticsId(v.id)}
                  title={t("dashboard.analytics_title")}
                  aria-label={t("dashboard.analytics_title")}
                >
                  <BarChart3 size={15} />
                </button>
                <button
                  className="btn btn-outline btn-icon"
                  onClick={() => copyShare(v)}
                  title={t("dashboard.copy_link_title")}
                  aria-label={t("dashboard.copy_link_title")}
                >
                  {copied === v.id ? <Check size={15} color="var(--green)" /> : <Link2 size={15} />}
                </button>
                <button
                  className="btn btn-danger btn-icon"
                  onClick={() => setDeleteTarget(v)}
                  title={t("dashboard.confirm_delete")}
                  aria-label={t("dashboard.confirm_delete")}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* نافذة تأكيد الحذف */}
      <ConfirmDialog
        open={!!deleteTarget}
        title={t("dashboard.confirm_delete")}
        description={deleteTarget?.title}
        confirmLabel={t("dashboard.confirm_delete_btn", "حذف")}
        cancelLabel={t("dashboard.cancel_btn", "إلغاء")}
        danger
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* مودال التحليلات */}
      {analyticsId && (
        <Analytics videoId={analyticsId} onClose={() => setAnalyticsId(null)} />
      )}
    </div>
  );
}
