"use client";

import { useEffect, useRef } from "react";

/**
 * Calls `tick` now and every `intervalMs` while the tab is visible; pauses when hidden and
 * ticks again as soon as it is shown. A tick never overlaps the previous one.
 */
export function usePolling(tick: () => Promise<unknown> | void, intervalMs: number, enabled = true) {
  const tickRef = useRef(tick);
  useEffect(() => {
    tickRef.current = tick;
  });

  useEffect(() => {
    if (!enabled) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let running = false;
    let stopped = false;

    const schedule = () => {
      if (timer) clearTimeout(timer);
      if (!stopped && document.visibilityState === "visible") timer = setTimeout(run, intervalMs);
    };
    const run = async () => {
      if (running || stopped) return;
      running = true;
      try {
        await tickRef.current();
      } catch {
        // The caller shows its own error state.
      } finally {
        running = false;
        schedule();
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") void run();
      else if (timer) clearTimeout(timer);
    };

    void run();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [intervalMs, enabled]);
}
