"use client";

/** The current tier: price, renewal, usage vs limits, and Renew / Cancel / Resume. */

import { useState } from "react";
import { CreditCard, LoaderCircle } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { SectionCard, UsageMeter, usd } from "@/components/portal/kit";
import { CHANNEL_LABELS } from "@/components/portal/plan-section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";
import { billingApi, formatApiError, type ChannelKey, type PlanView } from "@/services/api";

const FEATURE_LABELS: Record<string, string> = {
  google_calendar: "Google Calendar",
  recording_retention: "12-month recordings",
  extra_language: "Extra language",
};

export function CurrentPlan({ plan, onChanged }: { plan: PlanView; onChanged: () => Promise<void> }) {
  const toast = useAppToast();
  const [busy, setBusy] = useState<"renew" | "cancel" | "resume" | null>(null);
  const { tier, renewal, subscription, usage, limits } = plan;
  const interval = renewal?.interval ?? subscription?.interval ?? "month";
  const price = interval === "year" ? tier.price_year : tier.price_month;
  const channels = plan.entitlements.channels;
  const voice = channels.includes("voice");
  const chat = channels.some((channel) => channel !== "voice");
  const chips = [...tier.channels.map((key) => CHANNEL_LABELS[key as ChannelKey] ?? key), ...tier.includes.map((key) => FEATURE_LABELS[key] ?? key)];
  const ending = Boolean(renewal?.ends_at);

  const act = async (kind: "renew" | "cancel" | "resume") => {
    if (kind === "cancel" && !window.confirm(`Cancel at the end of this period? You keep ${tier.name} until ${formatDate(renewal?.renews_at)}.`)) return;
    setBusy(kind);
    try {
      if (kind === "renew") {
        const result = await billingApi.renew();
        if (result.checkout_url) {
          window.location.assign(result.checkout_url);
          return;
        }
        toast.success("Renewed.");
      } else {
        await (kind === "cancel" ? billingApi.cancel() : billingApi.resume());
        toast.success(kind === "cancel" ? "Cancels at the end of the period." : "Your plan continues.");
      }
      await onChanged();
    } catch (err) {
      toast.error(formatApiError(err, "Could not update your plan."));
    } finally {
      setBusy(null);
    }
  };

  const spinner = (kind: typeof busy) => busy === kind && <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden />;

  return (
    <SectionCard id="plan" icon={CreditCard} title="Your plan" badge={renewal && <Badge variant={ending ? "warning" : "success"}>{ending ? "Ending" : "Active"}</Badge>}>
      <div className="grid gap-6 md:grid-cols-[15rem_minmax(0,1fr)]">
        <div className="min-w-0 space-y-3 rounded-md border border-border bg-surface p-4">
          <div>
            <p className="text-xl font-bold">{tier.name}</p>
            <p className="text-sm tabular-nums text-muted-foreground">{price ? `${usd(price)} / ${interval === "year" ? "year" : "mo"}` : "Free"}</p>
          </div>
          {renewal && (
            <p className="text-xs text-muted-foreground">
              {ending ? `Ends ${formatDate(renewal.ends_at)}` : renewal.renews_at ? `Renews ${formatDate(renewal.renews_at)} · ${usd(renewal.amount)}` : renewal.status}
            </p>
          )}
          {chips.length > 0 && (
            <ul className="flex flex-wrap gap-1.5" aria-label="Included">
              {chips.map((chip) => (
                <li key={chip} className="rounded-full bg-accent px-2 py-0.5 text-[11.5px] font-semibold text-accent-foreground">
                  {chip}
                </li>
              ))}
            </ul>
          )}
          {subscription && (
            <div className="flex flex-wrap gap-2 pt-1">
              {ending ? (
                <Button type="button" size="sm" variant="outline" disabled={Boolean(busy)} onClick={() => void act("resume")}>
                  {spinner("resume")}
                  Keep my plan
                </Button>
              ) : (
                <Button type="button" size="sm" variant="ghost" disabled={Boolean(busy)} onClick={() => void act("cancel")}>
                  {spinner("cancel")}
                  Cancel
                </Button>
              )}
              <Button type="button" size="sm" variant="outline" disabled={Boolean(busy)} onClick={() => void act("renew")}>
                {spinner("renew")}
                Renew now
              </Button>
            </div>
          )}
        </div>
        <div className="grid min-w-0 content-start gap-5">
          {voice && <UsageMeter label="Call minutes" used={usage.minutes} included={limits.minutes} unit="min" />}
          {chat && <UsageMeter label="Chats" used={usage.chats} included={limits.chats} unit="chats" />}
          <UsageMeter label="Texts" used={usage.sms ?? 0} included={limits.sms} unit="texts" />
        </div>
      </div>
    </SectionCard>
  );
}
