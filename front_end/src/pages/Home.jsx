/**
 * سوى — Landing Page
 * تصميم عصري: 3D تفاعلي، canvas، تأثيرات بصرية
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Mic, BrainCircuit, Search, Globe, FileText, Lock,
  Rocket, Check, X, Video, Languages, Sparkles, File,
} from "lucide-react";

/* ─────────────────────────────────────────────────────
   Hook: تتبع موضع الماوس للـ 3D tilt
───────────────────────────────────────────────────── */
function useTilt(ref, strength = 15) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onMove = (e) => {
      const r = el.getBoundingClientRect();
      const x = ((e.clientX - r.left) / r.width  - 0.5) * strength;
      const y = ((e.clientY - r.top)  / r.height - 0.5) * strength;
      el.style.transform = `perspective(800px) rotateY(${x}deg) rotateX(${-y}deg) scale3d(1.02,1.02,1.02)`;
    };
    const onLeave = () => { el.style.transform = "perspective(800px) rotateY(0deg) rotateX(0deg) scale3d(1,1,1)"; };
    el.addEventListener("mousemove", onMove);
    el.addEventListener("mouseleave", onLeave);
    return () => { el.removeEventListener("mousemove", onMove); el.removeEventListener("mouseleave", onLeave); };
  }, [ref, strength]);
}

/* ─────────────────────────────────────────────────────
   Hook: Scroll reveal
───────────────────────────────────────────────────── */
function useReveal() {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setVisible(true); obs.disconnect(); } }, { threshold: 0.15 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);
  return [ref, visible];
}

/* ─────────────────────────────────────────────────────
   Hook: Counting animation
───────────────────────────────────────────────────── */
function useCount(target, duration = 1800, start = false) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!start) return;
    let startTime = null;
    const step = (ts) => {
      if (!startTime) startTime = ts;
      const p = Math.min((ts - startTime) / duration, 1);
      setVal(Math.floor(p * target));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target, duration, start]);
  return val;
}

/* ─────────────────────────────────────────────────────
   Component: خلفية mesh gradient متحركة
───────────────────────────────────────────────────── */
function MeshBackground() {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx    = canvas.getContext("2d");
    let   raf;
    let   t = 0;

    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
    resize();
    window.addEventListener("resize", resize);

    const blobs = [
      { x: 0.2, y: 0.2, r: 0.35, c: [52, 211, 153, 0.12] },
      { x: 0.8, y: 0.3, r: 0.3,  c: [129, 140, 248, 0.10] },
      { x: 0.5, y: 0.8, r: 0.4,  c: [52, 211, 153, 0.08] },
      { x: 0.1, y: 0.7, r: 0.25, c: [192, 132, 252, 0.08] },
    ];

    const draw = () => {
      t += 0.003;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      blobs.forEach((b, i) => {
        const ox = Math.sin(t + i * 1.3) * 0.06;
        const oy = Math.cos(t + i * 0.9) * 0.06;
        const cx = (b.x + ox) * canvas.width;
        const cy = (b.y + oy) * canvas.height;
        const r  = b.r * Math.min(canvas.width, canvas.height);

        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
        g.addColorStop(0, `rgba(${b.c[0]},${b.c[1]},${b.c[2]},${b.c[3]})`);
        g.addColorStop(1, `rgba(${b.c[0]},${b.c[1]},${b.c[2]},0)`);
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fill();
      });

      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, []);

  return <canvas ref={canvasRef} style={{ position:"fixed", inset:0, pointerEvents:"none", zIndex:0 }} />;
}

/* ─────────────────────────────────────────────────────
   Component: موجة صوت متحركة
───────────────────────────────────────────────────── */
function AudioWave({ color = "#34D399", height = 60, bars = 40 }) {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx    = canvas.getContext("2d");
    let   raf, t = 0;
    const W = canvas.width, H = canvas.height;

    const draw = () => {
      t += 0.04;
      ctx.clearRect(0, 0, W, H);
      const barW = W / bars;

      for (let i = 0; i < bars; i++) {
        const phase  = i / bars * Math.PI * 4 + t;
        const amp    = (Math.sin(phase) * 0.5 + 0.5) * 0.8 + 0.1;
        const bH     = amp * H * 0.85;
        const x      = i * barW + barW * 0.15;
        const alpha  = 0.4 + amp * 0.6;

        ctx.fillStyle = color + Math.round(alpha * 255).toString(16).padStart(2,"0");
        ctx.beginPath();
        const r = barW * 0.35;
        ctx.roundRect(x, (H - bH) / 2, barW * 0.7, bH, r);
        ctx.fill();
      }
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [color, bars, height]);

  return <canvas ref={canvasRef} width={320} height={height} style={{ display:"block" }} />;
}

/* ─────────────────────────────────────────────────────
   Component: بطاقة 3D تتبع الماوس
───────────────────────────────────────────────────── */
function Card3D({ children, style = {} }) {
  const ref = useRef(null);
  useTilt(ref, 12);
  return (
    <div ref={ref} style={{
      transition: "transform 0.1s ease",
      transformStyle: "preserve-3d",
      willChange: "transform",
      ...style,
    }}>
      {children}
    </div>
  );
}

/* ─────────────────────────────────────────────────────
   Component: شاشة موك-أب المنتج
───────────────────────────────────────────────────── */
function ProductMockup() {
  const ref = useRef(null);
  useTilt(ref, 8);
  const [activeWord, setActiveWord] = useState(3);

  useEffect(() => {
    const id = setInterval(() => setActiveWord(w => (w + 1) % 6), 800);
    return () => clearInterval(id);
  }, []);

  const words = [
    { t: "00:01", text: "السلام" },
    { t: "00:02", text: "عليكم" },
    { t: "00:03", text: "ورحمة" },
    { t: "00:04", text: "الله" },
    { t: "00:05", text: "وبركاته" },
    { t: "00:06", text: "جميعاً" },
  ];

  return (
    <div ref={ref} style={{
      transition: "transform 0.12s ease",
      transformStyle: "preserve-3d",
      background: "linear-gradient(135deg, #0d0d1a, #13132a)",
      border: "1px solid #34D39930",
      borderRadius: 20,
      padding: 20,
      boxShadow: "0 40px 80px #00000060, 0 0 0 1px #34D39920, inset 0 1px 0 #ffffff08",
      maxWidth: 460,
      width: "100%",
    }}>
      {/* شريط العنوان */}
      <div style={{ display:"flex", gap:6, marginBottom:14 }}>
        {["#F87171","#FCD34D","#34D399"].map(c => (
          <div key={c} style={{ width:10, height:10, borderRadius:"50%", background:c, opacity:0.8 }} />
        ))}
        <div style={{ flex:1, background:"#ffffff0a", borderRadius:6, height:10, margin:"0 8px" }} />
      </div>

      {/* مشغّل مصغّر */}
      <div style={{ background:"#000", borderRadius:12, height:140, marginBottom:14, display:"flex", alignItems:"center", justifyContent:"center", overflow:"hidden", position:"relative" }}>
        <div style={{ position:"absolute", inset:0, background:"linear-gradient(135deg, #34D39915, #818CF815)" }} />
        <AudioWave color="#34D399" height={80} bars={30} />
        <div style={{ position:"absolute", bottom:8, left:12, fontSize:12, color:"#34D399", fontFamily:"monospace", background:"#00000080", borderRadius:6, padding:"2px 8px" }}>
          ● 00:06
        </div>
      </div>

      {/* النص المفرَّغ */}
      <div style={{ display:"flex", flexWrap:"wrap", gap:6, marginBottom:12 }}>
        {words.map((w, i) => (
          <div key={i} style={{
            padding: "5px 10px", borderRadius: 8, fontSize: 14, fontWeight: 600,
            background: i === activeWord ? "#34D399" : "#ffffff0a",
            color:      i === activeWord ? "#000" : "#ccc",
            border:     `1px solid ${i === activeWord ? "#34D399" : "#ffffff10"}`,
            transition: "all 0.3s",
            cursor:     "pointer",
          }}>
            {w.text}
          </div>
        ))}
      </div>

      {/* شريط الأدوات */}
      <div style={{ display:"flex", gap:6 }}>
        {[
          { icon: <Languages size={12} />, label: "ترجمة" },
          { icon: <Sparkles size={12} />, label: "تلخيص" },
          { icon: <File size={12} />, label: ".docx" },
        ].map((btn) => (
          <div key={btn.label} style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", gap:5, padding:"6px", background:"#ffffff08", border:"1px solid #ffffff10", borderRadius:8, fontSize:11, color:"#888" }}>
            {btn.icon}
            {btn.label}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────
   Component: بطاقة ميزة
───────────────────────────────────────────────────── */
function FeatureCard({ icon, title, desc, color, delay = 0 }) {
  const [ref, vis] = useReveal();
  const [hovered, setHovered] = useState(false);
  const cardRef = useRef(null);
  useTilt(cardRef, 10);

  return (
    <div ref={ref} style={{
      opacity: vis ? 1 : 0, transform: vis ? "translateY(0)" : "translateY(30px)",
      transition: `all 0.6s ease ${delay}ms`,
    }}>
      <div ref={cardRef} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
        style={{
          background: hovered ? `${color}08` : "#0d0d1a",
          border: `1px solid ${hovered ? color + "44" : "#1e1e30"}`,
          borderRadius: 16, padding: "24px 20px",
          transition: "all 0.3s ease",
          cursor: "default",
          position: "relative", overflow: "hidden",
          transformStyle: "preserve-3d",
        }}
      >
        {/* ضوء خلفي عند التحويم */}
        <div style={{
          position:"absolute", top:-40, right:-40, width:120, height:120,
          borderRadius:"50%", background: color,
          filter: "blur(60px)", opacity: hovered ? 0.15 : 0,
          transition: "opacity 0.4s", pointerEvents:"none",
        }} />

        <div style={{
          width:44, height:44, borderRadius:12,
          background: `${color}20`, border:`1px solid ${color}33`,
          display:"flex", alignItems:"center", justifyContent:"center",
          fontSize:22, marginBottom:14,
          transition: "transform 0.3s",
          transform: hovered ? "scale(1.1) rotate(-5deg)" : "scale(1)",
        }}>
          {icon}
        </div>
        <div style={{ fontWeight:800, fontSize:15, marginBottom:8, color:"#fff" }}>{title}</div>
        <div style={{ fontSize:13, color:"#888", lineHeight:1.7 }}>{desc}</div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────
   Component: إحصائية متحركة
───────────────────────────────────────────────────── */
function Stat({ value, suffix, label, color, delay }) {
  const [ref, vis] = useReveal();
  const count = useCount(value, 1600, vis);
  return (
    <div ref={ref} style={{
      textAlign:"center",
      opacity: vis ? 1 : 0, transform: vis ? "translateY(0)" : "translateY(20px)",
      transition: `all 0.6s ease ${delay}ms`,
    }}>
      <div style={{ fontSize:42, fontWeight:900, color, lineHeight:1, marginBottom:6 }}>
        {count}{suffix}
      </div>
      <div style={{ fontSize:13, color:"#666" }}>{label}</div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────
   Component: مقارنة بـ Loom
───────────────────────────────────────────────────── */
function CompareRow({ feature, sawa, loom, delay }) {
  const [ref, vis] = useReveal();
  return (
    <tr ref={ref} style={{
      opacity: vis ? 1 : 0, transition: `opacity 0.5s ease ${delay}ms`,
      borderBottom: "1px solid #10101e",
    }}>
      <td style={{ padding:"12px 16px", fontSize:13, color:"#ccc" }}>{feature}</td>
      <td style={{ textAlign:"center", padding:"12px" }}>
        {sawa
          ? <Check size={18} color="#34D399" style={{ filter:"drop-shadow(0 0 6px #34D399)" }} strokeWidth={3} />
          : <X size={18} color="#F87171" strokeWidth={3} />}
      </td>
      <td style={{ textAlign:"center", padding:"12px" }}>
        {loom
          ? <Check size={18} color="#666" strokeWidth={3} />
          : <X size={18} color="#444" strokeWidth={3} />}
      </td>
    </tr>
  );
}

/* ─────────────────────────────────────────────────────
   Component: بطاقة خطة أسعار (مكوّن مستقل — احتراماً لقواعد Hooks)
───────────────────────────────────────────────── */
function PricingCard({ plan, index, startFreeLabel, subscribeLabel, popularLabel }) {
  const [ref, vis] = useReveal();
  const [hov, setHov] = useState(false);
  const p = plan;

  return (
    <div ref={ref} style={{
      opacity: vis ? 1 : 0, transform: vis ? "translateY(0)" : "translateY(30px)",
      transition: `all 0.6s ease ${index * 120}ms`,
    }}>
      <Card3D style={{ height:"100%" }}>
        <div
          onMouseEnter={() => setHov(true)}
          onMouseLeave={() => setHov(false)}
          style={{
            background: p.popular ? `linear-gradient(135deg, ${p.color}12, #0d0d1a)` : "#0d0d1a",
            border: `${p.popular ? 2 : 1}px solid ${hov || p.popular ? p.color + "55" : "#1e1e30"}`,
            borderRadius:16, padding:24, position:"relative",
            transition:"all 0.3s", height:"100%", boxSizing:"border-box",
            boxShadow: p.popular ? `0 0 40px ${p.color}15` : "none",
          }}
        >
          {p.popular && (
            <div style={{
              position:"absolute", top:-12, right:20,
              background:`linear-gradient(90deg, #34D399, #818CF8)`,
              color:"#000", borderRadius:20, padding:"3px 14px",
              fontSize:11, fontWeight:900,
            }}>{popularLabel}</div>
          )}
          <div style={{ color:p.color, fontWeight:800, fontSize:15, marginBottom:10 }}>{p.name}</div>
          <div style={{ marginBottom:20 }}>
            <span style={{ fontSize:36, fontWeight:900, color:"#fff" }}>${p.price}</span>
            <span style={{ fontSize:13, color:"#666" }}>{p.period}</span>
          </div>
          {p.features.map(f => (
            <div key={f} style={{ display:"flex", gap:8, marginBottom:8, alignItems:"center" }}>
              <Check size={13} color={p.color} strokeWidth={3} style={{ flexShrink:0 }} />
              <span style={{ fontSize:13, color:"#bbb" }}>{f}</span>
            </div>
          ))}
          <Link to={p.price > 0 ? "/pricing" : "/auth"}
            style={{
              display:"block", width:"100%", textAlign:"center",
              padding:"11px", marginTop:20, borderRadius:10,
              background: p.popular ? p.color : "transparent",
              color: p.popular ? "#000" : p.color,
              border:`1px solid ${p.color}66`,
              fontWeight:800, fontSize:14, textDecoration:"none",
              transition:"all 0.2s", boxSizing:"border-box",
              boxShadow: p.popular ? `0 0 20px ${p.color}30` : "none",
            }}
          >
            {p.price === 0 ? startFreeLabel : subscribeLabel}
          </Link>
        </div>
      </Card3D>
    </div>
  );
}

/* ─────────────────────────────────────────────────
   Main: Home Page
───────────────────────────────────────────────────── */
export default function Home() {
  const { t } = useTranslation();
  const [mousePos, setMousePos] = useState({ x: 0.5, y: 0.5 });

  const FEATURES = [
    { icon:<Mic size={22} color="#34D399" />, title: t("home.feature_recording"), desc: t("home.feature_recording_desc"), color:"#34D399" },
    { icon:<BrainCircuit size={22} color="#818CF8" />, title: t("home.feature_transcription"), desc: t("home.feature_transcription_desc"), color:"#818CF8" },
    { icon:<Search size={22} color="#F59E0B" />, title: t("home.feature_search"), desc: t("home.feature_search_desc"), color:"#F59E0B" },
    { icon:<Globe size={22} color="#F472B6" />, title: t("home.feature_ai"), desc: t("home.feature_ai_desc"), color:"#F472B6" },
    { icon:<FileText size={22} color="#60A5FA" />, title: t("home.feature_export"), desc: t("home.feature_export_desc"), color:"#60A5FA" },
    { icon:<Lock size={22} color="#C084FC" />, title: t("home.feature_privacy"), desc: t("home.feature_privacy_desc"), color:"#C084FC" },
  ];
  const heroRef = useRef(null);
  const [heroRef2, heroVis] = useReveal();

  const handleMouseMove = useCallback((e) => {
    const r = heroRef.current?.getBoundingClientRect();
    if (!r) return;
    setMousePos({ x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height });
  }, []);

  return (
    <div style={{ position:"relative", overflow:"hidden" }}>
      <MeshBackground />

      {/* ════════════════════════════════
          HERO
      ════════════════════════════════ */}
      <section ref={heroRef} onMouseMove={handleMouseMove}
        style={{ minHeight:"90vh", display:"flex", alignItems:"center", justifyContent:"center", padding:"80px 24px 60px", position:"relative", zIndex:1 }}>

        {/* Spotlight effect */}
        <div style={{
          position:"absolute", pointerEvents:"none",
          width:600, height:600, borderRadius:"50%",
          background: "radial-gradient(circle, #34D39910 0%, transparent 70%)",
          left: `calc(${mousePos.x * 100}% - 300px)`,
          top:  `calc(${mousePos.y * 100}% - 300px)`,
          transition:"left 0.1s, top 0.1s",
        }} />

        <div className="hero-grid" style={{ maxWidth:1100, width:"100%", display:"grid", gridTemplateColumns:"1fr 1fr", gap:60, alignItems:"center" }}>

          {/* نص الهيرو */}
          <div>
            <div style={{
              display:"inline-flex", gap:8, alignItems:"center",
              background:"#34D39915", border:"1px solid #34D39930",
              borderRadius:20, padding:"6px 14px", marginBottom:24, fontSize:12, color:"#34D399",
            }}>
              <span style={{ width:7, height:7, borderRadius:"50%", background:"#34D399", animation:"pulse-ring 1.5s infinite" }} />
              {t("home.badge")}
            </div>

            <h1 style={{
              fontSize:"clamp(36px, 5vw, 58px)", fontWeight:900, lineHeight:1.15,
              marginBottom:20, letterSpacing:"-0.5px",
            }}>
              <span style={{ color:"#fff" }}>{t("home.hero_title_1")}</span>
              <br />
              <span style={{
                background:"linear-gradient(90deg, #34D399, #818CF8)",
                WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent",
              }}>
                {t("home.hero_title_2")}
              </span>
              <br />
              <span style={{ color:"#fff" }}>{t("home.hero_title_3")}</span>
            </h1>

            <p style={{ fontSize:16, color:"#888", lineHeight:1.8, marginBottom:32, maxWidth:440 }}>
              {t("home.hero_desc")}
            </p>

            {/* موجة صوت */}
            <div style={{ marginBottom:28, opacity:0.7 }}>
              <AudioWave color="#34D399" height={40} bars={50} />
            </div>

            <div style={{ display:"flex", gap:12, flexWrap:"wrap" }}>
              <Link to="/record" style={{
                display:"inline-flex", alignItems:"center", gap:8,
                background:"#34D399", color:"#000", padding:"13px 28px",
                borderRadius:12, fontWeight:800, fontSize:15, textDecoration:"none",
                boxShadow:"0 0 30px #34D39940",
                transition:"all 0.2s",
              }}
                onMouseEnter={(e)=>e.currentTarget.style.boxShadow="0 0 50px #34D39960"}
                onMouseLeave={(e)=>e.currentTarget.style.boxShadow="0 0 30px #34D39940"}
              >
                <Video size={18} />
                {t("home.cta_start")}
              </Link>
              <Link to="/auth" style={{
                display:"inline-flex", alignItems:"center", gap:8,
                background:"transparent", color:"#fff", padding:"13px 28px",
                borderRadius:12, fontWeight:700, fontSize:15, textDecoration:"none",
                border:"1px solid #ffffff20", backdropFilter:"blur(10px)",
                transition:"all 0.2s",
              }}
                onMouseEnter={(e)=>e.currentTarget.style.borderColor="#34D39966"}
                onMouseLeave={(e)=>e.currentTarget.style.borderColor="#ffffff20"}
              >
                {t("home.cta_register")}
              </Link>
            </div>

            <p style={{ fontSize:12, color:"#555", marginTop:14 }}>
              {t("home.hero_footer")}
            </p>
          </div>

          {/* موك-أب المنتج */}
          <div style={{ display:"flex", justifyContent:"center" }}>
            <ProductMockup />
          </div>
        </div>
      </section>

      {/* ════════════════════════════════
          STATS
      ════════════════════════════════ */}
      <section style={{ padding:"40px 24px 60px", position:"relative", zIndex:1 }}>
        <div style={{ maxWidth:800, margin:"0 auto" }}>
          <div style={{
            display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:0,
            background:"#0d0d1a", border:"1px solid #1e1e30", borderRadius:16,
            overflow:"hidden",
          }}>
            {[
              { value:400, suffix:"M+", label:t("home.stat_users_label"), color:"#34D399", delay:0 },
              { value:99,  suffix:"%",  label:t("home.stat_accuracy_label"), color:"#818CF8", delay:150 },
              { value:7,   suffix:"$",  label:t("home.stat_price_label"),   color:"#F59E0B", delay:300 },
            ].map((s, i) => (
              <div key={i} style={{ padding:"28px 20px", borderRight: i < 2 ? "1px solid #1e1e30" : "none" }}>
                <Stat {...s} />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════
          FEATURES
      ════════════════════════════════ */}
      <section style={{ padding:"60px 24px", position:"relative", zIndex:1 }}>
        <div style={{ maxWidth:1100, margin:"0 auto" }}>
          <div style={{ textAlign:"center", marginBottom:48 }}>
            <div style={{ fontSize:12, color:"#818CF8", letterSpacing:3, marginBottom:12, textTransform:"uppercase" }}>
              {t("home.stats_title")}
            </div>
            <h2 style={{ fontSize:"clamp(26px, 4vw, 38px)", fontWeight:900, marginBottom:12 }}>
              {t("home.stats_subtitle")}
            </h2>
            <p style={{ color:"#666", fontSize:15, maxWidth:500, margin:"0 auto" }}>
              {t("home.stats_desc")}
            </p>
          </div>

          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(290px,1fr))", gap:14 }}>
            {FEATURES.map((f, i) => <FeatureCard key={f.title} {...f} delay={i * 80} />)}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════
          المقارنة مع Loom
      ════════════════════════════════ */}
      <section style={{ padding:"60px 24px", position:"relative", zIndex:1 }}>
        <div style={{ maxWidth:600, margin:"0 auto" }}>
          <div style={{ textAlign:"center", marginBottom:36 }}>
            <div style={{ fontSize:12, color:"#F87171", letterSpacing:3, marginBottom:12, textTransform:"uppercase" }}>
              {t("home.compare_title")}
            </div>
            <h2 style={{ fontSize:"clamp(24px, 3vw, 34px)", fontWeight:900 }}>
              {t("home.compare_subtitle")}
            </h2>
          </div>

          <Card3D>
            <div style={{ background:"#0d0d1a", border:"1px solid #1e1e30", borderRadius:16, overflow:"hidden" }}>
              <table style={{ width:"100%", borderCollapse:"collapse" }}>
                <thead>
                  <tr style={{ borderBottom:"1px solid #1e1e30" }}>
                    <th style={{ textAlign:"right", padding:"14px 16px", fontSize:12, color:"#555" }}>{t("home.compare_header_feature")}</th>
                    <th style={{ textAlign:"center", padding:"14px", fontSize:15, color:"#34D399", fontWeight:900 }}>
                      {t("home.compare_header_sawa")}
                    </th>
                    <th style={{ textAlign:"center", padding:"14px", fontSize:13, color:"#555" }}>{t("home.compare_header_loom")}</th>
                  </tr>
                </thead>
                <tbody>
                  {t("home.compare_features", { returnObjects: true }).map((f, i) => {
                    const loomValues = [false, false, false, false, false, false, true, true];
                    const sawaValues = [true, true, true, true, true, true, true, true];
                    return <CompareRow key={i} feature={f} sawa={sawaValues[i]} loom={loomValues[i]} delay={i * 60} />;
                  })}
                </tbody>
              </table>
            </div>
          </Card3D>
        </div>
      </section>

      {/* ════════════════════════════════
          الأسعار
      ════════════════════════════════ */}
      <section style={{ padding:"60px 24px 80px", position:"relative", zIndex:1 }}>
        <div style={{ maxWidth:900, margin:"0 auto" }}>
          <div style={{ textAlign:"center", marginBottom:48 }}>
            <h2 style={{ fontSize:"clamp(24px,3vw,34px)", fontWeight:900, marginBottom:8 }}>
              {t("home.pricing_title")}
            </h2>
            <p style={{ color:"#666" }}>{t("home.pricing_subtitle")}</p>
          </div>

          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(240px,1fr))", gap:14 }}>
            {[
              { name:t("pricing.free_name"),  price:0,  color:"#555",    period:"",       features:[t("home.feature_recording"), t("home.feature_search"), t("home.feature_privacy")], popular:false },
              { name:t("pricing.pro_name"),    price:7,  color:"#34D399", period:"/شهر",   features:[t("home.feature_ai"), t("home.feature_export"), t("home.feature_transcription"), t("home.feature_privacy")], popular:true },
              { name:t("pricing.team_name"),   price:20, color:"#818CF8", period:"/شهر",   features:[t("home.feature_recording"), t("home.feature_search"), t("home.feature_ai"), t("home.feature_export")], popular:false },
            ].map((p, i) => (
              <PricingCard
                key={p.name}
                plan={p}
                index={i}
                startFreeLabel={t("home.start_free")}
                subscribeLabel={t("home.subscribe_now")}
                popularLabel={t("home.popular")}
              />
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════
          CTA نهائي
      ════════════════════════════════ */}
      <section style={{ padding:"60px 24px 80px", position:"relative", zIndex:1 }}>
        <div style={{ maxWidth:600, margin:"0 auto", textAlign:"center" }}>
          <div style={{
            background:"linear-gradient(135deg, #34D39910, #818CF810)",
            border:"1px solid #34D39930", borderRadius:24, padding:"48px 32px",
            position:"relative", overflow:"hidden",
          }}>
            <div style={{ position:"absolute", top:-60, right:-60, width:200, height:200, borderRadius:"50%", background:"#34D39920", filter:"blur(60px)" }} />
            <div style={{ position:"absolute", bottom:-40, left:-40, width:160, height:160, borderRadius:"50%", background:"#818CF820", filter:"blur(50px)" }} />
            <div style={{ position:"relative" }}>
              <div style={{
                width:64, height:64, borderRadius:18, margin:"0 auto 20px",
                background:"rgba(52,211,153,0.12)", border:"1px solid rgba(52,211,153,0.3)",
                display:"flex", alignItems:"center", justifyContent:"center",
              }} className="float">
                <Rocket size={28} color="#34D399" />
              </div>
              <h2 style={{ fontSize:26, fontWeight:900, marginBottom:12 }}>
                {t("home.cta_title")}
              </h2>
              <p style={{ color:"#888", marginBottom:28, lineHeight:1.7 }}>
                {t("home.cta_desc")}
              </p>
              <Link to="/auth?mode=register" style={{
                display:"inline-flex", alignItems:"center", gap:10,
                background:"#34D399", color:"#000",
                padding:"14px 32px", borderRadius:12,
                fontWeight:900, fontSize:16, textDecoration:"none",
                boxShadow:"0 0 40px #34D39940",
              }}>
                {t("home.cta_button")}
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ borderTop:"1px solid #1e1e30", padding:"24px 20px", textAlign:"center", position:"relative", zIndex:1 }}>
        <div style={{ fontSize:22, fontWeight:900, background:"linear-gradient(90deg, #34D399, #818CF8)", WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent", marginBottom:6 }}>
          سوى
        </div>
        <div style={{ fontSize:12, color:"#444" }}>{t("home.footer_made")}</div>
      </footer>
    </div>
  );
}
