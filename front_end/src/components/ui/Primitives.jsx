/**
 * مكونات UI أساسية مشتركة — Spinner / Skeleton / EmptyState / ConfirmDialog
 */
import { useEffect } from "react";

/* ── مؤشر تحميل ─────────────────────────────────────── */
export function Spinner({ size = 32, label }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
      <div className="spinner" style={{ width: size, height: size }} role="status" aria-label={label || "loading"} />
      {label && <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{label}</span>}
    </div>
  );
}

/* ── شاشة تحميل صفحة كاملة ──────────────────────────── */
export function PageLoader({ label }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "50vh" }}>
      <Spinner label={label} />
    </div>
  );
}

/* ── Skeleton لبطاقة تسجيل ──────────────────────────── */
export function VideoCardSkeleton() {
  return (
    <div className="card" style={{ display: "flex", gap: 14, alignItems: "center" }}>
      <div className="skeleton" style={{ width: 96, height: 56, flexShrink: 0 }} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="skeleton" style={{ height: 14, width: "55%" }} />
        <div className="skeleton" style={{ height: 10, width: "35%" }} />
      </div>
      <div className="skeleton" style={{ width: 90, height: 32, flexShrink: 0 }} />
    </div>
  );
}

/* ── حالة فارغة ─────────────────────────────────────── */
export function EmptyState({ icon, title, description, action }) {
  return (
    <div className="empty-state fade-in">
      <div style={{
        width: 72, height: 72, borderRadius: 20, margin: "0 auto 20px",
        background: "rgba(52, 211, 153, 0.08)", border: "1px solid rgba(52, 211, 153, 0.2)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {icon}
      </div>
      <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>{title}</h3>
      {description && (
        <p style={{ color: "var(--text-muted)", marginBottom: action ? 24 : 0, fontSize: 14, maxWidth: 380, marginInline: "auto" }}>
          {description}
        </p>
      )}
      {action}
    </div>
  );
}

/* ── نافذة تأكيد ────────────────────────────────────── */
export function ConfirmDialog({ open, title, description, confirmLabel, cancelLabel, danger = false, loading = false, onConfirm, onCancel }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onCancel?.(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      onClick={onCancel}
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(0, 0, 0, 0.65)", backdropFilter: "blur(6px)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
      }}
    >
      <div
        className="fade-in-scale"
        onClick={(e) => e.stopPropagation()}
        role="dialog" aria-modal="true"
        style={{
          background: "var(--bg-elevated)", border: "1px solid var(--border)",
          borderRadius: "var(--radius)", padding: 28, width: "100%", maxWidth: 400,
          boxShadow: "var(--shadow-lg)",
        }}
      >
        <h3 style={{ fontSize: 17, fontWeight: 800, marginBottom: 8 }}>{title}</h3>
        {description && <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 24, lineHeight: 1.7 }}>{description}</p>}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button className="btn btn-outline" onClick={onCancel} disabled={loading}>{cancelLabel}</button>
          <button
            className={danger ? "btn btn-danger" : "btn btn-primary"}
            style={danger ? { background: "rgba(248,113,113,0.12)" } : undefined}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? <span className="spinner spinner-sm" /> : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
