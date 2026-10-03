"use client";

import { useId, useState } from "react";

import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { PLANS, usd } from "@/lib/site-content";

const WEEKS_PER_MONTH = 4.33;
/** Only used for the "minutes check" line; shown to the visitor as an assumption. */
const ASSUMED_MINUTES_PER_CALL = 3;

function toNumber(value: string, max: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return 0;
  return Math.min(parsed, max);
}

function fmt(value: number, decimals = 0): string {
  return value.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** Missed calls → bookings → revenue, against the plan price. All math shown. */
export function RoiCalculator() {
  const id = useId();
  const [missed, setMissed] = useState("15");
  const [rate, setRate] = useState("30");
  const [value, setValue] = useState("120");
  const [planKey, setPlanKey] = useState("growth");

  const plan = PLANS.find((item) => item.key === planKey) ?? PLANS[1];
  const missedWeek = toNumber(missed, 10_000);
  const ratePct = toNumber(rate, 100);
  const jobValue = toNumber(value, 1_000_000);

  const callsMonth = missedWeek * WEEKS_PER_MONTH;
  const bookings = (callsMonth * ratePct) / 100;
  const revenue = bookings * jobValue;
  const net = revenue - plan.price;
  const multiple = plan.price > 0 ? revenue / plan.price : 0;
  const minutesNeeded = callsMonth * ASSUMED_MINUTES_PER_CALL;
  const overageMinutes = Math.max(0, minutesNeeded - plan.minutes);

  return (
    <div className="grid overflow-hidden rounded-2xl border border-border bg-card lg:grid-cols-[1fr_1.1fr]">
      <form className="space-y-5 p-6 sm:p-8" onSubmit={(event) => event.preventDefault()} aria-label="ROI inputs">
        <div className="space-y-1.5">
          <label htmlFor={`${id}-missed`} className="text-sm font-semibold text-foreground">
            Missed calls per week
          </label>
          <Input
            id={`${id}-missed`}
            type="number"
            inputMode="numeric"
            min={0}
            step={1}
            value={missed}
            onChange={(event) => setMissed(event.target.value)}
          />
          <p className="text-xs text-muted-foreground">After hours, while you're busy, or on hold too long.</p>
        </div>

        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <label htmlFor={`${id}-rate`} className="text-sm font-semibold text-foreground">
              Share that would have booked
            </label>
            <span className="text-sm font-semibold tabular-nums text-primary-dark">{fmt(ratePct)}%</span>
          </div>
          <input
            id={`${id}-rate`}
            type="range"
            min={0}
            max={100}
            step={5}
            value={ratePct}
            onChange={(event) => setRate(event.target.value)}
            className="w-full accent-primary"
            aria-valuetext={`${fmt(ratePct)} percent`}
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor={`${id}-value`} className="text-sm font-semibold text-foreground">
            Average job or visit value (USD)
          </label>
          <Input
            id={`${id}-value`}
            type="number"
            inputMode="decimal"
            min={0}
            step={10}
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor={`${id}-plan`} className="text-sm font-semibold text-foreground">
            Plan
          </label>
          <Select id={`${id}-plan`} value={planKey} onChange={(event) => setPlanKey(event.target.value)}>
            {PLANS.map((item) => (
              <option key={item.key} value={item.key}>
                {item.name} — {usd(item.price)} / month
              </option>
            ))}
          </Select>
        </div>
      </form>

      <div className="flex flex-col border-t border-border bg-surface p-6 sm:p-8 lg:border-l lg:border-t-0">
        <p className="text-sm font-semibold text-muted-foreground">Revenue recovered per month</p>
        <p className="mt-1 text-4xl font-bold tracking-tight tabular-nums text-primary-dark" aria-live="polite" aria-atomic="true">
          {usd(revenue)}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          vs. {plan.name} at {usd(plan.price)} / month
          {revenue > 0 && plan.price > 0 && <> · about {fmt(multiple, 1)}× the plan cost</>}
        </p>

        <dl className="mt-6 space-y-2.5 border-t border-border pt-5 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">
              {fmt(missedWeek)} missed calls × {WEEKS_PER_MONTH} weeks
            </dt>
            <dd className="font-medium tabular-nums text-foreground">{fmt(callsMonth, 1)} calls</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">× {fmt(ratePct)}% that book</dt>
            <dd className="font-medium tabular-nums text-foreground">{fmt(bookings, 1)} bookings</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">× {usd(jobValue)} average value</dt>
            <dd className="font-medium tabular-nums text-foreground">{usd(revenue)}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">− {plan.name} plan</dt>
            <dd className="font-medium tabular-nums text-foreground">{usd(plan.price)}</dd>
          </div>
          <div className="flex justify-between gap-4 border-t border-border pt-2.5">
            <dt className="font-semibold text-foreground">Net per month</dt>
            <dd className={net >= 0 ? "font-bold tabular-nums text-primary-dark" : "font-bold tabular-nums text-destructive"}>
              {net < 0 ? "−" : ""}
              {usd(Math.abs(net))}
            </dd>
          </div>
        </dl>

        <p className="mt-6 rounded-lg border border-border bg-card p-3 text-xs leading-relaxed text-muted-foreground">
          <span className="font-semibold text-foreground">Minutes check:</span> at about {ASSUMED_MINUTES_PER_CALL} minutes per call,{" "}
          {fmt(callsMonth, 0)} calls use roughly {fmt(minutesNeeded)} of {plan.name}&apos;s {fmt(plan.minutes)} included minutes
          {overageMinutes > 0
            ? ` — about ${fmt(overageMinutes)} extra minutes at ${usd(plan.overage, 2)} (${usd(overageMinutes * plan.overage)}).`
            : "."}{" "}
          Counts only calls you currently miss — not time saved on calls you already answer.
        </p>
      </div>
    </div>
  );
}
