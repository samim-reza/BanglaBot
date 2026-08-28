"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { OutcomeBadge } from "@/components/status-badge";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, formatDuration, humanize, languageLabel } from "@/lib/format";
import { adminApi, formatApiError, type CallLog, type Merchant } from "@/services/api";

const PAGE_SIZE = 25;

export default function AdminCallsPage() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [merchantId, setMerchantId] = useState("");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<CallLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    adminApi.merchants().then(setMerchants).catch(() => setMerchants([]));
  }, []);

  const load = useCallback(async () => {
    try {
      const result = await adminApi.calls({ merchant_id: merchantId, page, page_size: PAGE_SIZE });
      setItems(result.items);
      setTotal(result.total);
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load calls."));
    } finally {
      setLoading(false);
    }
  }, [merchantId, page]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <PageHeader title="Calls" subtitle="Every confirmation call the agent has placed. Click a row to read the transcript." />
      <ApiError message={error} />

      <Select
        className="sm:w-64"
        value={merchantId}
        onChange={(event) => {
          setMerchantId(event.target.value);
          setPage(1);
        }}
      >
        <option value="">All merchants</option>
        {merchants.map((merchant) => (
          <option key={merchant.id} value={merchant.id}>
            {merchant.business_name}
          </option>
        ))}
      </Select>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading calls…</p>
      ) : items.length === 0 ? (
        <EmptyState title="No calls yet" />
      ) : (
        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Started</TableHead>
                <TableHead>Merchant</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Twilio status</TableHead>
                <TableHead>Language</TableHead>
                <TableHead className="text-right">Duration</TableHead>
                <TableHead>Ended at</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((log) => {
                const open = expanded === log.id;
                return (
                  <Fragment key={log.id}>
                    <TableRow className="cursor-pointer" onClick={() => setExpanded(open ? null : log.id)}>
                      <TableCell className="text-muted-foreground">
                        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                      </TableCell>
                      <TableCell className="whitespace-nowrap">{formatDateTime(log.created_at)}</TableCell>
                      <TableCell className="font-medium">{log.merchant_name ?? "—"}</TableCell>
                      <TableCell>
                        <div>{log.customer_name ?? "—"}</div>
                        {log.order_ref && <div className="text-xs text-muted-foreground">Ref {log.order_ref}</div>}
                      </TableCell>
                      <TableCell>
                        <OutcomeBadge outcome={log.outcome} />
                      </TableCell>
                      <TableCell className="text-muted-foreground">{humanize(log.call_status)}</TableCell>
                      <TableCell>{languageLabel(log.language)}</TableCell>
                      <TableCell className="whitespace-nowrap text-right tabular-nums">{formatDuration(log.duration_secs)}</TableCell>
                      <TableCell className="text-muted-foreground">{humanize(log.final_node)}</TableCell>
                    </TableRow>
                    {open && (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={9} className="bg-surface">
                          <div className="grid gap-3 text-xs text-muted-foreground sm:grid-cols-3">
                            <div>
                              <span className="block uppercase tracking-wide">Call SID</span>
                              <span className="font-mono text-foreground">{log.twilio_call_sid ?? "—"}</span>
                            </div>
                            <div>
                              <span className="block uppercase tracking-wide">Recording SID</span>
                              <span className="font-mono text-foreground">{log.recording_sid ?? "—"}</span>
                            </div>
                            <div>
                              <span className="block uppercase tracking-wide">Order</span>
                              <span className="font-mono text-foreground">{log.order_id}</span>
                            </div>
                          </div>
                          {log.transcript ? (
                            <pre className="transcript mt-3 max-h-72 overflow-y-auto font-sans">
                              {log.transcript}
                            </pre>
                          ) : (
                            <p className="mt-3 text-sm text-muted-foreground">No transcript recorded.</p>
                          )}
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

      <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
    </div>
  );
}
