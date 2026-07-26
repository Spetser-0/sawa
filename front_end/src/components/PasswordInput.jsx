import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff } from "lucide-react";

export default function PasswordInput({
  value, onChange, placeholder,
  label, name = "password",
  minLength, required = false, style: extraStyle = {},
}) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  const displayLabel = label !== undefined ? label : t("password_input.label");
  const displayPlaceholder = placeholder !== undefined ? placeholder : t("password_input.placeholder");

  return (
    <div style={{ ...extraStyle }}>
      {displayLabel && <label>{displayLabel}</label>}
      <div style={{ position: "relative" }}>
        <input
          type={visible ? "text" : "password"}
          name={name}
          value={value}
          onChange={onChange}
          placeholder={displayPlaceholder}
          autoComplete={name === "new_password" ? "new-password" : "current-password"}
          minLength={minLength}
          required={required}
          style={{ paddingInlineEnd: 44 }}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? t("password_input.hide") : t("password_input.show")}
          tabIndex={-1}
          style={{
            position: "absolute",
            insetInlineEnd: 10,
            top: "50%",
            transform: "translateY(-50%)",
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            padding: 4,
            display: "flex",
            alignItems: "center",
            transition: "color 0.2s",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "var(--green)")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
        >
          {visible ? <EyeOff size={18} /> : <Eye size={18} />}
        </button>
      </div>
    </div>
  );
}
