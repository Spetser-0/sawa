/**
2	 * API Client - Cross-Domain + CSRF + Bearer Fallback + Retry + Abort
2	 */
3	
4	const API_BASE = import.meta.env.VITE_API_URL
5	  ? `${import.meta.env.VITE_API_URL}/api`
6	  : "/api";
7	
8	let csrfToken = null;
9	let currentUpload = null;
10	
11	const NO_REFRESH_PATHS = [
12	  "/auth/login",
13	  "/auth/register",
14	  "/auth/refresh",
15	  "/auth/logout",
16	];
17	
18	// Bearer token helper for iOS/CORS fallback
19	const getAuthToken = () => localStorage.getItem("sawa_token");
20	const setAuthToken = (token) => localStorage.setItem("sawa_token", token);
21	
22	async function initCsrf() {
23	  try {
24	    const res = await fetch(`${API_BASE}/auth/csrf-token`, {
25	      credentials: "include",
26	      mode: "cors",
27	    });
28	    if (res.ok) {
29	      const data = await res.json();
30	      csrfToken = data.csrf_token;
31	    }
32	  } catch {
33	    /* best-effort */
34	  }
35	}
36	
37	initCsrf();
38	
39	async function ensureCsrf() {
40	  if (!csrfToken) await initCsrf();
41	}
42	
43	async function request(
44	  method,
45	  path,
46	  body,
47	  isFormData = false,
48	  isRetry = false,
49	  retries = 0,
50	) {
51	  await ensureCsrf();
52	
53	  const headers = {};
54	  if (!isFormData && body) headers["Content-Type"] = "application/json";
55	
56	  if (method !== "GET" && csrfToken) {
57	    headers["X-CSRF-Token"] = csrfToken;
58	  }
59	
60	  // iOS Fallback: Add Bearer token if cookies are blocked
61	  const token = getAuthToken();
62	  if (token) {
63	    headers["Authorization"] = `Bearer ${token}`;
64	  }
65	
66	  try {
67	    const res = await fetch(`${API_BASE}${path}`, {
68	      method,
69	      headers,
70	      credentials: "include",
71	      mode: "cors",
72	      body: isFormData ? body : body ? JSON.stringify(body) : undefined,
73	    });
74	
75	    // Handle Auth Responses
76	    if (path === "/auth/login" && res.ok) {
77	      const data = await res.clone().json();
78	      if (data.access_token) setAuthToken(data.access_token);
79	    }
80	
81	    // تجديد التوكن التلقائي
82	    if (
83	      res.status === 401 &&
84	      !isRetry &&
85	      !NO_REFRESH_PATHS.some((p) => path.startsWith(p))
86	    ) {
87	      try {
88	        const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
89	          method: "POST",
90	          credentials: "include",
91	          mode: "cors",
92	          headers: token ? { "Authorization": `Bearer ${token}` } : {},
93	        });
94	        if (refreshRes.ok) {
95	          const data = await refreshRes.json();
96	          if (data.access_token) setAuthToken(data.access_token);
97	          return request(method, path, body, isFormData, true);
98	        }
99	      } catch {
100	        /* refresh failed */
101	      }
102	
103	      const err = new Error("انتهت صلاحية الجلسة");
104	      err.status = 401;
105	      err.code = "SESSION_EXPIRED";
106	      throw err;
107	    }
108	
109	    if (!res.ok) {
110	      const err = await res.json().catch(() => ({ detail: "خطأ غير متوقع" }));
111	      const error = new Error(err.detail || "فشل الطلب");
112	      error.status = res.status;
113	      error.detail = err.detail;
114	      error.error_code = err.error_code;
115	      throw error;
116	    }
117	    if (res.status === 204) return null;
118	    return res.json();
119	  } catch (networkErr) {
120	    if (!networkErr.status && retries < 2) {
121	      await new Promise((r) => setTimeout(r, 1000 * (retries + 1)));
122	      return request(method, path, body, isFormData, isRetry, retries + 1);
123	    }
124	    throw networkErr;
125	  }
126	}
127	
128	// ── Auth ──────────────────────────────────────────────
129	export const authAPI = {
130	  register: (name, email, password) =>
131	    request("POST", "/auth/register", { name, email, password }),
132	  login: (email, password) =>
133	    request("POST", "/auth/login", { email, password }),
134	  logout: () => {
135	    localStorage.removeItem("sawa_token");
136	    return request("POST", "/auth/logout");
137	  },
138	  me: () => request("GET", "/auth/me"),
139	  csrf: () => request("GET", "/auth/csrf-token"),
140	  updateName: (name) => request("PATCH", "/auth/settings/name", { name }),
141	  updatePassword: (current_password, new_password) =>
142	    request("PATCH", "/auth/settings/password", {
143	      current_password,
144	      new_password,
145	    }),
146	  forgotPassword: (email) =>
147	    request("POST", "/auth/forgot-password", { email }),
148	  verifyOtp: (email, otp) =>
149	    request("POST", "/auth/verify-otp", { email, otp }),
150	  resetPassword: (reset_token, new_password) =>
151	    request("POST", "/auth/reset-password", { reset_token, new_password }),
152	};
153	
154	// ── Videos ───────────────────────────────────────────
155	export const videosAPI = {
156	  /**
157	   * Upload using Presigned URLs (Direct-to-R2)
158	   * This is much more reliable for large files and works better on iOS.
159	   */
160	  upload: async (
161	    file,
162	    title,
163	    dialect = "ar",
164	    mode = "screen",
165	    onProgress,
166	    noiseReduction = false,
167	  ) => {
168	    // 1. Get presigned URL from backend
169	    const presigned = await request("POST", "/videos/presigned-upload", {
170	      filename: file.name,
171	      content_type: file.type || "video/webm",
172	      title,
173	      dialect,
174	    });
175	
176	    const { url, fields, video_id } = presigned;
177	
178	    // 2. Upload directly to R2
179	    return new Promise((resolve, reject) => {
180	      const xhr = new XMLHttpRequest();
181	      xhr.open("PUT", url); // R2 presigned PUT
182	      
183	      // Set Content-Type header as required by presigned URL
184	      xhr.setRequestHeader("Content-Type", file.type || "video/webm");
185	
186	      if (onProgress) {
187	        xhr.upload.onprogress = (e) => {
188	          if (e.lengthComputable)
189	            onProgress(Math.round((e.loaded / e.total) * 100));
190	        };
191	      }
192	
193	      xhr.onload = async () => {
194	        currentUpload = null;
195	        if (xhr.status === 200 || xhr.status === 204) {
196	          // 3. Inform backend that upload is complete (optional, depends on backend logic)
197	          // For Sawa, the record is already created as 'pending'.
198	          // We can now fetch the full video object.
199	          try {
200	            const video = await videosAPI.getVideo(video_id);
201	            resolve(video);
202	          } catch (err) {
203	            reject(err);
204	          }
205	        } else {
206	          reject(new Error(`فشل الرفع المباشر: ${xhr.status}`));
207	        }
208	      };
209	      
210	      xhr.onerror = () => { currentUpload = null; reject(new Error("خطأ في الشبكة أثناء الرفع المباشر")); };
211	      xhr.ontimeout = () => { currentUpload = null; reject(new Error("انتهت مهلة الرفع المباشر")); };
212	      xhr.onabort = () => { currentUpload = null; reject(new Error("تم إلغاء الرفع")); };
213	      
214	      xhr.timeout = 600000; // 10 minutes for direct upload
215	      xhr.send(file);
216	      currentUpload = xhr;
217	    });
218	  },
219	
220	  cancelUpload: () => {
221	    if (currentUpload) {
222	      currentUpload.abort();
223	      currentUpload = null;
224	    }
225	  },
226	
227	  getMyVideos: () => request("GET", "/videos/my"),
228	  getVideo: (id) => request("GET", `/videos/${id}`),
229	  getByToken: (tok) => request("GET", `/videos/share/${tok}`),
230	  deleteVideo: (id) => request("DELETE", `/videos/${id}`),
231	  updateShareSettings: (id, data) =>
232	    request("PATCH", `/videos/${id}/share-settings`, data),
233	  unlockShare: (token, password) =>
234	    request("POST", `/videos/share/${token}/unlock`, { password }),
235	  streamUrl: (videoId) => `${API_BASE}/videos/${videoId}/stream`,
236	  shareStreamUrl: (token) => `${API_BASE}/videos/share/${token}/stream`,
237	  hlsUrl: (videoId) => `${API_BASE}/videos/${videoId}/hls/playlist.m3u8`,
238	  convertHls: (videoId) => request("POST", `/videos/${videoId}/hls/convert`),
239	};
240	
241	// ── Transcripts ───────────────────────────────────────
242	export const transcriptAPI = {
243	  get: (videoId) => request("GET", `/transcripts/${videoId}`),
244	  edit: (videoId, data) => request("PATCH", `/transcripts/${videoId}`, data),
245	  retry: (videoId) => request("POST", `/transcripts/${videoId}/retry`),
246	  export: (videoId, fmt) =>
247	    `${API_BASE}/transcripts/${videoId}/export?fmt=${fmt}`,
248	};
249	
250	// ── AI Features ───────────────────────────────────────
251	export const aiAPI = {
252	  translate: (videoId) => request("POST", `/transcripts/${videoId}/translate`),
253	  summarize: (videoId) => request("POST", `/transcripts/${videoId}/summarize`),
254	  diarize: (videoId, n) =>
255	    request(
256	      "POST",
257	      `/transcripts/${videoId}/diarize${n ? `?num_speakers=${n}` : ""}`,
258	    ),
259	  exportUrl: (videoId, fmt) =>
260	    `${API_BASE}/transcripts/${videoId}/export?fmt=${fmt}`,
261	  generateChapters: (videoId) =>
262	    request("POST", `/transcripts/${videoId}/chapters`),
263	  getChapters: (videoId) => request("GET", `/transcripts/${videoId}/chapters`),
264	};
265	
266	// ── Comments ──────────────────────────────────────────
267	export const commentsAPI = {
268	  list: (videoId) => request("GET", `/videos/${videoId}/comments`),
269	  add: (videoId, data) => request("POST", `/videos/${videoId}/comments`, data),
270	  delete: (commentId) => request("DELETE", `/videos/comment/${commentId}`),
271	};
272	
273	// ── Analytics ─────────────────────────────────────────
274	export const analyticsAPI = {
275	  ping: (videoId, secondsWatched) =>
276	    request("POST", `/videos/${videoId}/view-event`, {
277	      seconds_watched: secondsWatched,
278	    }),
279	  get: (videoId) => request("GET", `/videos/${videoId}/analytics`),
280	};
281	
282	// ── Payments ──────────────────────────────────────────
283	export const paymentsAPI = {
284	  getPlans: () => request("GET", "/payments/plans"),
285	  getStatus: () => request("GET", "/payments/status"),
286	  create: (plan) => request("POST", "/payments/create", { plan }),
287	  demo: (plan) => request("POST", `/payments/demo-activate/${plan}`),
288	};
289	
290	// ── Search ────────────────────────────────────────────
291	export const searchAPI = {
292	  search: (q) => request("GET", `/search?q=${encodeURIComponent(q)}`),
293	  suggest: (q) => request("GET", `/search/suggest?q=${encodeURIComponent(q)}`),
294	};
295	
