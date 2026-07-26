import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { useTranslation } from "react-i18next";
import { ToastProvider } from "./components/ui/Toast";
import { PageLoader } from "./components/ui/Primitives";
import Navbar from "./components/Navbar";
import Home from "./pages/Home";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import { RecordPage, WatchPage, SharePage } from "./pages/Pages";
import Pricing from "./pages/Pricing";
import Search from "./pages/Search";
import Settings from "./pages/Settings";

function Protected({ children }) {
  const { loading, verified } = useAuth();
  const { t } = useTranslation();

  if (loading) return <PageLoader label={t("loading")} />;
  if (!verified) return <Navigate to="/auth" replace />;

  return children;
}

/* التمرير لأعلى الصفحة عند تغيير المسار */
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  return null;
}

function AppRoutes() {
  return (
    <>
      <ScrollToTop />
      <Navbar />
      <Routes>
        <Route path="/"          element={<Home />} />
        <Route path="/auth"      element={<Auth />} />
        <Route path="/share/:token" element={<SharePage />} />
        <Route path="/pricing" element={<Pricing />} />

        {/* مسارات محمية */}
        <Route path="/record"    element={<Protected><RecordPage /></Protected>} />
        <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
        <Route path="/search" element={<Protected><Search /></Protected>} />
        <Route path="/watch/:id" element={<Protected><WatchPage /></Protected>} />
        <Route path="/settings" element={<Protected><Settings /></Protected>} />

        {/* أي مسار غير معروف */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <AppRoutes />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
