"use client";

/** Dashboard list rows: an upcoming / recent record and a recent call or chat. */

import Link from "next/link";

import { callerName, channelIcon, conversationLength } from "@/components/call-log-list";
import { OrderStatusBadge, OutcomeBadge } from "@/components/status-badge";
import { formatPhone } from "@/lib/format";
import { channelLabel, formatInZone } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import type { CallLog, Order } from "@/services/api";

const ROW = "flex items-center gap-3 rounded-md px-2 py-2.5 transition hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function RecordRow({ order, scheduled }: { order: Order; scheduled: boolean }) {
  const { vertical, merchant } = useWorkspace();
  const detail = order.summary || order.catalog_item_name || formatPhone(order.customer_phone);
  return (
    <li>
      <Link href={`/orders/${order.id}`} className={ROW}>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{order.customer_name}</p>
          <p className="truncate text-xs text-muted-foreground">
            {scheduled && order.scheduled_at ? `${formatInZone(order.scheduled_at, merchant.timezone)} · ` : ""}
            {detail}
          </p>
        </div>
        <OrderStatusBadge status={order.status} spec={vertical} className="shrink-0" />
      </Link>
    </li>
  );
}

export function CallRow({ log }: { log: CallLog }) {
  const { merchant } = useWorkspace();
  const Icon = channelIcon(log.direction);
  return (
    <li>
      <Link href={log.order_id ? `/orders/${log.order_id}` : "/calls"} className={ROW}>
        <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground" aria-hidden="true">
          <Icon className="h-3.5 w-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{callerName(log)}</p>
          <p className="truncate text-xs text-muted-foreground">
            {channelLabel(log.direction)} · {conversationLength(log)} · {formatInZone(log.created_at, merchant.timezone)}
          </p>
        </div>
        <OutcomeBadge outcome={log.outcome} callStatus={log.call_status} className="shrink-0" />
      </Link>
    </li>
  );
}
