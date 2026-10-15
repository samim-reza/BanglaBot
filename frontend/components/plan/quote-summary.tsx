"use client";

/** A live price for a selection: line items, totals and (for owners) what the change does. */

import { useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";

import { usd } from "@/components/portal/kit";
import { formatDate } from "@/lib/format";
import { formatApiError, type PlanChange, type Quote } from "@/services/api";

/** Re-quotes `key` (a JSON selection) shortly after it changes; stale answers are dropped. */
export function useQuote<T>(key: string, fetcher: (key: string) => Promise<T>, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const ticket = useRef(0);
  const fetchRef = useRef(fetcher);
  useEffect(() => {
    fetchRef.current = fetcher;
  });
  useEffect(() => {
    if (!enabled || !key) return;
    const mine = ++ticket.current;
    const timer = window.setTimeout(() => {
      setLoading(true);
      fetchRef
        .current(key)
        .then((next) => {
          if (mine !== ticket.current) return;
          setData(next);
          setError(null);
        })
        .catch((err) => {
          if (mine !== ticket.current) return;
          setData(null);
          setError(formatApiError(err, "Could not price that."));
        })
        .finally(() => {
          if (mine === ticket.current) setLoading(false);
        });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [key, enabled]);
  return { data, error, loading };
}

const PERIOD: Record<string, string> = { month: "/ mo", year: "/ year", once: "once" };

export function changeLine(change: PlanChange): string {
  const when = change.effective === "period_end" ? `from ${formatDate(change.effective_at)}` : change.effective === "now" ? "now" : "once paid";
  switch (change.kind) {
    case "same":
      return "That's your current plan.";
    case "upgrade":
      return `Upgrade, starts ${when}.`;
    case "downgrade":
      return `Downgrade, starts ${when}.`;
    case "swap":
      return `Change, starts ${when}.`;
    default:
      return `New plan, starts ${when}.`;
  }
}

export function QuoteSummary({ quote, change, loading, error }: { quote: Quote | null; change?: PlanChange | null; loading: boolean; error: string | null }) {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4 text-sm" aria-live="polite">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Summary</h3>
        {loading && <LoaderCircle className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Updating" />}
      </div>
      {error && <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>}
      {quote ? (
        <>
          <ul className="space-y-1.5">
            {quote.items.map((item) => (
              <li key={`${item.kind}:${item.key}`} className="flex justify-between gap-3">
                <span className="min-w-0 truncate">
                  {item.name}
                  {item.quantity > 1 && <span className="text-muted-foreground"> ×{item.quantity}</span>}
                </span>
                <span className="shrink-0 tabular-nums">
                  {usd(item.amount)} <span className="text-xs text-muted-foreground">{PERIOD[item.period] ?? ""}</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="space-y-1 border-t border-border pt-2">
            <p className="flex justify-between font-semibold">
              <span>{quote.interval === "year" ? "Every year" : "Every month"}</span>
              <span className="tabular-nums">{usd(quote.recurring)}</span>
            </p>
            {quote.one_time > 0 && (
              <p className="flex justify-between text-muted-foreground">
                <span>One-time</span>
                <span className="tabular-nums">{usd(quote.one_time)}</span>
              </p>
            )}
            {change && (
              <p className="flex justify-between font-semibold text-primary-dark dark:text-primary">
                <span>Due now</span>
                <span className="tabular-nums">{usd(change.due_now)}</span>
              </p>
            )}
          </div>
          {change && <p className="text-xs text-muted-foreground">{changeLine(change)}</p>}
        </>
      ) : (
        !error && <div className="h-16 animate-pulse rounded-md bg-secondary" />
      )}
    </div>
  );
}
