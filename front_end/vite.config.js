import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  
  // في التطوير: proxy للـ Backend المحلي
  // في الإنتاج: الـ Frontend يتصل بـ Render مباشرة
  server: {
    port: 3000,
    proxy: mode === "development" ? {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/media": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    } : {},
  },

  define: {
    // متاح في الكود كـ import.meta.env.VITE_API_URL
    __API_URL__: JSON.stringify(
      mode === "production"
        ? process.env.VITE_API_URL || ""
        : "http://127.0.0.1:8000"
    ),
  },

  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          hls: ["hls.js"],
          charts: ["recharts"],
          i18n: ["i18next", "react-i18next"],
          icons: ["lucide-react"],
        },
      },
    },
  },
}));
