import { useState, useRef, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { UploadCloud, HardDrive, FolderOpen, CheckCircle2, X } from "lucide-react";
import { videosAPI } from "../api/client";
import { useToast } from "../components/ui/Toast";

// يطابق backend/app/config.py::Settings.MAX_UPLOAD_BYTES — حد موحّد لكل
// مسارات الرفع (presigned PUT المباشر و proxy). لو غيّرت القيمة في الباك
// إند، حدّثها هنا كمان.
const MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024;
const ALLOWED_EXTENSIONS = [
  "mp4", "webm", "mov", "mp3", "wav", "m4a", "avi", "mkv", "ogg", "flac",
];
const LANGUAGES = [
  { value: "ar",    label: "العربية" },
  { value: "en",    label: "English" },
  { value: "es",    label: "Español" },
  { value: "fr",    label: "Français" },
  { value: "de",    label: "Deutsch" },
  { value: "ru",    label: "Русский" },
  { value: "zh",    label: "中文" },
  { value: "ja",    label: "日本語" },
  { value: "ko",    label: "한국어" },
  { value: "pt",    label: "Português" },
  { value: "it",    label: "Italiano" },
  { value: "tr",    label: "Türkçe" },
  { value: "hi",    label: "हिन्दी" },
  { value: "ar-EG", label: "العربية (مصر)" },
  { value: "ar-AE", label: "العربية (خليجي)" },
  { value: "ar-SY", label: "العربية (شامي)" },
  { value: "ar-MA", label: "العربية (مغاربي)" },
  { value: "ar-LY", label: "العربية (ليبي)" },
];

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);

export default function Uploader({ onSuccess }) {
  const { t } = useTranslation();
  const toast = useToast();

  const [state, setState]       = useState("idle");
  const [selectedFile, setFile] = useState(null);
  const [title, setTitle]       = useState("");
  const [dialect, setDialect]   = useState("ar");
  const [noiseReduction, setNR] = useState(false);
  const [progress, setProgress] = useState(0);
  const [videoId, setVideoId]   = useState(null);
  const [error, setError]       = useState("");
  const [dragOver, setDragOver] = useState(false);

  const fileInputRef = useRef(null);
  // Track blob URLs so we can revoke them after use to prevent memory leaks
  const blobUrlRef = useRef(null);

  // Revoke any tracked blob URL on unmount
  useEffect(() => {
    return () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, []);

  const validateFile = useCallback(
    (file) => {
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (!ext || !ALLOWED_EXTENSIONS.includes(ext)) {
        setError(
          t("uploader.error_file_not_supported", {
            ext,
            types: ALLOWED_EXTENSIONS.join(", "),
          }),
        );
        return false;
      }
      if (file.size > MAX_FILE_SIZE) {
        setError(t("uploader.error_file_too_large", { max: "500 MB" }));
        return false;
      }
      return true;
    },
    [t],
  );

  const handleFile = useCallback(
    (file) => {
      if (!validateFile(file)) return;
      setFile(file);
      if (!title) setTitle(file.name.replace(/\.[^.]+$/, ""));
      setError("");
    },
    [validateFile, title],
  );

  const handleInputChange = useCallback(
    (e) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
      e.target.value = "";
    },
    [handleFile],
  );

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleUpload = useCallback(async () => {
    if (!selectedFile) return;
    setState("uploading");
    setProgress(0);
    setError("");
    try {
      const video = await videosAPI.upload(
        selectedFile,
        title || selectedFile.name,
        dialect,
        "file",
        (pct) => setProgress(pct),
        noiseReduction,
      );
      setVideoId(video.id);
      setState("done");
      // Revoke any blob URL now that upload is complete and preview is no longer needed
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
      toast.success(t("uploader.toast_success"));
      if (onSuccess) onSuccess(video.id);
    } catch (err) {
      setError(`${t("uploader.error_upload_failed")}${err.message}`);
      setState("idle");
      // Also revoke on failure so leaked URLs are cleaned up
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    }
  }, [selectedFile, title, dialect, noiseReduction, t, toast, onSuccess]);

  const handleGoogleDriveImport = useCallback(async () => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    const apiKey = import.meta.env.VITE_GOOGLE_API_KEY;
    if (!clientId || !apiKey) {
      setError(t("uploader.error_drive_not_configured"));
      return;
    }

    try {
      const token = await new Promise((resolve, reject) => {
        const head = document.createElement("script");
        head.src = "https://accounts.google.com/gsi/client";
        head.onload = () => {
          const client = google.accounts.oauth2.initTokenClient({
            client_id: clientId,
            scope: "https://www.googleapis.com/auth/drive.readonly",
            callback: (resp) => {
              if (resp.error) reject(new Error(resp.error));
              else resolve(resp.access_token);
            },
          });
          client.requestAccessToken();
        };
        head.onerror = () => reject(new Error(t("uploader.error_gsi_load")));
        document.head.appendChild(head);
      });

      await new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "https://apis.google.com/js/api.js";
        script.onload = () => {
          gapi.load("picker", () => resolve());
        };
        script.onerror = () =>
          reject(new Error(t("uploader.error_picker_load")));
        document.head.appendChild(script);
      });

      const picked = await new Promise((resolve, reject) => {
        const docsView = new google.picker.DocsView(
          google.picker.ViewId.VIDEOS,
        )
          .setSelectFolderEnabled(false)
          .setMimeTypes("video/*,audio/*");

        const picker = new google.picker.PickerBuilder()
          .setTitle(t("uploader.drive_picker_title"))
          .addView(docsView)
          .setOAuthToken(token)
          .setDeveloperKey(apiKey)
          .setCallback((data) => {
            if (data.action === google.picker.Action.PICKED) {
              const doc = data.docs[0];
              if (!doc) {
                reject(new Error(t("uploader.error_no_file_selected")));
                return;
              }
              resolve(doc);
            } else if (data.action === google.picker.Action.CANCEL) {
              reject(new Error(t("uploader.error_cancelled")));
            }
          })
          .build();
        picker.setVisible(true);
      });

      setState("uploading");
      setProgress(10);

      const response = await fetch(
        `https://www.googleapis.com/drive/v3/files/${picked.id}?alt=media`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) throw new Error(t("uploader.error_drive_download"));

      const contentLength = parseInt(
        response.headers.get("content-length") || "0",
      );
      const reader = response.body.getReader();
      const chunks = [];
      let received = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        received += value.length;
        if (contentLength > 0) {
          setProgress(Math.round((received / contentLength) * 90) + 10);
        }
      }

      const blob = new Blob(chunks, {
        type: picked.mimeType || "video/mp4",
      });
      // Determine extension: prefer the extension already present in the filename,
      // then fall back to deriving it from the MIME type, then hardcode "mp4".
      const originalName = picked.name || "drive-video";
      const hasExtension = /\.[a-z0-9]{2,4}$/i.test(originalName);
      const mimeExt = (picked.mimeType || "")
        .split("/")[1]
        ?.replace(/;.*/, "")
        .toLowerCase() || "mp4";
      const finalName = hasExtension ? originalName : `${originalName}.${mimeExt}`;
      // Track blob URL if one is created for preview purposes
      const blobUrl = URL.createObjectURL(blob);
      blobUrlRef.current = blobUrl;
      const localFile = new File(
        [blob],
        finalName,
        { type: picked.mimeType || "video/mp4" },
      );

      setFile(localFile);
      if (!title) setTitle(picked.name || "");

      const video = await videosAPI.upload(
        localFile,
        title || picked.name || "Google Drive Video",
        dialect,
        "file",
        (pct) => setProgress(pct),
        noiseReduction,
      );
      setVideoId(video.id);
      setState("done");
      // Revoke blob URL now that upload is complete
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
      toast.success(t("uploader.toast_success"));
      if (onSuccess) onSuccess(video.id);
    } catch (err) {
      if (err.message === t("uploader.error_cancelled")) return;
      setError(`${t("uploader.error_import_failed")}${err.message}`);
      setState("idle");
    }
  }, [title, dialect, noiseReduction, t, toast, onSuccess]);

  const reset = useCallback(() => {
    setState("idle");
    setFile(null);
    setTitle("");
    setProgress(0);
    setVideoId(null);
    setError("");
  }, []);

  return (
    <div className="uploader fade-in">

      {state === "idle" && !selectedFile && (
        <div
          className={`uploader-dropzone${dragOver ? " uploader-dropzone--active" : ""}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="video/*,audio/*"
            className="uploader-file-input"
            onChange={handleInputChange}
            title=""
          />
          <div className="uploader-dropzone-icon">
            <UploadCloud size={32} strokeWidth={1.5} />
          </div>
          <div className="uploader-dropzone-title">
            {t("uploader.dropzone_title")}
          </div>
          <div className="uploader-dropzone-desc">
            {t("uploader.dropzone_desc")}
          </div>
          <div className="uploader-dropzone-formats">
            {t("uploader.dropzone_formats")}
          </div>
          <button
            className="btn btn-primary uploader-browse-btn"
            type="button"
            onClick={() => fileInputRef.current?.click()}
          >
            <FolderOpen size={16} />
            {t("uploader.browse")}
          </button>
          {isMobile && (
            <button
              className="btn btn-outline btn-block uploader-mobile-btn"
              type="button"
              onClick={() => {
                const camInput = document.createElement("input");
                camInput.type = "file";
                camInput.accept = "video/*,audio/*";
                camInput.capture = "environment";
                camInput.onchange = (e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFile(f);
                };
                camInput.click();
              }}
            >
              <UploadCloud size={16} />
              {t("uploader.record_camera")}
            </button>
          )}
          <button
            className="btn btn-outline btn-block uploader-drive-btn"
            type="button"
            onClick={handleGoogleDriveImport}
          >
            <HardDrive size={16} />
            Google Drive
          </button>
        </div>
      )}

      {state === "idle" && selectedFile && (
        <div className="card fade-in">
          <div className="uploader-file-info">
            <div className="uploader-file-icon">
              <FolderOpen size={20} />
            </div>
            <div className="uploader-file-details">
              <div className="uploader-file-name">{selectedFile.name}</div>
              <div className="uploader-file-size">
                {formatSize(selectedFile.size)}
              </div>
            </div>
            <button
              className="uploader-file-remove"
              type="button"
              onClick={() => {
                setFile(null);
                setError("");
              }}
            >
              <X size={16} />
            </button>
          </div>

          <div className="uploader-field">
            <label>{t("uploader.title_label")}</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("uploader.title_placeholder")}
            />
          </div>

          <div className="uploader-field">
            <label>{t("uploader.dialect")}</label>
            <select
              value={dialect}
              onChange={(e) => setDialect(e.target.value)}
            >
              {LANGUAGES.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>

          <label
            className="uploader-checkbox-row"
            onClick={() => setNR((v) => !v)}
          >
            <input
              type="checkbox"
              checked={noiseReduction}
              onChange={() => {}}
              className="uploader-checkbox"
            />
            <span className="uploader-checkbox-label">
              {t("uploader.noise_reduction")}
            </span>
            <span className="uploader-checkbox-badge">AI</span>
          </label>

          <div className="uploader-actions">
            <button
              className="btn btn-primary btn-block"
              type="button"
              onClick={handleUpload}
            >
              <UploadCloud size={16} />
              {t("uploader.upload_button")}
            </button>
          </div>

          <div className="uploader-actions">
            <button
              className="btn btn-outline btn-block"
              type="button"
              onClick={() => {
                setFile(null);
                setError("");
              }}
            >
              <X size={16} />
            </button>
          </div>

          <div className="uploader-actions">
            <button
              className="btn btn-outline btn-block uploader-drive-btn"
              type="button"
              onClick={handleGoogleDriveImport}
            >
              <HardDrive size={16} />
              Google Drive
            </button>
          </div>
        </div>
      )}

      {state === "uploading" && (
        <div className="card fade-in" style={{ textAlign: "center" }}>
          <div className="uploader-progress-icon">
            <UploadCloud size={24} />
          </div>
          <div style={{ fontWeight: 700, marginBottom: 12 }}>
            {noiseReduction
              ? t("uploader.uploading_denoising")
              : t("uploader.uploading")}
          </div>
          <div className="uploader-progress-track">
            <div
              className="uploader-progress-fill"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="uploader-progress-text">{progress}%</div>
          {noiseReduction && (
            <div className="uploader-progress-note">
              {t("uploader.denoising_filter")}
            </div>
          )}
        </div>
      )}

      {state === "done" && (
        <div className="card card-hover fade-in" style={{ textAlign: "center", borderColor: "rgba(52,211,153,0.35)" }}>
          <CheckCircle2 size={32} color="var(--green)" style={{ marginBottom: 8 }} />
          <div style={{ fontWeight: 700, marginBottom: 4 }}>
            {t("uploader.upload_done")}
          </div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
            {noiseReduction
              ? t("uploader.upload_done_denoising_desc")
              : t("uploader.upload_done_desc")}
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
            <a href={`/watch/${videoId}`} className="btn btn-primary">
              {t("uploader.view_recording")}
            </a>
            <button
              className="btn btn-outline"
              type="button"
              onClick={reset}
            >
              {t("uploader.upload_another")}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="alert alert-error" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}
    </div>
  );
}
