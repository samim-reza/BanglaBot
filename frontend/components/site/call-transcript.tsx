import { CircleCheck, MessageSquare, PhoneIncoming, PhoneOutgoing } from "lucide-react";

import type { ExampleConversation } from "@/lib/site-content";
import { cn } from "@/lib/utils";

const CHANNEL_ICON = {
  "Inbound call": PhoneIncoming,
  "Outbound call": PhoneOutgoing,
  "Website chat": MessageSquare,
} as const;

/** Decorative sound-wave bars for the call header. */
function Waveform({ className }: { className?: string }) {
  const bars = [6, 12, 18, 10, 16, 8, 14, 20, 12, 7, 15, 10];
  return (
    <svg viewBox="0 0 70 22" className={cn("h-5 w-16", className)} aria-hidden>
      {bars.map((height, index) => (
        <rect key={index} x={index * 6} y={(22 - height) / 2} width="3" height={height} rx="1.5" fill="currentColor" />
      ))}
    </svg>
  );
}

/** A stylised call transcript: who said what, and the outcome written to the records. */
export function CallTranscript({
  conversation,
  className,
  maxLines,
  live = false,
}: {
  conversation: ExampleConversation;
  className?: string;
  maxLines?: number;
  live?: boolean;
}) {
  const Icon = CHANNEL_ICON[conversation.channel];
  const lines = maxLines ? conversation.lines.slice(0, maxLines) : conversation.lines;
  return (
    <figure
      className={cn(
        "overflow-hidden rounded-2xl border border-border bg-card text-card-foreground shadow-[0_20px_50px_-24px_rgb(15_118_110/0.35)]",
        className,
      )}
    >
      <div className="flex items-center gap-3 border-b border-border bg-surface px-4 py-3">
        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{conversation.business}</p>
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            {live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" aria-hidden />}
            {conversation.channel} · AI agent
          </p>
        </div>
        <Waveform className="hidden text-tint-strong sm:block" />
      </div>
      <figcaption className="sr-only">
        Example {conversation.channel.toLowerCase()} for {conversation.business}
      </figcaption>
      <ol className="space-y-2.5 px-4 py-4">
        {lines.map((line, index) => (
          <li key={index} className={cn("flex", line.who === "caller" ? "justify-end" : "justify-start")}>
            <p
              className={cn(
                "max-w-[85%] rounded-2xl px-3.5 py-2 text-[13.5px] leading-relaxed",
                line.who === "agent"
                  ? "rounded-bl-md bg-accent text-foreground"
                  : "rounded-br-md bg-secondary text-secondary-foreground",
              )}
            >
              <span className="sr-only">{line.who === "agent" ? "Agent: " : "Caller: "}</span>
              {line.text}
            </p>
          </li>
        ))}
      </ol>
      <div className="flex items-start gap-2.5 border-t border-border bg-surface px-4 py-3">
        <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0 text-sm">
          <p className="font-semibold text-foreground">{conversation.result.label}</p>
          <p className="text-xs text-muted-foreground">{conversation.result.detail}</p>
        </div>
      </div>
    </figure>
  );
}
