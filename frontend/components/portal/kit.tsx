"use client";

/** Building blocks shared by the portal's settings pages (cards, drafts, copy, meters). */

import { useCallback, useId, useState } from "react";
import { ChevronRight, Check, CircleCheck, Copy, Info, TriangleAlert, type LucideIcon } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { HoverInfo } from "@/components/ui/hover-info";
import { cn } from "@/lib/utils";

export function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** A form draft over server values (see the settings page for the same pattern). */
export function useDraft<T>(source: T) {
  const sourceKey = JSON.stringify(source);
  const [state, setState] = useState(() => ({ key: sourceKey, base: source, draft: source }));
  if (state.key !== sourceKey) {
    const edited = !same(state.draft, state.base);
    setState({ key: sourceKey, base: source, draft: edited ? state.draft : source });
  }
  const setDraft = useCallback((update: (previous: T) => T) => setState((current) => ({ ...current, draft: update(current.draft) })), []);
  const reset = useCallback(() => setState((current) => ({ ...current, draft: current.base })), []);
  // Keeps the source key: the refreshed server values that follow are adopted as-is.
  const commit = useCallback((saved: T) => setState((current) => ({ key: current.key, base: saved, draft: saved })), []);
  return { draft: state.draft, dirty: !same(state.draft, state.base), setDraft, reset, commit };
}

export function useCopy() {
  const toast = useAppToast();
  const [copied, setCopied] = useState<string | null>(null);
  const copy = useCallback(
    async (id: string, text: string) => {
      try {
        await navigator.clipboard.writeText(text);
        setCopied(id);
        window.setTimeout(() => setCopied((current) => (current === id ? null : current)), 2000);
      } catch {
        toast.error("Could not copy — select the text and copy it manually.");
      }
    },
    [toast],
  );
  return { copied, copy };
}

export function CopyButton({ id, text, copied, onCopy, label = "Copy", disabled }: { id: string; text: string; copied: string | null; onCopy: (id: string, text: string) => void; label?: string; disabled?: boolean }) {
  const done = copied === id;
  return (
    <Button type="button" variant="outline" size="sm" disabled={disabled || !text} onClick={() => onCopy(id, text)}>
      {done ? <Check className="h-3.5 w-3.5 text-primary" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
      <span aria-live="polite">{done ? "Copied" : label}</span>
    </Button>
  );
}

/**
 * An info icon that shows an explanation on hover. Screen readers get the same
 * text as the button's description.
 */
export function InfoTip({ children, label = "More info", width = 288 }: { children: React.ReactNode; label?: string; width?: number }) {
  const id = useId();
  return (
    <>
      <HoverInfo
        width={width}
        trigger={
          <button
            type="button"
            aria-label={label}
            aria-describedby={id}
            className="inline-flex h-5 w-5 items-center justify-center rounded-full align-middle text-muted-foreground transition hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Info className="h-3.5 w-3.5" aria-hidden />
          </button>
        }
      >
        <span className="block text-xs font-normal leading-relaxed text-muted-foreground">{children}</span>
      </HoverInfo>
      <span id={id} hidden>
        {children}
      </span>
    </>
  );
}

/** A collapsed "How it works" block for longer explanations. */
export function HowTo({ title = "How it works", children, className }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <details className={cn("group rounded-md border border-border", className)}>
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-[13px] font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" aria-hidden />
        {title}
      </summary>
      <div className="space-y-2 border-t border-border px-3 py-3 text-xs leading-relaxed text-muted-foreground">{children}</div>
    </details>
  );
}

export function SectionCard({
  id,
  icon: Icon,
  title,
  description,
  badge,
  info,
  className,
  children,
}: {
  id: string;
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  badge?: React.ReactNode;
  /** Longer explanation, behind an info icon next to the title. */
  info?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Card id={id} role="region" aria-labelledby={`${id}-title`} className={cn("scroll-mt-24", className)}>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1.5">
            <CardTitle id={`${id}-title`} className="flex items-center gap-2">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-accent text-accent-foreground">
                <Icon className="h-4 w-4" aria-hidden />
              </span>
              {title}
            </CardTitle>
            {info && <InfoTip label={`About ${title}`}>{info}</InfoTip>}
          </div>
          {badge}
        </div>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function StatusPill({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12.5px] font-semibold",
        ok ? "bg-[#d1fae5] text-[#065f46] dark:bg-emerald-500/15 dark:text-emerald-300" : "bg-secondary text-muted-foreground",
      )}
    >
      {ok ? <CircleCheck className="h-3.5 w-3.5" aria-hidden /> : <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />}
      {children}
    </span>
  );
}

export function InlineError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {message}
    </p>
  );
}

export function CodeBlock({ code, label }: { code: string; label: string }) {
  return (
    <pre aria-label={label} className="max-h-96 overflow-auto rounded-md border border-border bg-surface p-3 text-[12.5px] leading-relaxed">
      <code className="font-mono">{code}</code>
    </pre>
  );
}

export function browserOrigin(): string {
  return typeof window === "undefined" ? "" : window.location.origin;
}

export function isLocalOrigin(origin: string): boolean {
  try {
    const host = new URL(origin).hostname;
    return host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0" || host.endsWith(".local");
  } catch {
    return false;
  }
}

export function SwitchRow({ title, hint, checked, onChange, disabled }: { title: string; hint?: React.ReactNode; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  return (
    <label className={cn("flex items-start justify-between gap-4 rounded-md border border-border p-3", disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer")}>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{title}</span>
        {hint && <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">{hint}</span>}
      </span>
      <input type="checkbox" role="switch" className="peer sr-only" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span
        aria-hidden
        className="relative mt-0.5 inline-flex h-5 w-9 shrink-0 rounded-full bg-input transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-white after:shadow after:transition-transform peer-checked:bg-primary peer-checked:after:translate-x-4 peer-focus-visible:ring-2 peer-focus-visible:ring-ring"
      />
    </label>
  );
}

export function SetupNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-md border border-border bg-surface p-2.5 text-xs leading-relaxed text-muted-foreground">
      <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="min-w-0">{children}</span>
    </p>
  );
}


export function usd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatNumber(value: number, digits = 1): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: digits });
}

/** `included`: the monthly allowance; null = no limit, 0 = none included (no bar). */
export function UsageMeter({ label, used, included, unit }: { label: string; used: number; included: number | null; unit: string }) {
  const limit = included ?? 0;
  const metered = limit > 0;
  const pct = metered ? Math.min(100, (used / limit) * 100) : 0;
  const over = metered && used > limit;
  const near = metered && !over && pct >= 80;
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          <span className="font-semibold text-foreground">{formatNumber(used)}</span>
          {metered ? ` / ${formatNumber(limit, 0)} ${unit}` : included === null ? ` ${unit} · no limit` : ` ${unit}`}
        </span>
      </div>
      {metered && (
        <div
          role="meter"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={limit}
          aria-valuenow={Math.min(used, limit)}
          aria-valuetext={`${formatNumber(used)} of ${formatNumber(limit, 0)} ${unit}`}
          className="mt-2 h-2 overflow-hidden rounded-full bg-secondary"
        >
          <div className={cn("h-full rounded-full transition-[width]", over ? "bg-destructive" : near ? "bg-amber-500" : "bg-primary")} style={{ width: `${pct}%` }} />
        </div>
      )}
      {(over || near) && (
        <p className={cn("mt-1.5 flex items-center gap-1.5 text-xs font-medium", over ? "text-destructive" : "text-amber-700 dark:text-amber-300")}>
          <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
          {over ? "Over your allowance" : "Close to your allowance"}
        </p>
      )}
    </div>
  );
}
