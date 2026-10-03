"use client";

import { useEffect, useRef, useState } from "react";
import { Play } from "lucide-react";

import { callsApi, formatApiError } from "@/services/api";

export type RecordingLoader = (logId: string) => Promise<string>;

/**
 * Plays a call recording. The audio bytes are fetched with the merchant bearer
 * header (an `<audio src>` can't carry one) and exposed as an object URL that
 * is revoked when the component unmounts or the log changes. Nothing is
 * downloaded until the user asks for it.
 *
 * `load` turns a call-log id into an object URL; it defaults to the account's
 * call-log recording endpoint (`callsApi.recordingObjectUrl`).
 */
export function RecordingPlayer({ logId, load }: { logId: string; load?: RecordingLoader }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [requested, setRequested] = useState(false);
  // Keep the latest loader without re-fetching when a parent passes an inline function.
  const loaderRef = useRef<RecordingLoader>(load ?? callsApi.recordingObjectUrl);
  useEffect(() => {
    loaderRef.current = load ?? callsApi.recordingObjectUrl;
  }, [load]);

  useEffect(() => {
    setRequested(false);
    setUrl(null);
    setError(null);
  }, [logId]);

  useEffect(() => {
    if (!requested) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    setLoading(true);
    setError(null);
    loaderRef
      .current(logId)
      .then((next) => {
        if (cancelled) {
          URL.revokeObjectURL(next);
          return;
        }
        objectUrl = next;
        setUrl(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(formatApiError(err, "Recording unavailable"));
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
      <button
        type="button"
        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1 text-xs font-medium text-primary-dark hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => setRequested(true)}
      >
        <Play className="h-3.5 w-3.5" aria-hidden="true" />
        Play recording
      </button>
    );
  }
  if (loading) return <span className="text-xs text-muted-foreground" role="status">Loading recording…</span>;
  if (error) {
    return (
      <span className="text-xs text-destructive">
        {error}{" "}
        <button type="button" className="font-medium underline" onClick={() => setRequested(false)}>
          Try again
        </button>
      </span>
    );
  }
  if (!url) return null;
  // Phone recordings have no caption track; the transcript is shown alongside.
  return <audio controls autoPlay preload="metadata" src={url} className="h-9 w-full max-w-md" aria-label="Call recording" />;
}
