"use client";

import { useEffect, useState } from "react";
import { Headphones, LoaderCircle, Mic, MicOff, PhoneCall, PhoneOff, TriangleAlert } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { Conversation } from "./conversation";
import { voiceActive, type VoiceCall } from "./use-voice-call";

function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function useNow(enabled: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [enabled]);
  return now;
}

function LevelMeter({ level, muted, active }: { level: number; muted: boolean; active: boolean }) {
  const bars = 12;
  const lit = muted || !active ? 0 : Math.round(Math.min(1, level) * bars);
  return (
    <div className="flex items-center gap-2">
      {muted ? <MicOff className="h-4 w-4 shrink-0 text-destructive" aria-hidden /> : <Mic className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />}
      <div
        role="meter"
        aria-label="Microphone level"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={muted ? 0 : Math.round(level * 100)}
        aria-valuetext={muted ? "Muted" : `${Math.round(level * 100)}%`}
        className="flex h-4 flex-1 items-end gap-0.5"
      >
        {Array.from({ length: bars }, (_, index) => (
          <span
            key={index}
            aria-hidden
            className={cn("flex-1 rounded-sm transition-colors duration-75", index < lit ? "bg-primary" : "bg-secondary")}
            style={{ height: `${35 + (index / (bars - 1)) * 65}%` }}
          />
        ))}
      </div>
      <span className="w-12 shrink-0 text-right text-xs text-muted-foreground">{muted ? "Muted" : active ? "Mic on" : "Mic off"}</span>
    </div>
  );
}

/** The browser call: start / hang up, mute, mic level and the live transcript. */
export function VoicePanel({ voice, onStart, startDisabled, startHint }: { voice: VoiceCall; onStart: () => void; startDisabled?: boolean; startHint?: string }) {
  const { phase, error, lines, level, muted, startedAt, endedAt, socketUrl } = voice;
  const active = voiceActive(phase);
  const now = useNow(phase === "live");
  const elapsed = startedAt ? (phase === "live" ? now : endedAt ?? now) - startedAt : 0;
  const endedQuickly = phase === "ended" && startedAt !== null && endedAt !== null && endedAt - startedAt < 4000 && lines.length === 0;

  const status =
    phase === "idle"
      ? "Ready when you are"
      : phase === "requesting"
        ? "Getting a line…"
        : phase === "connecting"
          ? "Connecting…"
          : phase === "live"
            ? `Live · ${clock(elapsed)}`
            : phase === "ended"
              ? `Call ended${startedAt ? ` · ${clock(elapsed)}` : ""}`
              : "The call couldn't start";

  return (
    <div className="space-y-4">
      <div className="flex flex-col items-center gap-4 rounded-lg border border-border bg-surface px-4 py-6 text-center">
        <div className="flex items-center gap-2 text-sm font-medium" aria-live="polite">
          <span
            aria-hidden
            className={cn(
              "inline-block h-2 w-2 rounded-full",
              phase === "live" ? "status-dot bg-emerald-500 text-emerald-500" : active ? "animate-pulse bg-amber-500" : phase === "error" ? "bg-destructive" : "bg-muted-foreground/50",
            )}
          />
          <span className="tabular-nums">{status}</span>
        </div>

        {active ? (
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button
              type="button"
              variant="destructive"
              className="h-12 rounded-full px-7 text-base"
              onClick={voice.hangUp}
              disabled={phase === "requesting"}
            >
              <PhoneOff className="h-5 w-5" aria-hidden />
              Hang up
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-12 rounded-full px-5"
              aria-pressed={muted}
              onClick={voice.toggleMute}
              disabled={phase !== "live"}
            >
              {muted ? <MicOff className="h-5 w-5 text-destructive" aria-hidden /> : <Mic className="h-5 w-5" aria-hidden />}
              {muted ? "Unmute" : "Mute"}
            </Button>
          </div>
        ) : (
          <Button type="button" className="h-12 rounded-full px-8 text-base" onClick={onStart} disabled={startDisabled}>
            <PhoneCall className="h-5 w-5" aria-hidden />
            {phase === "ended" || phase === "error" ? "Call again" : "Start call"}
          </Button>
        )}
        {phase === "requesting" && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden />
            Your browser may ask for microphone access — allow it.
          </p>
        )}
        {!active && startHint && <p className="text-xs text-muted-foreground">{startHint}</p>}

        <div className="w-full max-w-sm">
          <LevelMeter level={level} muted={muted} active={phase === "live"} />
        </div>
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Headphones className="h-3.5 w-3.5 shrink-0" aria-hidden />
          Use headphones to avoid echo.
        </p>
      </div>

      {error &&
        (error.kind === "api" ? (
          <div className="space-y-2">
            <ApiError message={error.message} />
            {/could not connect/i.test(error.message) && (
              <p className="text-xs text-muted-foreground">Check that the backend is running (localhost:8000 in development).</p>
            )}
          </div>
        ) : (
          <div role="alert" className="flex items-start gap-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
            <div className="min-w-0 space-y-1">
              <p className="font-medium text-destructive">
                {error.kind === "mic" ? "Microphone blocked" : error.kind === "insecure" ? "Microphone unavailable" : error.kind === "audio" ? "Audio problem" : "Call server unreachable"}
              </p>
              <p className="break-words text-muted-foreground">{error.message}</p>
              {(error.kind === "server" || error.kind === "dropped") && (
                <p className="text-muted-foreground">
                  Check that the backend is reachable (<code className="rounded bg-secondary px-1 font-mono text-xs">ws://localhost:8000</code> in development).
                </p>
              )}
            </div>
          </div>
        ))}
      {endedQuickly && !error && (
        <p className="flex items-start gap-2 rounded-md border border-border bg-surface p-3 text-xs text-muted-foreground">
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          The call ended right away. Check the backend{socketUrl ? ` at ${socketUrl}` : ""} and its logs.
        </p>
      )}

      <Conversation
        label="Call transcript"
        lines={lines}
        className="h-80"
        empty={
          active
            ? "Listening… the agent speaks first."
            : "The transcript appears here."
        }
      />
    </div>
  );
}
