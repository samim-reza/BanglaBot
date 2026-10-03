"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronDown, ExternalLink } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { CallTechStats, ConversationTranscript, callerName, channelIcon, conversationLength } from "@/components/call-log-list";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { RecordingPlayer } from "@/components/recording-player";
import { OutcomeBadge } from "@/components/status-badge";
import { Select } from "@/components/ui/select";
import { languageLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { channelLabel, formatInZone, outcomeLabel, t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { callsApi, formatApiError, type CallChannel, type CallLog, type ChannelKey } from "@/services/api";

const PAGE_SIZE = 20;

/** Filter chips; `channel` = the plan channel the chip needs (tests are always shown). */
const CHANNELS: { value: CallChannel | ""; label: string; channel?: ChannelKey }[] = [
  { value: "", label: "All" },
  { value: "inbound", label: "Inbound calls", channel: "voice" },
  { value: "outbound", label: "Outbound calls", channel: "voice" },
  { value: "widget", label: "Website chat", channel: "web_chat" },
  { value: "whatsapp", label: "WhatsApp", channel: "whatsapp" },
  { value: "messenger", label: "Messenger", channel: "messenger" },
  { value: "web", label: "Browser tests" },
  { value: "chat", label: "Chat tests" },
];

/** Outcomes the agent records, for the filter (labels come from the shared helper). */
const OUTCOMES = [
  "confirmed",
  "booked",
  "rescheduled",
  "cancelled",
  "lead",
  "inquiry",
  "not_interested",
  "relay",
  "transfer",
  "emergency",
  "wrong_number",
  "unclear",
  "voicemail",
  "diverted",
  "auto_dropped",
];

function CallRow({ log, timezone, recordLabel }: { log: CallLog; timezone: string; recordLabel: string }) {
  const [open, setOpen] = useState(false);
  const Icon = channelIcon(log.direction);
  const panelId = `call-${log.id}`;
  return (
    <li className="rounded-lg border border-border bg-card">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-start gap-3 rounded-lg p-3 text-left transition hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:items-center sm:p-4"
      >
        <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground sm:mt-0" aria-hidden="true">
          <Icon className="h-4 w-4" />
        </span>
        <span className="grid min-w-0 flex-1 gap-1 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto] sm:items-center sm:gap-4">
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">{callerName(log)}</span>
            <span className="block truncate text-xs text-muted-foreground">
              {channelLabel(log.direction)}
              {log.customer_name && log.caller_number ? ` · ${log.caller_number}` : ""}
            </span>
          </span>
          <span className="flex flex-wrap items-center gap-2">
            <OutcomeBadge outcome={log.outcome} callStatus={log.call_status} />
            <span className="text-xs tabular-nums text-muted-foreground">{conversationLength(log)}</span>
          </span>
          <time className="text-xs text-muted-foreground sm:text-right" dateTime={log.created_at}>
            {formatInZone(log.created_at, timezone)}
          </time>
        </span>
        <ChevronDown className={cn("mt-2 h-4 w-4 shrink-0 text-muted-foreground transition-transform sm:mt-0", open && "rotate-180")} aria-hidden="true" />
      </button>
      {open && (
        <div id={panelId} className="space-y-3 border-t border-border px-3 pb-4 pt-3 sm:px-4">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted-foreground">
            {log.order_id ? (
              <Link href={`/orders/${log.order_id}`} className="inline-flex items-center gap-1 font-medium text-primary-dark hover:underline">
                Open {recordLabel.toLowerCase()}
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </Link>
            ) : (
              <span>No {recordLabel.toLowerCase()} linked</span>
            )}
            {log.language && <span>{languageLabel(log.language)}</span>}
          </div>
          <ConversationTranscript transcript={log.transcript} className="max-h-96 overflow-y-auto" />
          {log.recording_sid && <RecordingPlayer logId={log.id} load={callsApi.recordingObjectUrl} />}
          <CallTechStats log={log} />
        </div>
      )}
    </li>
  );
}

export default function CallsPage() {
  const { vertical, merchant, entitlements } = useWorkspace();
  const recordLabel = t(vertical.record_label, "Record");
  const [items, setItems] = useState<CallLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [direction, setDirection] = useState<CallChannel | "">("");
  const [outcome, setOutcome] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await callsApi.list({ page, page_size: PAGE_SIZE, direction, outcome });
      setItems(result.items);
      setTotal(result.total);
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load calls and chats."));
    } finally {
      setLoading(false);
    }
  }, [page, direction, outcome]);

  useEffect(() => {
    void load();
  }, [load]);

  // Channels the account doesn't run are hidden from the filter (the selected one always stays).
  const channels = CHANNELS.filter((channel) => {
    if (channel.value === direction) return true;
    if (channel.channel && !entitlements.channels.includes(channel.channel)) return false;
    return !(channel.value === "inbound" || channel.value === "outbound") || vertical.directions.includes(channel.value);
  });
  const filtered = Boolean(direction || outcome);

  return (
    <div className="space-y-6">
      <PageHeader title="Calls & chats" subtitle="Every conversation your agent has had." />
      <ApiError message={error} />

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div role="group" aria-label="Channel" className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 lg:flex-wrap lg:overflow-visible lg:pb-0">
          {channels.map((channel) => {
            const active = direction === channel.value;
            return (
              <button
                key={channel.value || "all"}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  setDirection(channel.value);
                  setPage(1);
                }}
                className={cn(
                  "h-9 shrink-0 whitespace-nowrap rounded-full border px-3.5 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  active ? "border-primary bg-accent text-accent-foreground" : "border-border bg-card text-muted-foreground hover:bg-secondary hover:text-foreground",
                )}
              >
                {channel.label}
              </button>
            );
          })}
        </div>
        <Select
          aria-label="Filter by outcome"
          className="lg:w-52"
          value={outcome}
          onChange={(event) => {
            setOutcome(event.target.value);
            setPage(1);
          }}
        >
          <option value="">All outcomes</option>
          {OUTCOMES.map((value) => (
            <option key={value} value={value}>
              {outcomeLabel(value)}
            </option>
          ))}
        </Select>
      </div>

      {loading && items.length === 0 ? (
        <div className="space-y-2" role="status" aria-label="Loading calls and chats">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="h-[68px] animate-pulse rounded-lg bg-secondary" />
          ))}
        </div>
      ) : items.length === 0 ? (
        error ? null : (
          <EmptyState title={filtered ? "Nothing matches these filters" : "No calls or chats yet"}>
            {filtered ? (
              <button
                type="button"
                className="font-medium text-primary-dark hover:underline"
                onClick={() => {
                  setDirection("");
                  setOutcome("");
                  setPage(1);
                }}
              >
                Clear filters
              </button>
            ) : (
              <Link href="/test" className="font-medium text-primary-dark hover:underline">
                Test your agent
              </Link>
            )}
          </EmptyState>
        )
      ) : (
        <ol className={cn("space-y-2 transition-opacity", loading && "opacity-60")} aria-busy={loading}>
          {items.map((log) => (
            <CallRow key={log.id} log={log} timezone={merchant.timezone} recordLabel={recordLabel} />
          ))}
        </ol>
      )}

      {total > 0 && <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />}
    </div>
  );
}
