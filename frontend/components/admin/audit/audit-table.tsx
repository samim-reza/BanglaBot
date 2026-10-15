"use client";

import Link from "next/link";

import { Pill, type Tone } from "@/components/admin/badges";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import type { AuditEvent } from "@/services/api/admin/audit";

const ACTOR_TONES: Record<string, Tone> = { admin: "violet", merchant: "teal", system: "neutral" };
const ACTOR_LABELS: Record<string, string> = { admin: "Admin", merchant: "Owner", system: "System" };

export function ActorCell({ event, names }: { event: AuditEvent; names: Map<string, string> }) {
  const name = event.actor_type === "merchant" ? names.get(event.actor_id) : undefined;
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <Pill tone={ACTOR_TONES[event.actor_type] ?? "neutral"} className="px-2 py-0 text-[11px]">
        {ACTOR_LABELS[event.actor_type] ?? event.actor_type}
      </Pill>
      <span className="truncate font-mono text-xs" title={event.actor_id}>
        {name ?? (event.actor_id || "—")}
      </span>
    </span>
  );
}

/** Newest first; a row opens its details. */
export function AuditTable({ items, names, onOpen }: { items: AuditEvent[]; names: Map<string, string>; onOpen: (event: AuditEvent) => void }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>When</TableHead>
            <TableHead>Actor</TableHead>
            <TableHead>Action</TableHead>
            <TableHead>Target</TableHead>
            <TableHead>Account</TableHead>
            <TableHead>IP</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((event) => (
            <TableRow
              key={event.id}
              className="cursor-pointer"
              tabIndex={0}
              onClick={(e) => !(e.target as HTMLElement).closest("a") && onOpen(event)}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen(event))}
              aria-label={`${event.action} — details`}
            >
              <TableCell className="whitespace-nowrap">{formatDateTime(event.at)}</TableCell>
              <TableCell className="max-w-[14rem]">
                <ActorCell event={event} names={names} />
              </TableCell>
              <TableCell className="whitespace-nowrap font-mono text-xs font-semibold">{event.action}</TableCell>
              <TableCell className="max-w-[12rem] truncate text-xs text-muted-foreground" title={`${event.target_type} ${event.target_id}`}>
                {event.target_type ? `${event.target_type} · ${event.target_id}` : "—"}
              </TableCell>
              <TableCell className="max-w-[12rem] truncate">
                {event.merchant_id ? (
                  <Link href={`/admin/merchants/${event.merchant_id}`} className="hover:text-primary hover:underline">
                    {names.get(event.merchant_id) ?? event.merchant_id}
                  </Link>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">{event.ip || "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
