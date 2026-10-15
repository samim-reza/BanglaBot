"use client";

import Link from "next/link";
import { PhoneIncoming, PhoneOff, PhoneOutgoing } from "lucide-react";

import { Pill } from "@/components/admin/badges";
import { fmtClock } from "@/components/admin/numbers";
import { verticalName, useAdminMeta } from "@/components/admin/use-admin-meta";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { humanize, languageLabel } from "@/lib/format";
import type { LiveCall } from "@/services/api/admin/system";

export function LiveCallsTable({
  items,
  elapsed,
  canHangUp,
  onHangUp,
}: {
  items: LiveCall[];
  elapsed: number;
  canHangUp: boolean;
  onHangUp: (call: LiveCall) => void;
}) {
  const { meta } = useAdminMeta();
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Account</TableHead>
            <TableHead>Caller</TableHead>
            <TableHead className="text-right">Time</TableHead>
            <TableHead>Stage</TableHead>
            <TableHead>Language</TableHead>
            <TableHead>Models</TableHead>
            {canHangUp && (
              <TableHead className="w-24">
                <span className="sr-only">Actions</span>
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((call) => {
            const DirectionIcon = call.direction === "outbound" ? PhoneOutgoing : PhoneIncoming;
            return (
              <TableRow key={call.call_log_id}>
                <TableCell className="min-w-[10rem]">
                  {call.merchant_id ? (
                    <Link href={`/admin/merchants/${call.merchant_id}`} className="font-medium hover:text-primary hover:underline">
                      {call.business || "Unknown account"}
                    </Link>
                  ) : (
                    <span className="font-medium">{call.business || "—"}</span>
                  )}
                  <div className="text-xs text-muted-foreground">{verticalName(meta, call.vertical)}</div>
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  <span className="inline-flex items-center gap-1.5">
                    <DirectionIcon className="h-3.5 w-3.5 text-muted-foreground" aria-label={call.direction === "outbound" ? "Outbound" : "Inbound"} />
                    <span className="font-mono text-xs">{call.caller || "—"}</span>
                  </span>
                </TableCell>
                <TableCell className="whitespace-nowrap text-right font-mono tabular-nums">{fmtClock(call.seconds + elapsed)}</TableCell>
                <TableCell className="whitespace-nowrap">
                  {call.closing ? <Pill tone="amber">Ending</Pill> : <span>{call.stage ? humanize(call.stage) : "—"}</span>}
                </TableCell>
                <TableCell className="whitespace-nowrap">{call.language ? languageLabel(call.language) : "—"}</TableCell>
                <TableCell className="min-w-[10rem]">
                  <div className="truncate font-mono text-xs" title={call.llm}>
                    {call.llm || "—"}
                  </div>
                  <div className="truncate font-mono text-xs text-muted-foreground" title="Speech-to-text">
                    {call.stt || "—"}
                  </div>
                </TableCell>
                {canHangUp && (
                  <TableCell className="text-right">
                    <Button variant="outline" size="sm" className="text-destructive hover:text-destructive" disabled={call.closing} onClick={() => onHangUp(call)}>
                      <PhoneOff className="h-3.5 w-3.5" />
                      Hang up
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
