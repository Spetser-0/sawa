/**
 * مكوّن التحليلات — Feature 5
 * عرض إحصائيات الفيديو: مشاهدات، دول، مخطط احتفاظ
 */
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { analyticsAPI } from "../api/client";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell,
} from "recharts";
import { X, Eye, Users, Clock, TrendingUp, Globe, AlertTriangle, Inbox } from "lucide-react";

const COUNTRY_NAMES = {
  SA: "السعودية", AE: "الإمارات", EG: "مصر", KW: "الكويت", QA: "قطر",
  BH: "البحرين", OM: "عُمان", JO: "الأردن", LB: "لبنان", IQ: "العراق",
  SY: "سوريا", MA: "المغرب", TN: "تونس", DZ: "الجزائر", LY: "ليبيا",
  YE: "اليمن", PS: "فلسطين", SD: "السودان", US: "أمريكا", GB: "بريطانيا",
  DE: "ألمانيا", FR: "فرنسا", TR: "تركيا", local: "محلي",
};

function fmtDur(sec, t) {
  if (!sec) return t("analytics.zero_seconds");
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  if (m > 0) return `${m}${t("analytics.minute_short")} ${s}${t("analytics.second_short")}`;
  return `${s}${t("analytics.second_short")}`;
}

function MetricCard({ icon, label, value, color }) {
  // icon أصبح عنصر React (أيقونة SVG)
  return (
    <div style={{
      background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 12,
      padding: "16px 20px", display: "flex", flexDirection: "column", gap: 6,
      borderTop: `3px solid ${color}`,
    }}>
      <div style={{ display: "flex" }}>{icon}</div>
      <div style={{ fontSize: 24, fontWeight: 800, color }}>{value}</div>
      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{label}</div>
    </div>
  );
}

export default function Analytics({ videoId, onClose }) {
  const { t } = useTranslation();
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState("");

  useEffect(() => {
    analyticsAPI.get(videoId)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [videoId]);

  const fmtRetention = (data?.retention_graph || []).map(p => ({
    second: p.second,
    label: fmtDur(p.second, t),
    viewers: p.viewers,
  }));

  const fmtCountries = (data?.countries || []).slice(0, 8).map(c => ({
    ...c,
    name: t("analytics.countries." + c.country, COUNTRY_NAMES[c.country] || c.country),
  }));

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      backdropFilter: "blur(8px)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: 20,
    }} onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "var(--bg-card)", border: "1px solid var(--border)",
          borderRadius: 20, padding: 28, width: "100%", maxWidth: 780,
          maxHeight: "90vh", overflowY: "auto",
          animation: "fadeInScale 0.25s ease",
        }}
      >
        {/* رأس */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <div>
            <h2 style={{ fontSize: 20, fontWeight: 800, marginBottom: 4 }}>{t("analytics.title")}</h2>
            <p style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("analytics.subtitle")}</p>
          </div>
          <button onClick={onClose} style={{
            background: "none", border: "none", cursor: "pointer",
            color: "var(--text-muted)", fontSize: 22, lineHeight: 1,
          }} aria-label="close"><X size={20} /></button>
        </div>

        {loading && (
          <div style={{ textAlign: "center", padding: "60px 0" }}>
            <div className="spin" style={{ width: 36, height: 36, border: "3px solid var(--border)", borderTopColor: "var(--green)", borderRadius: "50%", margin: "0 auto 12px" }} />
            <div style={{ color: "var(--text-muted)", fontSize: 13 }}>{t("analytics.loading")}</div>
          </div>
        )}

        {error && (
          <div style={{ textAlign: "center", padding: "40px 0", color: "var(--red)" }}>
            <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
              <AlertTriangle size={34} />
            </div>
            <div>{error}</div>
          </div>
        )}

        {data && !loading && (
          <>
            {/* بطاقات الأرقام */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 28 }}>
              <MetricCard icon={<Eye size={20} color="#34D399" />} label={t("analytics.total_views")} value={data.total_views.toLocaleString("ar")} color="#34D399" />
              <MetricCard icon={<Users size={20} color="#818CF8" />} label={t("analytics.unique_viewers")} value={data.unique_viewers.toLocaleString("ar")} color="#818CF8" />
              <MetricCard icon={<Clock size={20} color="#F59E0B" />} label={t("analytics.avg_watch_duration")} value={fmtDur(data.avg_watch_duration, t)} color="#F59E0B" />
            </div>

            {/* مخطط الاحتفاظ */}
            {fmtRetention.length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: "var(--text-muted)" }}>
                  <TrendingUp size={14} style={{ verticalAlign: "middle", marginInlineEnd: 6 }} />{t("analytics.retention_curve")}
                </h3>
                <div style={{ background: "var(--bg)", borderRadius: 12, padding: "16px 8px", border: "1px solid var(--border)" }}>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={fmtRetention}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e1e30" />
                      <XAxis
                        dataKey="label"
                        tick={{ fill: "#6b7280", fontSize: 11 }}
                        axisLine={{ stroke: "#1e1e30" }}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fill: "#6b7280", fontSize: 11 }}
                        axisLine={{ stroke: "#1e1e30" }}
                        tickLine={false}
                        width={30}
                      />
                      <Tooltip
                        contentStyle={{ background: "#0d0d1a", border: "1px solid #1e1e30", borderRadius: 8, fontSize: 12 }}
                        labelStyle={{ color: "#34D399" }}
                        itemStyle={{ color: "#e0e0ec" }}
                        formatter={(val) => [val, t("analytics.viewers_tooltip")]}
                      />
                      <Line
                        type="monotone" dataKey="viewers"
                        stroke="#34D399" strokeWidth={2}
                        dot={false} activeDot={{ r: 4, fill: "#34D399" }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* توزيع الدول */}
            {fmtCountries.length > 0 && (
              <div>
                <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: "var(--text-muted)" }}>
                  <Globe size={14} style={{ verticalAlign: "middle", marginInlineEnd: 6 }} />{t("analytics.country_distribution")}
                </h3>
                <div style={{ background: "var(--bg)", borderRadius: 12, padding: "16px 8px", border: "1px solid var(--border)" }}>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={fmtCountries} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e1e30" horizontal={false} />
                      <XAxis type="number" tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis
                        type="category" dataKey="name" width={70}
                        tick={{ fill: "#e0e0ec", fontSize: 12 }} axisLine={false} tickLine={false}
                      />
                      <Tooltip
                        contentStyle={{ background: "#0d0d1a", border: "1px solid #1e1e30", borderRadius: 8, fontSize: 12 }}
                        formatter={(val) => [val, t("analytics.view_tooltip")]}
                      />
                      <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                        {fmtCountries.map((_, i) => (
                          <Cell key={i} fill={["#34D399","#818CF8","#F59E0B","#F472B6","#60A5FA","#C084FC","#34D399","#818CF8"][i % 8]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {data.total_views === 0 && (
              <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
                <div style={{ display: "flex", justifyContent: "center", marginBottom: 12, opacity: 0.5 }}>
                  <Inbox size={36} />
                </div>
                <div>{t("analytics.no_data")}</div>
                <div style={{ fontSize: 12, marginTop: 8 }}>{t("analytics.share_to_start")}</div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
