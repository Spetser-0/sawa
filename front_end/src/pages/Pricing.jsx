/**
 * صفحة الأسعار والاشتراكات
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useTranslation } from "react-i18next";
import { paymentsAPI } from "../api/client";
import { useToast } from "../components/ui/Toast";
import { Check, AlertCircle } from "lucide-react";

export default function Pricing() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(null);
  const [error,   setError]   = useState("");
  const { user }              = useAuth();
  const navigate              = useNavigate();
  const toast                 = useToast();

  const PLANS = [
    {
      id:"free", name:t("pricing.free_name"), price:0, color:"#555",
      features:[t("pricing.free_features.0"), t("pricing.free_features.1"), t("pricing.free_features.2"), t("pricing.free_features.3")],
      cta:t("pricing.free_cta"), disabled:true,
    },
    {
      id:"pro", name:t("pricing.pro_name"), price:7, color:"#34D399",
      features:[t("pricing.pro_features.0"), t("pricing.pro_features.1"), t("pricing.pro_features.2"), t("pricing.pro_features.3"), t("pricing.pro_features.4")],
      cta:t("pricing.pro_cta"), disabled:false, popular:true,
    },
    {
      id:"team", name:t("pricing.team_name"), price:20, color:"#818CF8",
      features:[t("pricing.team_features.0"), t("pricing.team_features.1"), t("pricing.team_features.2"), t("pricing.team_features.3"), t("pricing.team_features.4")],
      cta:t("pricing.team_cta"), disabled:false,
    },
  ];

  const handleSubscribe = async (planId) => {
    if (!user) { navigate("/auth"); return; }
    setLoading(planId);
    setError("");

    try {
      const data = await paymentsAPI.create(planId);

      if (data.mode === "development") {
        // وضع التطوير — فعّل تجريبياً
        await paymentsAPI.demo(planId);
        toast.success(t("pricing.demo_activated", { plan: planId }));
        navigate("/dashboard");
      } else {
        // وجّه المستخدم لبوابة الدفع
        window.location.href = data.payment_url;
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(null);
    }
  };

  return (
    <div style={{ maxWidth:900, margin:"0 auto", padding:"40px 20px" }}>
      <div style={{ textAlign:"center", marginBottom:48 }}>
        <h1 style={{ fontSize:28, fontWeight:900, marginBottom:8 }}>{t("pricing.title")}</h1>
        <p style={{ color:"var(--text-muted)" }}>
          {t("pricing.subtitle")}
        </p>
        <div style={{ display:"inline-flex", gap:8, background:"var(--bg-card)", border:"1px solid var(--border)", borderRadius:12, padding:8, marginTop:16 }}>
          {["Visa","Mastercard","USDT","BTC"].map(m => (
            <span key={m} style={{ fontSize:12, color:"var(--text-muted)", background:"var(--bg)", borderRadius:6, padding:"4px 10px" }}>{m}</span>
          ))}
        </div>
      </div>

      {/* بطاقات الخطط */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(240px,1fr))", gap:16, marginBottom:24 }}>
        {PLANS.map(p => (
          <div key={p.id} style={{
            background:"var(--bg-card)",
            border:`2px solid ${p.popular ? p.color+"66" : "var(--border)"}`,
            borderRadius:16, padding:24, position:"relative",
          }}>
            {p.popular && (
              <div style={{ position:"absolute", top:-12, right:20, background:p.color, color:"#000", borderRadius:20, padding:"3px 14px", fontSize:11, fontWeight:800 }}>
                {t("pricing.popular_badge")}
              </div>
            )}
            <div style={{ fontSize:16, fontWeight:700, color:p.color, marginBottom:8 }}>{p.name}</div>
            <div style={{ marginBottom:20 }}>
              <span style={{ fontSize:34, fontWeight:900 }}>${p.price}</span>
              {p.price > 0 && <span style={{ fontSize:13, color:"var(--text-muted)" }}>{t("pricing.per_month")}</span>}
            </div>
            {p.features.map(f => (
              <div key={f} style={{ display:"flex", gap:8, marginBottom:8, alignItems:"flex-start" }}>
                <Check size={15} color={p.color} strokeWidth={3} style={{ flexShrink:0, marginTop:2 }} />
                <span style={{ fontSize:13 }}>{f}</span>
              </div>
            ))}
            <button
              disabled={p.disabled || loading === p.id || user?.plan === p.id}
              onClick={() => handleSubscribe(p.id)}
              style={{
                width:"100%", marginTop:20, padding:"11px",
                background: user?.plan === p.id ? "#34D39930" : p.disabled ? "#1a1a2e" : p.color,
                color: user?.plan === p.id ? "#34D399" : p.disabled ? "#555" : "#000",
                border:`1px solid ${user?.plan === p.id ? "#34D39966" : "transparent"}`,
                borderRadius:10, fontWeight:700, cursor:p.disabled?"default":"pointer",
                fontFamily:"inherit", fontSize:14, transition:"all 0.2s",
              }}
            >
              {loading === p.id ? t("pricing.loading") :
               user?.plan === p.id ? t("pricing.current_plan") : p.cta}
            </button>
          </div>
        ))}
      </div>

      {error && (
        <div style={{ padding:"12px 16px", background:"#F8717115", border:"1px solid #F8717133", borderRadius:10, color:"var(--red)", fontSize:13, display:"flex", alignItems:"center", justifyContent:"center", gap:8 }}>
          <AlertCircle size={15} style={{ flexShrink:0 }} />
          {error}
        </div>
      )}

      {/* معلومات الدفع */}
      <div style={{ background:"var(--bg-card)", border:"1px solid var(--border)", borderRadius:14, padding:20, marginTop:16 }}>
        <div style={{ fontSize:13, color:"var(--text-muted)", marginBottom:12, fontWeight:700 }}>{t("pricing.payment_title")}</div>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:12 }}>
          {[
            { step:"1", text:t("pricing.payment_step1") },
            { step:"2", text:t("pricing.payment_step2") },
            { step:"3", text:t("pricing.payment_step3") },
          ].map(s => (
            <div key={s.step} style={{ textAlign:"center" }}>
              <div style={{ width:32, height:32, borderRadius:"50%", background:"#34D39920", border:"1px solid #34D39944", margin:"0 auto 8px", display:"flex", alignItems:"center", justifyContent:"center", fontSize:14, fontWeight:800, color:"#34D399" }}>{s.step}</div>
              <div style={{ fontSize:12, color:"var(--text-muted)", lineHeight:1.5 }}>{s.text}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop:14, padding:"10px 14px", background:"#FCD34D10", border:"1px solid #FCD34D22", borderRadius:8, fontSize:12, color:"#FCD34D" }}>
          {t("pricing.payment_fee_note")}
        </div>
      </div>
    </div>
  );
}
