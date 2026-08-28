"use client";

import { useEffect, useState } from "react";

import { ordersApi } from "@/services/api";

/**
 * Plays a call recording. The audio bytes are fetched with the merchant bearer
 * header (an `<audio src>` can't carry one) and exposed as an object URL that
 * is revoked when the component unmounts or the log changes.
 */
export function RecordingPlayer({ logId }: { logId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [requested, setRequested] = useState(false);

  useEffect(() => {
    if (!requested) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    setLoading(true);
    setError(null);
    ordersApi
      .recordingObjectUrl(logId)
      .then((next) => {
        if (cancelled) {
          URL.revokeObjectURL(next);
          return;
        }
        objectUrl = next;
        setUrl(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Recording unavailable");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [logId, requested]);

  if (!requested) {
    return (
      <button type="button" className="text-xs font-medium text-primary hover:underline" onClick={() => setRequested(true)}>
        Load recording
      </button>
    );
  }
  if (loading) return <span className="text-xs text-muted-foreground">Loading recording…</span>;
  if (error) return <span className="text-xs text-destructive">{error}</span>;
  if (!url) return null;
  return <audio controls preload="metadata" src={url} className="h-9 w-full max-w-md" />;
}
