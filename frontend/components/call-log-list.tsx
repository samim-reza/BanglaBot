"use client";

import { Bot, Clock3, Languages, MessageSquare, UserRound } from "lucide-react";

import { RecordingPlayer, type RecordingLoader } from "@/components/recording-player";
import { ChannelBadge, OutcomeBadge } from "@/components/status-badge";
import { formatDuration, humanize, languageLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { formatInZone } from "@/lib/vertical";
import type { CallLog } from "@/services/api";

/** Text channels (no audio, no meaningful duration). */
export const CHAT_CHANNELS = new Set(["widget", "chat"]);

export function isChatLog(log: Pick<CallLog, "direction">): boolean {
  return CHAT_CHANNELS.has(log.direction);
}

type Turn = { role: "agent" | "customer" | "note"; text: string };

const SPEAKER = /^\s*(agent|assistant|bot|customer|caller|visitor|user)\s*:\s?(.*)$/i;

/** "Agent: …" / "Customer: …" lines → turns; continuation lines join the previous turn. */
export function parseTranscript(transcript: string | null | undefined): Turn[] {
  const turns: Turn[] = [];
  for (const line of String(transcript ?? "").split(/\r?\n/)) {
    const match = line.match(SPEAKER);
    if (match) {
      const who = match[1].toLowerCase();
      const role: Turn["role"] = who === "agent" || who === "assistant" || who === "bot" ? "agent" : "customer";
      turns.push({ role, text: match[2] });
    } else if (turns.length) {
      turns[turns.length - 1].text += `\n${line}`;
    } else if (line.trim()) {
      turns.push({ role: "note", text: line });
    }
  }
  return turns
    .map((turn) => ({ ...turn, text: turn.text.trim() }))
    .filter((turn) => turn.text);
}

/** How long a conversation was: minutes for calls, message count for chats. */
export function conversationLength(log: CallLog): string {
  if (isChatLog(log)) {
    const count = parseTranscript(log.transcript).filter((turn) => turn.role !== "note").length;
    return count ? `${count} message${count === 1 ? "" : "s"}` : "—";
  }
  return log.duration_secs ? formatDuration(log.duration_secs) : "—";
}

/** A transcript rendered as a conversation: the agent on the left, the customer on the right. */
export function ConversationTranscript({ transcript, className }: { transcript: string | null | undefined; className?: string }) {
  const turns = parseTranscript(transcript);
  if (!turns.length) return <p className={cn("text-sm text-muted-foreground", className)}>No transcript recorded.</p>;
  return (
    <ol className={cn("space-y-2.5 rounded-lg border border-border bg-surface p-3 sm:p-4", className)} aria-label="Transcript">
      {turns.map((turn, index) => {
        if (turn.role === "note") {
          return (
            <li key={index} className="text-center text-xs text-muted-foreground">
              {turn.text}
            </li>
          );
        }
        const agent = turn.role === "agent";
        return (
          <li key={index} className={cn("flex items-end gap-2", agent ? "justify-start" : "flex-row-reverse")}>
            <span
              className={cn(
                "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                agent ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground",
              )}
              aria-hidden="true"
            >
              {agent ? <Bot className="h-3.5 w-3.5" /> : <UserRound className="h-3.5 w-3.5" />}
            </span>
            <div
              className={cn(
                "max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-sm leading-relaxed sm:max-w-[75%]",
                agent ? "rounded-bl-sm bg-card text-foreground ring-1 ring-border" : "rounded-br-sm bg-accent text-foreground",
              )}
            >
              <span className="sr-only">{agent ? "Agent: " : "Customer: "}</span>
              {turn.text}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const number = (value: number) => value.toLocaleString("en-US");

/** Small technical usage line (LLM tokens, cached tokens, TTS characters, cache hits). */
export function CallTechStats({ log, className }: { log: CallLog; className?: string }) {
  const parts: string[] = [];
  if (log.llm_prompt_tokens || log.llm_completion_tokens) {
    parts.push(
      `LLM ${number(log.llm_prompt_tokens)} in${log.llm_cached_tokens ? ` (${number(log.llm_cached_tokens)} cached)` : ""} / ${number(log.llm_completion_tokens)} out`,
    );
  }
  if (log.tts_chars) parts.push(`TTS ${number(log.tts_chars)} chars`);
  if (log.tts_cache_hits) parts.push(`${number(log.tts_cache_hits)} voice cache hit${log.tts_cache_hits === 1 ? "" : "s"}`);
  if (log.final_node) parts.push(`ended at ${humanize(log.final_node).toLowerCase()}`);
  if (!parts.length) return null;
  return <p className={cn("text-[11.5px] leading-relaxed text-muted-foreground", className)}>{parts.join(" · ")}</p>;
}

/** Every call and chat about one record, newest first, with transcript and recording. */
export function CallLogList({
  logs,
  withRecordings = true,
  timezone,
  emptyText = "No calls or chats about this record yet.",
  loadRecording,
}: {
  logs: CallLog[];
  withRecordings?: boolean;
  timezone?: string;
  emptyText?: string;
  loadRecording?: RecordingLoader;
}) {
  if (!logs.length) {
    return <p className="text-sm text-muted-foreground">{emptyText}</p>;
  }
  const ordered = [...logs].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  return (
    <ol className="space-y-4">
      {ordered.map((log) => {
        const chat = isChatLog(log);
        return (
          <li key={log.id} className="rounded-lg border border-border bg-card p-3 sm:p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <ChannelBadge direction={log.direction} />
                <OutcomeBadge outcome={log.outcome} callStatus={log.call_status} />
              </div>
              <time className="text-xs text-muted-foreground" dateTime={log.created_at}>
                {formatInZone(log.created_at, timezone)}
              </time>
            </div>
            <dl className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
              <div className="inline-flex items-center gap-1.5">
                {chat ? <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" /> : <Clock3 className="h-3.5 w-3.5" aria-hidden="true" />}
                <dt className="sr-only">{chat ? "Messages" : "Duration"}</dt>
                <dd>{conversationLength(log)}</dd>
              </div>
              {log.language && (
                <div className="inline-flex items-center gap-1.5">
                  <Languages className="h-3.5 w-3.5" aria-hidden="true" />
                  <dt className="sr-only">Language</dt>
                  <dd>{languageLabel(log.language)}</dd>
                </div>
              )}
              {log.caller_number && (
                <div className="inline-flex items-center gap-1.5 tabular-nums">
                  <dt className="sr-only">Number</dt>
                  <dd>{log.caller_number}</dd>
                </div>
              )}
            </dl>
            <ConversationTranscript transcript={log.transcript} className="mt-3 max-h-80 overflow-y-auto" />
            {withRecordings && log.recording_sid && (
              <div className="mt-3">
                <RecordingPlayer logId={log.id} load={loadRecording} />
              </div>
            )}
            <CallTechStats log={log} className="mt-2" />
          </li>
        );
      })}
    </ol>
  );
}
