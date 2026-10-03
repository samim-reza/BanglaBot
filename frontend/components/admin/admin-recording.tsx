"use client";

import { useEffect, useState } from "react";
import { Mic } from "lucide-react";

import { formatApiError, rawRequest } from "@/services/api";

/**
 * Plays a call recording from GET /api/admin/recordings/{id}. An <audio src>
 * can't send the admin bearer header, so the bytes are fetched on demand and
 * exposed as an object URL that is revoked on unmount.
 */
export function AdminRecordingPlayer({ logId }: { logId: string }) {
  const [requested, setRequested] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!requested) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    setError(null);
    rawRequest(`/api/admin/recordings/${encodeURIComponent(logId)}`, { auth: "admin" })
      .then((response) => response.blob())
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((err) => {
        if (!cancelled) setError(formatApiError(err, "Recording unavailable."));
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [logId, requested]);

  if (!requested) {
    return (
      <button
        type="button"
        onClick={() => setRequested(true)}
        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs font-semibold text-foreground hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Mic className="h-3.5 w-3.5" aria-hidden="true" />
        Play recording
      </button>
    );
  }
  if (error) return <span className="text-xs text-destructive">{error}</span>;
  if (!url) return <span className="text-xs text-muted-foreground" role="status">Loading recording…</span>;
  return <audio controls autoPlay preload="metadata" src={url} className="h-9 w-full max-w-md" aria-label="Call recording" />;
}
