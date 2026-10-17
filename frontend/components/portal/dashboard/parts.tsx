"use client";

/** Small building blocks of the owner dashboard: a titled card, "View all", loading rows, a stat tile. */

import Link from "next/link";
import { ArrowRight, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle>{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function ViewAll({ href }: { href: string }) {
  return (
    <Button asChild variant="ghost" size="sm">
      <Link href={href}>
        View all
        <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
      </Link>
    </Button>
  );
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="h-12 animate-pulse rounded-md bg-secondary" />
      ))}
    </div>
  );
}

export function SkeletonTiles({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" role="status" aria-label="Loading">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="h-[88px] animate-pulse rounded-lg bg-secondary" />
      ))}
    </div>
  );
}

const TILE = "block rounded-lg border border-border bg-card p-4";

/** One number with its label; a link when ``href`` is given. */
export function StatTile({
  label,
  value,
  icon: Icon,
  accent,
  note,
  href,
}: {
  label: string;
  value: React.ReactNode;
  icon: LucideIcon;
  accent?: string;
  note?: React.ReactNode;
  href?: string;
}) {
  const body = (
    <>
      <span className="flex items-center justify-between gap-2">
        <span className="truncate text-[13px] font-medium text-muted-foreground">{label}</span>
        <Icon className={cn("h-4 w-4 shrink-0 text-muted-foreground", accent)} aria-hidden="true" />
      </span>
      <span className="mt-2 block text-[26px] font-bold leading-tight tabular-nums">{value}</span>
      {note && <span className="mt-0.5 block truncate text-xs text-muted-foreground">{note}</span>}
    </>
  );
  if (!href) return <div className={TILE}>{body}</div>;
  return (
    <Link href={href} className={cn(TILE, "transition hover:border-tint-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}>
      {body}
    </Link>
  );
}
