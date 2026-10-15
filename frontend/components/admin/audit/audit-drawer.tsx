"use client";

import { Overlay } from "@/components/admin/overlay";
import { formatDateTime } from "@/lib/format";
import type { AuditEvent } from "@/services/api/admin/audit";

import { ActorCell } from "./audit-table";

/** One event in full, with its meta as JSON. */
export function AuditDrawer({ event, names, onClose }: { event: AuditEvent | null; names: Map<string, string>; onClose: () => void }) {
  const rows: [string, React.ReactNode][] = event
    ? [
        ["When", formatDateTime(event.at)],
        ["Actor", <ActorCell key="actor" event={event} names={names} />],
        ["Actor id", <span key="id" className="break-all font-mono text-xs">{event.actor_id || "—"}</span>],
        ["Target", event.target_type ? `${event.target_type} · ${event.target_id}` : "—"],
        ["Account", event.merchant_id ? names.get(event.merchant_id) ?? event.merchant_id : "—"],
        ["IP", event.ip || "—"],
        ["Event id", <span key="eid" className="break-all font-mono text-xs">{event.id}</span>],
      ]
    : [];
  return (
    <Overlay open={Boolean(event)} onClose={onClose} variant="drawer" title={<span className="font-mono text-base">{event?.action}</span>}>
      <dl className="space-y-2 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[6rem_1fr] gap-3">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="min-w-0 break-words">{value}</dd>
          </div>
        ))}
      </dl>
      <h3 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Meta</h3>
      <pre className="overflow-x-auto rounded-md border border-border bg-surface p-3 font-mono text-xs leading-relaxed">
        {event && Object.keys(event.meta ?? {}).length ? JSON.stringify(event.meta, null, 2) : "—"}
      </pre>
    </Overlay>
  );
}
