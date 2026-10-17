"use client";

/** One "Hear it" sample call: play/pause, a waveform you can scrub, duration and a transcript that follows the audio. */

import { useId, useRef, useState } from "react";
import { ChevronDown, CircleCheck, LoaderCircle, Pause, Phone, Play, TriangleAlert } from "lucide-react";

import { assetPath } from "@/lib/paths";
import { agentByKey } from "@/lib/site/agents";
import type { SampleCall } from "@/lib/site/types";
import { cn } from "@/lib/utils";

/** Only one sample plays at a time across the page. */
let playingNow: HTMLAudioElement | null = null;

function clock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Index of the line being spoken at `time` (-1 before the first). */
function lineAt(call: SampleCall, time: number): number {
  let index = -1;
  call.lines.forEach((line, i) => {
    if (line.at <= time + 0.05) index = i;
  });
  return index;
}

function Waveform({ call, duration, time }: { call: SampleCall; duration: number; time: number }) {
  const count = call.peaks.length;
  return (
    <svg viewBox={`0 0 ${count * 5} 40`} preserveAspectRatio="none" className="h-10 w-full" aria-hidden>
      {call.peaks.map((peak, index) => {
        const start = (index / count) * duration;
        const who = call.lines[lineAt(call, start + duration / count / 2)]?.who ?? "agent";
        const height = Math.max(3, peak * 38);
        return (
          <rect
            key={index}
            x={index * 5 + 1}
            y={(40 - height) / 2}
            width={3}
            height={height}
            rx={1.5}
            className={cn(who === "agent" ? "fill-primary" : "fill-muted-foreground", start < time ? "opacity-100" : "opacity-30")}
          />
        );
      })}
    </svg>
  );
}

export function SampleCallCard({ call, defaultOpen = false, className }: { call: SampleCall; defaultOpen?: boolean; className?: string }) {
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(call.duration);
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const Icon = agentByKey(call.vertical)?.icon ?? Phone;
  const current = time > 0 || playing ? lineAt(call, time) : -1;

  const play = (from?: number) => {
    const el = audio.current;
    if (!el) return;
    if (from !== undefined) {
      el.currentTime = from;
      setTime(from);
    }
    setFailed(false);
    if (el.readyState < HTMLMediaElement.HAVE_FUTURE_DATA) setLoading(true);
    el.play().catch((err: unknown) => {
      if (!(err instanceof DOMException && err.name === "AbortError")) setFailed(true);
      setLoading(false);
    });
  };

  const toggle = () => {
    const el = audio.current;
    if (el && !el.paused) el.pause();
    else play();
  };

  const seek = (value: number) => {
    if (audio.current) audio.current.currentTime = value;
    setTime(value);
  };

  return (
    <article className={cn("flex flex-col rounded-2xl border border-border bg-card p-5 text-card-foreground shadow-[0_20px_50px_-30px_rgb(15_118_110/0.35)]", className)}>
      <header className="flex items-start gap-3">
        <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-foreground">
          <Icon className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h3 id={`${id}-title`} className="font-semibold text-foreground">
            {call.title}
          </h3>
          <p className="truncate text-sm text-muted-foreground">{call.business}</p>
        </div>
        <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-xs font-medium tabular-nums text-secondary-foreground">
          <span className="sr-only">Length </span>
          {clock(duration)}
        </span>
      </header>

      <div className="mt-5 flex items-center gap-3">
        <button
          type="button"
          onClick={toggle}
          aria-label={`${playing ? "Pause" : "Play"} sample call: ${call.title}`}
          className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm transition-colors hover:bg-primary-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
        >
          {loading ? (
            <LoaderCircle className="h-5 w-5 animate-spin" aria-hidden />
          ) : playing ? (
            <Pause className="h-5 w-5" fill="currentColor" aria-hidden />
          ) : (
            <Play className="ml-0.5 h-5 w-5" fill="currentColor" aria-hidden />
          )}
        </button>
        <div className="min-w-0 flex-1">
          <div className="relative rounded-md focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-card">
            <Waveform call={call} duration={duration} time={time} />
            <input
              type="range"
              min={0}
              max={duration}
              step={1}
              value={Math.min(time, duration)}
              onChange={(event) => seek(Number(event.target.value))}
              aria-label={`Seek in ${call.title}`}
              aria-valuetext={`${clock(time)} of ${clock(duration)}`}
              className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
            />
          </div>
          <p className="mt-1 flex justify-between text-[11px] tabular-nums text-muted-foreground" aria-hidden>
            <span>{clock(time)}</span>
            <span className="flex items-center gap-3">
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-primary" />
                Agent
              </span>
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-muted-foreground" />
                Caller
              </span>
            </span>
          </p>
        </div>
      </div>

      {failed && (
        <p role="alert" className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
          <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden />
          The audio couldn&apos;t play. Try again, or read the transcript.
        </p>
      )}

      <p className="mt-4 flex items-start gap-2 text-sm font-medium text-foreground">
        <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
        {call.result}
      </p>

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={`${id}-transcript`}
        className="mt-4 inline-flex items-center gap-1.5 self-start rounded-sm text-sm font-semibold text-primary-dark hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {open ? "Hide transcript" : "Show transcript"}
        <ChevronDown className={cn("h-4 w-4 transition-transform motion-reduce:transition-none", open && "rotate-180")} aria-hidden />
      </button>

      <ol id={`${id}-transcript`} hidden={!open} aria-label={`Transcript: ${call.title}`} className="mt-3 space-y-2 border-t border-border pt-4">
        {call.lines.map((line, index) => (
          <li key={index} className={cn("flex", line.who === "caller" ? "justify-end" : "justify-start")}>
            <button
              type="button"
              onClick={() => play(line.at)}
              aria-current={index === current ? "true" : undefined}
              title={`Play from ${clock(line.at)}`}
              className={cn(
                "max-w-[88%] rounded-2xl px-3 py-1.5 text-left text-[13px] leading-relaxed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
                line.who === "agent" ? "rounded-bl-md bg-accent text-foreground" : "rounded-br-md bg-secondary text-secondary-foreground",
                index === current && "ring-2 ring-primary/60",
              )}
            >
              <span className="sr-only">{line.who === "agent" ? "Agent: " : "Caller: "}</span>
              {line.text}
            </button>
          </li>
        ))}
      </ol>

      <audio
        ref={audio}
        src={assetPath(call.src)}
        preload="none"
        onPlay={(event) => {
          if (playingNow && playingNow !== event.currentTarget) playingNow.pause();
          playingNow = event.currentTarget;
          setPlaying(true);
        }}
        onPause={() => {
          setPlaying(false);
          setLoading(false);
        }}
        onEnded={() => {
          setPlaying(false);
          setTime(0);
        }}
        onWaiting={() => setLoading(true)}
        onPlaying={() => setLoading(false)}
        onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
        onLoadedMetadata={(event) => Number.isFinite(event.currentTarget.duration) && setDuration(event.currentTarget.duration)}
        onError={() => {
          setFailed(true);
          setPlaying(false);
          setLoading(false);
        }}
      />
    </article>
  );
}
