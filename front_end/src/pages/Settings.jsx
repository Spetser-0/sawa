import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { authAPI } from "../api/client";
import { useTranslation } from "react-i18next";
import PasswordInput from "../components/PasswordInput";
import { UserRound, KeyRound, CheckCircle2, AlertCircle, ArrowRight } from "lucide-react";

const PASSWORD_MIN_CHARS = 8;

function getStrength(pwd) {
  let score = 0;
  if (pwd.length >= 8) score++;
  if (/[A-Z]/.test(pwd)) score++;
  if (/[0-9]/.test(pwd)) score++;
  if (/[^A-Za-z0-9]/.test(pwd)) score++;
  return score;
}
const STRENGTH_COLORS = ["#F87171", "#F87171", "#FCD34D", "#34D399", "#34D399"];

export default function Settings() {
  const { user, logout, refresh } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const ERROR_MESSAGES = {
    "WRONG_PASSWORD": t("settings.error_wrong_current_password"),
    "SAME_PASSWORD": t("settings.error_same_password"),
    "VALIDATION_ERROR": t("settings.error_validation"),
  };
  const STRENGTH_LABELS = [t("settings.strength_0"), t("settings.strength_1"), t("settings.strength_2"), t("settings.strength_3"), t("settings.strength_4")];

  // ── تغيير الاسم ──
  const [name, setName] = useState(user?.name || "");
  const [nameLoading, setNameLoading] = useState(false);
  const [nameMsg, setNameMsg] = useState({ type: "", text: "" });

  // ── تغيير كلمة المرور ──
  const [currentPwd, setCurrentPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [pwdLoading, setPwdLoading] = useState(false);
  const [pwdMsg, setPwdMsg] = useState({ type: "", text: "" });

  const handleNameSave = async () => {
    setNameLoading(true);
    setNameMsg({ type: "", text: "" });
    try {
      await authAPI.updateName(name.trim());
      await refresh();
      setNameMsg({ type: "success", text: t("settings.name_updated") });
    } catch (err) {
      setNameMsg({ type: "error", text: err.message });
    } finally {
      setNameLoading(false);
    }
  };

  const handlePasswordChange = async () => {
    setPwdLoading(true);
    setPwdMsg({ type: "", text: "" });

    if (newPwd.length < PASSWORD_MIN_CHARS) {
      setPwdMsg({ type: "error", text: t("settings.error_password_min", { count: PASSWORD_MIN_CHARS }) });
      setPwdLoading(false);
      return;
    }
    if (!/\d/.test(newPwd)) {
      setPwdMsg({ type: "error", text: t("settings.error_password_digit") });
      setPwdLoading(false);
      return;
    }
    if (newPwd !== confirmPwd) {
      setPwdMsg({ type: "error", text: t("settings.error_password_mismatch") });
      setPwdLoading(false);
      return;
    }

    try {
      await authAPI.updatePassword(currentPwd, newPwd);
      setPwdMsg({ type: "success", text: t("settings.password_changed") });
      setTimeout(async () => {
        await logout();
        navigate("/auth");
      }, 2000);
    } catch (err) {
      const code = err.error_code;
      setPwdMsg({ type: "error", text: code ? (ERROR_MESSAGES[code] || err.message) : err.message });
    } finally {
      setPwdLoading(false);
    }
  };

  const inputStyle = { marginBottom: 0 };

  return (
    <div style={{ minHeight: "80vh", padding: "40px 24px", maxWidth: 600, margin: "0 auto" }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 4 }}>{t("settings.title")}</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 14 }}>{t("settings.subtitle")}</p>
      </div>

      {/* معلومات الحساب */}
      <div className="card fade-in" style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
          <UserRound size={16} color="var(--green)" />
          {t("settings.account_info")}
        </h2>

        <div style={{ marginBottom: 14 }}>
          <label>{t("settings.email")}</label>
          <input type="email" value={user?.email || ""} disabled
            style={{ opacity: 0.5, cursor: "not-allowed" }} />
        </div>

        <div style={{ marginBottom: 14 }}>
          <label>{t("settings.name")}</label>
          <input value={name} onChange={e => setName(e.target.value)} placeholder={t("settings.name_placeholder")} style={inputStyle} />
        </div>

        {nameMsg.text && (
          <div style={{
            padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 12,
            background: nameMsg.type === "success" ? "#34D39915" : "#F8717115",
            border: `1px solid ${nameMsg.type === "success" ? "#34D39933" : "#F8717133"}`,
            color: nameMsg.type === "success" ? "var(--green)" : "var(--red)",
            display: "flex", alignItems: "center", gap: 8,
          }}>
            {nameMsg.type === "success" ? <CheckCircle2 size={14} style={{ flexShrink: 0 }} /> : <AlertCircle size={14} style={{ flexShrink: 0 }} />}
            {nameMsg.text}
          </div>
        )}

        <button className="btn btn-primary" onClick={handleNameSave} disabled={nameLoading}
          style={{ justifyContent: "center", width: "100%" }}>
          {nameLoading ? t("settings.saving") : t("settings.save_changes")}
        </button>
      </div>

      {/* تغيير كلمة المرور */}
      <div className="card fade-in" style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
          <KeyRound size={16} color="var(--purple)" />
          {t("settings.change_password")}
        </h2>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <PasswordInput
            label={t("settings.current_password")}
            value={currentPwd}
            onChange={e => setCurrentPwd(e.target.value)}
            name="current_password"
          />

          <PasswordInput
            label={t("settings.new_password")}
            value={newPwd}
            onChange={e => setNewPwd(e.target.value)}
            placeholder={t("settings.password_placeholder")}
            name="new_password"
          />

          {newPwd.length > 0 && (() => {
            const s = getStrength(newPwd);
            return (
              <div>
                <div style={{ display: "flex", gap: 4, marginBottom: 4 }}>
                  {[0,1,2,3].map(i => (
                    <div key={i} style={{ flex: 1, height: 4, borderRadius: 2, background: i < s ? STRENGTH_COLORS[s] : "var(--border)", transition: "background 0.3s" }} />
                  ))}
                </div>
                <span style={{ fontSize: 11, color: STRENGTH_COLORS[s] }}>{STRENGTH_LABELS[s]}</span>
              </div>
            );
          })()}

          <PasswordInput
            label={t("settings.confirm_password")}
            value={confirmPwd}
            onChange={e => setConfirmPwd(e.target.value)}
            name="confirm_new_password"
          />

          {pwdMsg.text && (
            <div style={{
              padding: "10px 14px", borderRadius: 8, fontSize: 13,
              background: pwdMsg.type === "success" ? "#34D39915" : "#F8717115",
              border: `1px solid ${pwdMsg.type === "success" ? "#34D39933" : "#F8717133"}`,
              color: pwdMsg.type === "success" ? "var(--green)" : "var(--red)",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              {pwdMsg.type === "success" ? <CheckCircle2 size={14} style={{ flexShrink: 0 }} /> : <AlertCircle size={14} style={{ flexShrink: 0 }} />}
              {pwdMsg.text}
            </div>
          )}

          <button className="btn btn-primary" onClick={handlePasswordChange} disabled={pwdLoading}
            style={{ justifyContent: "center" }}>
            {pwdLoading ? t("settings.changing") : t("settings.change_password_btn")}
          </button>
        </div>
      </div>

      {/* رابط العودة */}
      <div style={{ textAlign: "center" }}>
        <Link to="/dashboard" style={{ color: "var(--text-muted)", fontSize: 13, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6 }}>
          <ArrowRight size={14} />
          {t("settings.back_to_dashboard")}
        </Link>
      </div>
    </div>
  );
}
