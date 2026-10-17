"use client";

/** Owner alerts: an email and / or a text to the owner when the agent books, takes a message or flags something urgent. */

import { FormEvent, useState } from "react";
import { BellRing, Check, CircleCheck, LoaderCircle, RotateCcw, Send, TriangleAlert } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InfoTip, InlineError, SectionCard, SetupNote, StatusPill, useDraft } from "@/components/portal/kit";
import { useReportDirty } from "@/components/settings/shared";
import { formatPhone } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  formatApiError,
  integrationsApi,
  type AlertEvent,
  type AlertSettings,
  type AlertTestResult,
  type Integrations,
  type OwnerAlerts,
} from "@/services/api";

const EVENTS: { key: AlertEvent; label: string; tip?: string }[] = [
  { key: "booking", label: "New bookings & orders" },
  { key: "change", label: "Changes & cancellations" },
  { key: "message", label: "Messages & leads", tip: "Messages taken, new leads and “a team member will call you back” requests." },
  { key: "urgent", label: "Urgent", tip: "Emergencies, callers who ask for a person, and conversations that need review." },
];

type Channel = "email_events" | "sms_events";

const CHANNEL_LABEL = { email: "Email", sms: "Text" } as const;

function Toggle({ label, checked, disabled, onChange }: { label: string; checked: boolean; disabled?: boolean; onChange: (on: boolean) => void }) {
  return (
    <input
      type="checkbox"
      aria-label={label}
      className="h-4 w-4 cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-50"
      checked={checked}
      disabled={disabled}
      onChange={(e) => onChange(e.target.checked)}
    />
  );
}

export function OwnerAlertsSection({ alerts, onSaved }: { alerts: OwnerAlerts; onSaved: (next: Integrations) => void }) {
  const toast = useAppToast();
  const { draft, dirty, setDraft, reset, commit } = useDraft<AlertSettings>(alerts.settings);
  useReportDirty("alerts", dirty);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<AlertTestResult["results"] | null>(null);

  const saved = alerts.settings;
  const emailOn = Boolean(alerts.email_to && alerts.email_ready && saved.email_events.length);
  const smsOn = Boolean(alerts.sms_ready && saved.sms_to && saved.sms_events.length);
  const canTest = Boolean(alerts.email_to || saved.sms_to) && !dirty;
  const notReady = [!alerts.email_ready && "email", !alerts.sms_ready && "texts"].filter(Boolean).join(" and ");

  const toggle = (channel: Channel, event: AlertEvent, on: boolean) =>
    setDraft((current) => {
      const rest = current[channel].filter((value) => value !== event);
      return { ...current, [channel]: on ? [...rest, event] : rest };
    });

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (draft.sms_events.length && draft.sms_to.replace(/\D/g, "").length < 7) {
      setError("Add the mobile number alerts are texted to.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const next = await integrationsApi.updateAlerts(draft);
      if (next.alerts) commit(next.alerts.settings);
      onSaved(next);
      setTest(null);
      toast.success("Alert settings saved.");
    } catch (err) {
      setError(formatApiError(err, "Could not save the alert settings."));
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async () => {
    setTesting(true);
    setTest(null);
    setError(null);
    try {
      setTest((await integrationsApi.testAlert()).results);
    } catch (err) {
      setError(formatApiError(err, "Could not send the test alert."));
    } finally {
      setTesting(false);
    }
  };

  return (
    <SectionCard
      id="alerts"
      icon={BellRing}
      title="Owner alerts"
      badge={<StatusPill ok={emailOn || smsOn}>{emailOn || smsOn ? "On" : "Off"}</StatusPill>}
      description="A heads-up when your agent books, takes a message or flags something urgent."
      info="Each alert shows the caller, what was booked, a short AI summary and a link to the record. Texts count toward your plan's texts."
    >
      <form onSubmit={submit} noValidate className="grid gap-4">
        {notReady && <SetupNote>Sending {notReady} isn&apos;t set up on this server yet. Your choices still save.</SetupNote>}

        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface text-[13px] text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-semibold">
                  Alert me about
                </th>
                <th scope="col" className="w-20 px-3 py-2 text-center font-semibold">
                  <span className="inline-flex items-center gap-1">
                    Email
                    <InfoTip label="Where email alerts go">
                      {alerts.email_to ? <>Sent to {alerts.email_to}.</> : <>Add your email in Business settings first.</>}
                    </InfoTip>
                  </span>
                </th>
                <th scope="col" className="w-20 px-3 py-2 text-center font-semibold">
                  Text
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {EVENTS.map((row) => (
                <tr key={row.key}>
                  <th scope="row" className="px-3 py-2.5 text-left font-medium">
                    <span className="inline-flex items-center gap-1">
                      {row.label}
                      {row.tip && <InfoTip label={`About ${row.label}`}>{row.tip}</InfoTip>}
                    </span>
                  </th>
                  <td className="px-3 py-2.5 text-center">
                    <Toggle
                      label={`${row.label} by email`}
                      checked={draft.email_events.includes(row.key)}
                      disabled={!alerts.email_to}
                      onChange={(on) => toggle("email_events", row.key, on)}
                    />
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <Toggle label={`${row.label} by text`} checked={draft.sms_events.includes(row.key)} onChange={(on) => toggle("sms_events", row.key, on)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid gap-1.5 sm:max-w-sm">
          <div className="flex items-center gap-1.5">
            <label htmlFor="alerts-sms-to" className="text-[13.5px] font-semibold text-muted-foreground">
              Mobile for texts
            </label>
            <InfoTip label="About alert texts">With the country code, e.g. +1 617 555 0100. Reply STOP to a text to pause them, START to resume.</InfoTip>
          </div>
          <Input
            id="alerts-sms-to"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            placeholder="+1 617 555 0100"
            value={draft.sms_to}
            onChange={(e) => setDraft((current) => ({ ...current, sms_to: e.target.value }))}
          />
        </div>

        <InlineError message={error} />

        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" disabled={saving || !dirty}>
            {saving ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <Check className="h-4 w-4" aria-hidden />}
            Save
          </Button>
          {dirty && (
            <Button type="button" variant="ghost" onClick={reset} disabled={saving}>
              <RotateCcw className="h-4 w-4" aria-hidden />
              Discard
            </Button>
          )}
          <span className="flex-1" />
          <Button type="button" variant="outline" onClick={() => void sendTest()} disabled={testing || !canTest} title={dirty ? "Save first" : undefined}>
            {testing ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <Send className="h-4 w-4" aria-hidden />}
            Send test alert
          </Button>
        </div>

        {test && (
          <ul role="status" className="grid gap-1 text-xs">
            {(Object.keys(test) as (keyof typeof CHANNEL_LABEL)[]).map((channel) => {
              const result = test[channel]!;
              const ok = ["sent", "queued", "delivered"].includes(result.status);
              const Icon = ok ? CircleCheck : TriangleAlert;
              const detail = channel === "sms" && ok && saved.sms_to ? `Sent to ${formatPhone(saved.sms_to)}.` : result.detail;
              return (
                <li key={channel} className={cn("flex items-center gap-1.5", ok ? "text-muted-foreground" : "text-destructive")}>
                  <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
                  <span className="font-medium">{CHANNEL_LABEL[channel]}:</span> {detail}
                </li>
              );
            })}
          </ul>
        )}
      </form>
    </SectionCard>
  );
}
