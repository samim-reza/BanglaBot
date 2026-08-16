import { useEffect, useState } from "react";
import { fetchBlob } from "../api/client";
import { useLang } from "../i18n";

/**
 * Lazy audio player for call recordings. The audio is fetched through the
 * backend proxy with the auth header (a plain <audio src> can't send it).
 */
export default function RecordingPlayer({ path }: { path: string }) {
  const { t } = useLang();
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);

  async function load() {
    setBusy(true);
    setError("");
    try {
      const blob = await fetchBlob(path);
      setUrl(URL.createObjectURL(blob));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (url) return <audio controls autoPlay src={url} style={{ width: "100%", maxWidth: 420 }} />;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <button type="button" className="btn secondary small" onClick={load} disabled={busy}>
        {busy ? t("রেকর্ডিং লোড হচ্ছে...") : `▶ ${t("রেকর্ডিং শুনুন")}`}
      </button>
      {error && <span className="error">{t(error)}</span>}
    </span>
  );
}
