/**
 * API Client — Cross-Domain + CSRF + Bearer Fallback + Retry + Abort
 */

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "/api";

let csrfToken = null;
let currentUpload = null;

const NO_REFRESH_PATHS = [
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
  "/auth/logout",
];

const getAuthToken = () => localStorage.getItem("sawa_token");
const setAuthToken = (token) => localStorage.setItem("sawa_token", token);

async function initCsrf() {
  try {
    const res = await fetch(`${API_BASE}/auth/csrf-token`, {
      credentials: "include",
      mode: "cors",
    });
    if (res.ok) {
      const data = await res.json();
      csrfToken = data.csrf_token;
    }
  } catch {
    /* best-effort */
  }
}

initCsrf();

async function ensureCsrf() {
  if (!csrfToken) await initCsrf();
}

async function request(
  method,
  path,
  body,
  isFormData = false,
  isRetry = false,
  retries = 0,
) {
  await ensureCsrf();

  const headers = {};
  if (!isFormData && body) headers["Content-Type"] = "application/json";

  if (method !== "GET" && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      credentials: "include",
      mode: "cors",
      body: isFormData ? body : body ? JSON.stringify(body) : undefined,
    });

    if (path === "/auth/login" && res.ok) {
      const data = await res.clone().json();
      if (data.access_token) setAuthToken(data.access_token);
    }

    if (
      res.status === 401 &&
      !isRetry &&
      !NO_REFRESH_PATHS.some((p) => path.startsWith(p))
    ) {
      try {
        const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          credentials: "include",
          mode: "cors",
          headers: token ? { "Authorization": `Bearer ${token}` } : {},
        });
        if (refreshRes.ok) {
          const data = await refreshRes.json();
          if (data.access_token) setAuthToken(data.access_token);
          return request(method, path, body, isFormData, true);
        }
      } catch {
        /* refresh failed */
      }

      const err = new Error("انتهت صلاحية الجلسة");
      err.status = 401;
      err.code = "SESSION_EXPIRED";
      throw err;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "خطأ غير متوقع" }));
      const error = new Error(err.detail || "فشل الطلب");
      error.status = res.status;
      error.detail = err.detail;
      error.error_code = err.error_code;
      throw error;
    }
    if (res.status === 204) return null;
    return res.json();
  } catch (networkErr) {
    if (!networkErr.status && retries < 2) {
      await new Promise((r) => setTimeout(r, 1000 * (retries + 1)));
      return request(method, path, body, isFormData, isRetry, retries + 1);
    }
    throw networkErr;
  }
}

// ── Auth ──────────────────────────────────────────────
export const authAPI = {
  register: (name, email, password) =>
    request("POST", "/auth/register", { name, email, password }),
  login: (email, password) =>
    request("POST", "/auth/login", { email, password }),
  logout: () => {
    localStorage.removeItem("sawa_token");
    return request("POST", "/auth/logout");
  },
  me: () => request("GET", "/auth/me"),
  csrf: () => request("GET", "/auth/csrf-token"),
  updateName: (name) => request("PATCH", "/auth/settings/name", { name }),
  updatePassword: (current_password, new_password) =>
    request("PATCH", "/auth/settings/password", {
      current_password,
      new_password,
    }),
  forgotPassword: (email) =>
    request("POST", "/auth/forgot-password", { email }),
  verifyOtp: (email, otp) =>
    request("POST", "/auth/verify-otp", { email, otp }),
  resetPassword: (reset_token, new_password) =>
    request("POST", "/auth/reset-password", { reset_token, new_password }),
};

// ── Videos ───────────────────────────────────────────
export const videosAPI = {
  /**
   * Upload using Presigned URLs (Direct-to-R2)
   * This is much more reliable for large files and works better on iOS.
   */
  upload: async (
    file,
    title,
    dialect = "ar",
    mode = "screen",
    onProgress,
    noiseReduction = false,
  ) => {
    const presigned = await request("POST", "/videos/presigned-upload", {
      filename: file.name,
      content_type: file.type || "video/webm",
      title,
      dialect,
    });

    const { url, fields, video_id } = presigned;

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", url);
      xhr.setRequestHeader("Content-Type", file.type || "video/webm");

      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable)
            onProgress(Math.round((e.loaded / e.total) * 100));
        };
      }

      xhr.onload = async () => {
        currentUpload = null;
        if (xhr.status === 200 || xhr.status === 204) {
          try {
            await request("POST", `/videos/${video_id}/complete`);
            const video = await videosAPI.getVideo(video_id);
            resolve(video);
          } catch (err) {
            reject(err);
          }
        } else {
          reject(new Error(`فشل الرفع المباشر: ${xhr.status}`));
        }
      };

      xhr.onerror = () => { currentUpload = null; reject(new Error("خطأ في الشبكة أثناء الرفع المباشر")); };
      xhr.ontimeout = () => { currentUpload = null; reject(new Error("انتهت مهلة الرفع المباشر")); };
      xhr.onabort = () => { currentUpload = null; reject(new Error("تم إلغاء الرفع")); };

      xhr.timeout = 600000;
      xhr.send(file);
      currentUpload = xhr;
    });
  },

  cancelUpload: () => {
    if (currentUpload) {
      currentUpload.abort();
      currentUpload = null;
    }
  },

  getMyVideos: () => request("GET", "/videos/my"),
  getVideo: (id) => request("GET", `/videos/${id}`),
  getByToken: (tok) => request("GET", `/videos/share/${tok}`),
  deleteVideo: (id) => request("DELETE", `/videos/${id}`),
  updateShareSettings: (id, data) =>
    request("PATCH", `/videos/${id}/share-settings`, data),
  unlockShare: (token, password) =>
    request("POST", `/videos/share/${token}/unlock`, { password }),
  streamUrl: (videoId) => `${API_BASE}/videos/${videoId}/stream`,
  shareStreamUrl: (token) => `${API_BASE}/videos/share/${token}/stream`,
  hlsUrl: (videoId) => `${API_BASE}/videos/${videoId}/hls/playlist.m3u8`,
  convertHls: (videoId) => request("POST", `/videos/${videoId}/hls/convert`),
};

// ── Transcripts ───────────────────────────────────────
export const transcriptAPI = {
  get: (videoId) => request("GET", `/transcripts/${videoId}`),
  edit: (videoId, data) => request("PATCH", `/transcripts/${videoId}`, data),
  retry: (videoId) => request("POST", `/transcripts/${videoId}/retry`),
  export: (videoId, fmt) =>
    `${API_BASE}/transcripts/${videoId}/export?fmt=${fmt}`,
};

// ── AI Features ───────────────────────────────────────
export const aiAPI = {
  translate: (videoId) => request("POST", `/transcripts/${videoId}/translate`),
  summarize: (videoId) => request("POST", `/transcripts/${videoId}/summarize`),
  diarize: (videoId, n) =>
    request(
      "POST",
      `/transcripts/${videoId}/diarize${n ? `?num_speakers=${n}` : ""}`,
    ),
  exportUrl: (videoId, fmt) =>
    `${API_BASE}/transcripts/${videoId}/export?fmt=${fmt}`,
  generateChapters: (videoId) =>
    request("POST", `/transcripts/${videoId}/chapters`),
  getChapters: (videoId) => request("GET", `/transcripts/${videoId}/chapters`),
};

// ── Comments ──────────────────────────────────────────
export const commentsAPI = {
  list: (videoId) => request("GET", `/videos/${videoId}/comments`),
  add: (videoId, data) => request("POST", `/videos/${videoId}/comments`, data),
  delete: (commentId) => request("DELETE", `/videos/comment/${commentId}`),
};

// ── Analytics ─────────────────────────────────────────
export const analyticsAPI = {
  ping: (videoId, secondsWatched) =>
    request("POST", `/videos/${videoId}/view-event`, {
      seconds_watched: secondsWatched,
    }),
  get: (videoId) => request("GET", `/videos/${videoId}/analytics`),
};

// ── Payments ──────────────────────────────────────────
export const paymentsAPI = {
  getPlans: () => request("GET", "/payments/plans"),
  getStatus: () => request("GET", "/payments/status"),
  create: (plan) => request("POST", "/payments/create", { plan }),
  demo: (plan) => request("POST", `/payments/demo-activate/${plan}`),
};

// ── Search ────────────────────────────────────────────
export const searchAPI = {
  search: (q) => request("GET", `/search?q=${encodeURIComponent(q)}`),
  suggest: (q) => request("GET", `/search/suggest?q=${encodeURIComponent(q)}`),
};
