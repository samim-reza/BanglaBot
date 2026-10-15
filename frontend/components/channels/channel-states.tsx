"use client";

/** One line per channel: in your plan, an add-on you have, available to add, or not offered. */

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import type { ChannelState } from "@/services/api";

const ANCHORS: Record<string, string> = { voice: "phone", web_chat: "web-chat", whatsapp: "whatsapp", messenger: "messenger", instagram: "instagram" };

function StateChip({ row }: { row: ChannelState }) {
  if (row.state === "included") return <Badge variant="success">In plan</Badge>;
  if (row.state === "addon") return <Badge variant="success">Add-on</Badge>;
  if (row.state === "available")
    return (
      <Link href={`/plan#${row.addon || row.channel}`} className="rounded-full bg-accent px-2.5 py-0.5 text-[12.5px] font-semibold text-accent-foreground hover:underline">
        Add{row.price_label ? ` · ${row.price_label}` : ""}
      </Link>
    );
  return <Badge variant="secondary">Not offered</Badge>;
}

export function ChannelStates({ rows }: { rows: ChannelState[] }) {
  if (!rows.length) return null;
  return (
    <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" aria-label="Channels">
      {rows.map((row) => (
        <li key={row.channel} className="flex items-center justify-between gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm">
          <a href={`#${ANCHORS[row.channel] ?? row.channel}`} className="truncate font-medium hover:underline">
            {row.label}
          </a>
          <StateChip row={row} />
        </li>
      ))}
    </ul>
  );
}
