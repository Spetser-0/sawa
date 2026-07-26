import { useState, useEffect, useRef } from "react";
import { Link, NavLink, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../hooks/useAuth";
import {
  Video, Settings, LogOut, Globe, Menu, X, ChevronDown,
  LayoutGrid, Search, CreditCard,
} from "lucide-react";

export default function Navbar() {
  const { user, logout } = useAuth();
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);      // قائمة المستخدم
  const [mobileOpen, setMobileOpen] = useState(false);  // قائمة الموبايل
  const menuRef = useRef(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // إغلاق قائمة الموبايل عند تغيير المسار
  useEffect(() => { setMobileOpen(false); setMenuOpen(false); }, [location.pathname]);

  const toggleLanguage = () => {
    i18n.changeLanguage(i18n.language === "ar" ? "en" : "ar");
  };

  const handleLogout = async () => {
    setMenuOpen(false);
    try { await logout(); } finally { navigate("/"); }
  };

  const NAV_LINKS = [
    { to: "/dashboard", label: t("nav.my_recordings"), icon: <LayoutGrid size={15} /> },
    { to: "/search",    label: t("nav.search"),        icon: <Search size={15} /> },
    { to: "/pricing",   label: t("nav.pricing"),       icon: <CreditCard size={15} /> },
  ];

  return (
    <>
      <nav className={`navbar ${scrolled || mobileOpen ? "scrolled" : ""}`}>
        {/* شعار */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {user && (
            <button
              className="nav-mobile-toggle"
              aria-label="menu"
              onClick={() => setMobileOpen((v) => !v)}
            >
              {mobileOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          )}
          <Link to="/" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: 10 }}>
            <span className="gradient-text" style={{ fontSize: 22, fontWeight: 900, lineHeight: 1 }}>
              {t("app_name")}
            </span>
            <span className="chip" style={{
              color: "var(--green)", background: "rgba(52,211,153,0.08)",
              border: "1px solid rgba(52,211,153,0.2)", letterSpacing: 1, fontSize: 10,
            }}>BETA</span>
          </Link>
        </div>

        {/* روابط سطح المكتب */}
        {user && (
          <div className="nav-links-desktop">
            {NAV_LINKS.map((l) => (
              <NavLink key={l.to} to={l.to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                {l.label}
              </NavLink>
            ))}
          </div>
        )}

        {/* يمين */}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            onClick={toggleLanguage}
            className="btn btn-outline btn-sm"
            style={{ gap: 5 }}
            aria-label="language"
          >
            <Globe size={13} />
            {i18n.language === "ar" ? "EN" : "عربي"}
          </button>

          {user ? (
            <>
              <Link to="/record" className="btn btn-primary btn-sm" style={{ boxShadow: "0 0 16px var(--green-glow)" }}>
                <Video size={14} />
                {t("nav.record")}
              </Link>

              {/* أفاتار مع قائمة منسدلة */}
              <div ref={menuRef} style={{ position: "relative" }}>
                <button
                  onClick={() => setMenuOpen((v) => !v)}
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  style={{
                    display: "flex", alignItems: "center", gap: 8, padding: "4px 10px 4px 8px",
                    background: "var(--bg-card)", border: `1px solid ${menuOpen ? "rgba(52,211,153,0.4)" : "var(--border)"}`,
                    borderRadius: 10, cursor: "pointer", fontFamily: "var(--font)",
                    transition: "border-color var(--transition)", width: "auto",
                  }}
                >
                  <span style={{
                    width: 26, height: 26, borderRadius: "50%", flexShrink: 0,
                    background: "linear-gradient(135deg, var(--green), var(--purple))",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 12, fontWeight: 800, color: "#04120c",
                  }}>
                    {user.name?.[0]?.toUpperCase() || "?"}
                  </span>
                  <span className="nav-user-name" style={{ fontSize: 13, color: "var(--text)", fontWeight: 600 }}>
                    {user.name?.split(" ")[0]}
                  </span>
                  <ChevronDown size={13} color="var(--text-muted)"
                    style={{ transform: menuOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
                </button>

                {menuOpen && (
                  <div className="dropdown-menu" role="menu">
                    <div style={{ padding: "8px 12px 10px", borderBottom: "1px solid var(--border)", marginBottom: 6 }}>
                      <div style={{ fontSize: 13, fontWeight: 700 }} className="text-truncate">{user.name}</div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }} className="text-truncate">{user.email}</div>
                    </div>
                    <Link to="/settings" className="dropdown-item" onClick={() => setMenuOpen(false)} role="menuitem">
                      <Settings size={15} />
                      {t("nav.settings")}
                    </Link>
                    <button className="dropdown-item danger" onClick={handleLogout} role="menuitem">
                      <LogOut size={15} />
                      {t("nav.logout")}
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <Link to="/auth" className="btn btn-outline btn-sm">{t("nav.login")}</Link>
              <Link to="/auth?mode=register" className="btn btn-primary btn-sm" style={{ boxShadow: "0 0 16px var(--green-glow)" }}>
                {t("nav.register")}
              </Link>
            </>
          )}
        </div>
      </nav>

      {/* قائمة الموبايل */}
      {user && mobileOpen && (
        <div className="nav-mobile-menu">
          {NAV_LINKS.map((l) => (
            <NavLink key={l.to} to={l.to}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
              style={{ display: "flex", alignItems: "center", gap: 10 }}
            >
              {l.icon}
              {l.label}
            </NavLink>
          ))}
          <NavLink to="/settings"
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            style={{ display: "flex", alignItems: "center", gap: 10 }}
          >
            <Settings size={15} />
            {t("nav.settings")}
          </NavLink>
        </div>
      )}
    </>
  );
}
