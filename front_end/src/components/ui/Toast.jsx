/**
 * نظام إشعارات Toast خفيف — بديل احترافي عن alert()
 * الاستخدام: const toast = useToast(); toast.success("تم!"); toast.error("فشل");
 */
import { createContext, useContext, useState, useCallback, useRef } from "react";
import { CheckCircle2, XCircle, Info } from "lucide-react";

const ToastContext = createContext(null);

const ICONS = {
  success: <CheckCircle2 size={17} color="var(--green)" />,
  error:   <XCircle size={17} color="var(--red)" />,
  info:    <Info size={17} color="var(--purple)" />,
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const push = useCallback((type, message, duration = 3500) => {
    const id = ++idRef.current;
    setToasts((t) => [...t, { id, type, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), duration);
  }, []);

  const api = {
    success: (msg, d) => push("success", msg, d),
    error:   (msg, d) => push("error", msg, d ?? 5000),
    info:    (msg, d) => push("info", msg, d),
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-container" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            {ICONS[t.type]}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // fallback آمن إذا استُخدم خارج المزود
    return {
      success: (m) => console.log("[toast]", m),
      error:   (m) => console.error("[toast]", m),
      info:    (m) => console.info("[toast]", m),
    };
  }
  return ctx;
}
