import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Pill } from "@/components/admin/badges";
import { Meter } from "@/components/admin/stats";

export const num = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 1 });

export function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8.5rem_1fr] gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

export function EditLink({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="font-semibold text-primary hover:underline">
      {children}
    </button>
  );
}

/** Used vs. the monthly limit (plan + add-ons); null = no limit, 0 = not included. */
export function UsageRow({ label, used, limit, unit, note }: { label: string; used: number; limit: number | null; unit: string; note?: string }) {
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
        <span className="font-semibold">{label}</span>
        <span>
          <span className="font-semibold">{num(used)}</span>
          <span className="text-muted-foreground"> / {limit === null ? "unlimited" : limit > 0 ? `${num(limit)} ${unit}` : "not included"}</span>
        </span>
      </div>
      {limit ? (
        <div className="mt-2">
          <Meter value={used} max={limit} label={`${label} used`} />
        </div>
      ) : null}
      {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

export function Figure({ label, value, href }: { label: string; value: string; href?: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-xl font-semibold">
        {href ? (
          <Link href={href} className="hover:text-primary hover:underline">
            {value}
          </Link>
        ) : (
          value
        )}
      </dd>
    </div>
  );
}

export function ActivityLink({
  href,
  icon: Icon,
  title,
  detail,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  detail: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-3 rounded-md border border-border p-3 transition-colors hover:border-tint-strong hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground">
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">{title}</span>
        <span className="block text-xs text-muted-foreground">{detail}</span>
      </span>
      <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary" aria-hidden="true" />
    </Link>
  );
}

export function Channel({
  icon: Icon,
  title,
  ok,
  value,
  hint,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  ok: boolean;
  value: React.ReactNode;
  hint: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold">
          <Icon className="h-4 w-4 text-muted-foreground" />
          {title}
        </span>
        <Pill tone={ok ? "green" : "neutral"}>{ok ? "Ready" : "Off"}</Pill>
      </div>
      <p className="mt-2 text-sm">{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}
