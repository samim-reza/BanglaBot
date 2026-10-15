import { Pill, type Tone } from "@/components/admin/badges";
import { fmtUsd } from "@/components/admin/numbers";
import { formatDate, humanize } from "@/lib/format";
import type { Subscription, SubscriptionKind, SubscriptionStatus } from "@/services/api/admin/subscriptions";

export const SUB_STATUSES: { value: SubscriptionStatus; label: string; tone: Tone }[] = [
  { value: "active", label: "Active", tone: "green" },
  { value: "pending", label: "Pending", tone: "amber" },
  { value: "past_due", label: "Past due", tone: "orange" },
  { value: "cancelled", label: "Cancelled", tone: "neutral" },
];

export const SUB_KINDS: { value: SubscriptionKind; label: string }[] = [
  { value: "signup", label: "Signup" },
  { value: "change", label: "Plan change" },
  { value: "renewal", label: "Renewal" },
  { value: "manual", label: "Manual" },
];

export function SubscriptionStatusPill({ status }: { status: string }) {
  const entry = SUB_STATUSES.find((item) => item.value === status);
  return <Pill tone={entry?.tone ?? "neutral"}>{entry?.label ?? humanize(status)}</Pill>;
}

/** Line items, add-ons and payment details of one subscription. */
export function SubscriptionDetail({ sub }: { sub: Subscription }) {
  const facts: [string, React.ReactNode][] = [
    ["Period", sub.current_period_start ? `${formatDate(sub.current_period_start)} → ${formatDate(sub.current_period_end)}` : "—"],
    ["Activated", formatDate(sub.activated_at)],
    ["Payment", sub.payment_provider ? `${sub.payment_provider}${sub.payment_ref ? ` · ${sub.payment_ref}` : ""}` : "—"],
    ["Renews", sub.cancel_at_period_end ? "Cancels at period end" : sub.status === "active" ? "Yes" : "—"],
  ];
  return (
    <div className="space-y-3 py-1">
      <dl className="grid gap-x-6 gap-y-2 text-xs sm:grid-cols-4">
        {facts.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
            <dd className="mt-0.5 break-all text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
      {sub.line_items.length > 0 && (
        <table className="w-full max-w-xl text-[13px]">
          <tbody>
            {sub.line_items.map((item, i) => (
              <tr key={`${item.key}-${i}`} className="border-b border-border last:border-0">
                <td className="py-1.5">
                  {item.name}
                  {item.quantity > 1 && <span className="text-muted-foreground"> × {item.quantity}</span>}
                </td>
                <td className="py-1.5 text-xs text-muted-foreground">{item.period === "once" ? "once" : item.period}</td>
                <td className="py-1.5 text-right tabular-nums">{fmtUsd(item.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
