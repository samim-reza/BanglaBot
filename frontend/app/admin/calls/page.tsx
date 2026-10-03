"use client";

import { Fragment, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, X } from "lucide-react";

import { AdminRecordingPlayer } from "@/components/admin/admin-recording";
import { OutcomePill } from "@/components/admin/badges";
import { FilterBar, LoadingRows } from "@/components/admin/states";
import { pageFrom, useUrlFilters } from "@/components/admin/url-filters";
import { useAdminMerchants } from "@/components/admin/use-admin-meta";
import { ApiError } from "@/components/api-error";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, formatDuration, humanize, languageLabel } from "@/lib/format";
import { channelLabel } from "@/lib/vertical";
import { adminApi, formatApiError, type CallChannel, type CallLog, type Merchant } from "@/services/api";

const PAGE_SIZE = 25;
const FILTER_KEYS = ["merchant_id", "direction", "page"] as const;
const CHANNELS: CallChannel[] = ["outbound", "inbound", "widget", "whatsapp", "messenger", "web", "chat"];
const CHAT_APPS: Record<string, string> = { whatsapp: "WhatsApp", messenger: "Messenger" };
const sourceLabel = (direction: string | null | undefined) => CHAT_APPS[direction ?? ""] ?? channelLabel(direction);
const VOICE: string[] = ["outbound", "inbound", "web"];

export default function AdminCallsPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading calls and chats…" />}>
      <CallsView />
    </Suspense>
  );
}

function CallsView() {
  const { merchants } = useAdminMerchants();
  const [filters, setFilters] = useUrlFilters(FILTER_KEYS);
  const merchantId = filters.merchant_id;
  const direction = (CHANNELS as string[]).includes(filters.direction) ? (filters.direction as CallChannel) : "";
  const page = pageFrom(filters.page);

  const [items, setItems] = useState<CallLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const byId = useMemo(() => new Map<string, Merchant>(merchants.map((merchant) => [merchant.id, merchant])), [merchants]);
  const selected = merchantId ? byId.get(merchantId) ?? null : null;

  const load = useCallback(async () => {
    try {
      const result = await adminApi.calls({ merchant_id: merchantId, direction, page, page_size: PAGE_SIZE });
      setItems(result.items);
      setTotal(result.total);
      setError(null);
    } catch (err) {
      setItems([]);
      setTotal(0);
      setError(formatApiError(err, "Could not load calls and chats."));
    } finally {
      setLoading(false);
    }
  }, [merchantId, direction, page]);

  useEffect(() => {
    setLoading(true);
    setExpanded(null);
    void load();
  }, [load]);

  const filtered = Boolean(merchantId || direction);
  const toggle = (id: string) => setExpanded((current) => (current === id ? null : id));

  return (
    <>
      <PageHeader
        title={selected ? `Calls & chats · ${selected.business_name}` : "Calls & chats"}
        subtitle="Every phone call, test call and website chat the agents have handled. Expand a row for the transcript and recording."
      />
      <ApiError message={error} />

      <FilterBar label="Filter calls and chats">
        <Select className="sm:w-64" aria-label="Account" value={merchantId} onChange={(event) => setFilters({ merchant_id: event.target.value, page: null })}>
          <option value="">All accounts</option>
          {merchantId && !selected && <option value={merchantId}>Selected account</option>}
          {merchants.map((merchant) => (
            <option key={merchant.id} value={merchant.id}>
              {merchant.business_name}
            </option>
          ))}
        </Select>
        <Select className="sm:w-52" aria-label="Channel" value={direction} onChange={(event) => setFilters({ direction: event.target.value, page: null })}>
          <option value="">All channels</option>
          {CHANNELS.map((value) => (
            <option key={value} value={value}>
              {sourceLabel(value)}
            </option>
          ))}
        </Select>
        {filtered && (
          <Button variant="ghost" size="sm" onClick={() => setFilters({ merchant_id: null, direction: null, page: null })}>
            <X className="h-3.5 w-3.5" />
            Clear filters
          </Button>
        )}
        {selected && (
          <Link href={`/admin/merchants/${selected.id}`} className="text-sm font-medium text-primary hover:underline sm:ml-auto">
            View account
          </Link>
        )}
      </FilterBar>

      {loading && items.length === 0 ? (
        <LoadingRows label="Loading calls and chats…" />
      ) : items.length === 0 ? (
        error ? null : (
          <EmptyState title={filtered ? "Nothing matches" : "No calls or chats yet"}>
            {filtered ? "Try another account or channel." : "Conversations appear here as soon as an agent handles one."}
          </EmptyState>
        )
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-card" aria-busy={loading}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <span className="sr-only">Details</span>
                </TableHead>
                <TableHead>When</TableHead>
                <TableHead>Account</TableHead>
                <TableHead>Channel</TableHead>
                <TableHead>Customer / caller</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead className="text-right">Duration</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((log) => {
                const open = expanded === log.id;
                const detailId = `call-${log.id}`;
                const accountId = log.merchant_id ?? "";
                const voice = VOICE.includes(log.direction);
                return (
                  <Fragment key={log.id}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={(event) => {
                        // Links and buttons inside the row keep their own behaviour.
                        if ((event.target as HTMLElement).closest("a, button")) return;
                        toggle(log.id);
                      }}
                    >
                      <TableCell className="py-1.5">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          aria-expanded={open}
                          aria-controls={detailId}
                          aria-label={open ? "Hide transcript" : "Show transcript"}
                          onClick={() => toggle(log.id)}
                        >
                          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </Button>
                      </TableCell>
                      <TableCell className="whitespace-nowrap">{formatDateTime(log.created_at)}</TableCell>
                      <TableCell className="min-w-[9rem]">
                        {accountId ? (
                          <Link href={`/admin/merchants/${accountId}`} className="font-medium hover:text-primary hover:underline">
                            {log.merchant_name || byId.get(accountId)?.business_name || "Unknown account"}
                          </Link>
                        ) : (
                          <span className="font-medium">{log.merchant_name || "—"}</span>
                        )}
                      </TableCell>
                      <TableCell className="whitespace-nowrap">{sourceLabel(log.direction)}</TableCell>
                      <TableCell className="min-w-[9rem]">
                        <div>{log.customer_name || (log.direction === "widget" ? "Website visitor" : "—")}</div>
                        {log.caller_number && <div className="font-mono text-xs text-muted-foreground">{log.caller_number}</div>}
                        {log.order_ref && <div className="text-xs text-muted-foreground">Ref {log.order_ref}</div>}
                      </TableCell>
                      <TableCell>
                        <OutcomePill outcome={log.outcome} />
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-right tabular-nums">{voice ? formatDuration(log.duration_secs) : "—"}</TableCell>
                    </TableRow>
                    {open && (
                      <TableRow id={detailId} className="hover:bg-transparent">
                        <TableCell colSpan={7} className="bg-surface">
                          <CallDetail log={log} />
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {total > 0 && <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={(next) => setFilters({ page: next })} />}
    </>
  );
}

function CallDetail({ log }: { log: CallLog }) {
  const facts: [string, React.ReactNode][] = [
    ["Language", languageLabel(log.language)],
    ["Call status", humanize(log.call_status)],
    ["Ended at", humanize(log.final_node)],
    ["Call SID", log.twilio_call_sid ? <span className="break-all font-mono">{log.twilio_call_sid}</span> : "—"],
  ];
  const tokens = (log.llm_prompt_tokens || 0) + (log.llm_completion_tokens || 0);
  if (tokens) facts.push(["LLM tokens", tokens.toLocaleString("en-US")]);
  if (log.tts_chars) facts.push(["TTS characters", `${log.tts_chars.toLocaleString("en-US")} (${log.tts_cache_hits} cached)`]);

  return (
    <div className="max-w-[calc(100vw-4rem)] space-y-3 py-1 sm:max-w-none">
      <dl className="grid gap-x-6 gap-y-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
        {facts.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
            <dd className="mt-0.5 text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
      {log.recording_sid && <AdminRecordingPlayer logId={log.id} />}
      {log.transcript ? (
        <pre className="transcript max-h-80 overflow-y-auto whitespace-pre-wrap break-words font-sans">{log.transcript}</pre>
      ) : (
        <p className="text-sm text-muted-foreground">No transcript recorded.</p>
      )}
    </div>
  );
}
