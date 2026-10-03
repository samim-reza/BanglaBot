"use client";

/** SMS confirmations and calendar sync (one GET /api/integrations), shown on the Settings page. */

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CalendarDays,
  CalendarSync,
  Check,
  ExternalLink,
  LoaderCircle,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Send,
  Smartphone,
  Unlink,
  X,
} from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useDraft, useCopy, CopyButton, SectionCard, StatusPill, InlineError, InfoTip, SwitchRow, SetupNote, UsageMeter } from "@/components/portal/kit";
import { SmsMessageList } from "@/components/sms-messages";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import {
  addonsApi,
  formatApiError,
  integrationsApi,
  type CalendarCheck,
  type CalendarItem,
  type GoogleCalendarOption,
  type Integrations,
  type SmsMessage,
  type SmsSettings,
  type VerticalKey,
} from "@/services/api";

// ---------------------------------------------------------------- data (one GET /api/integrations)

/** The SMS + calendar summary. With `enabled` false nothing loads until it turns true. */
export function useIntegrations(enabled = true) {
  const [data, setData] = useState<Integrations | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setData(await integrationsApi.get());
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load the SMS and calendar settings."));
    }
  }, []);
  const started = useRef(false);
  useEffect(() => {
    if (!enabled || started.current) return;
    started.current = true;
    void load();
  }, [enabled, load]);
  return { data, setData, error, reload: load };
}

/** Loading / error placeholder while the summary loads. */
export function IntegrationsPlaceholder({ error, onRetry }: { error: string | null; onRetry: () => void }) {
  return (
    <Card>
      {error ? (
        <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-5">
          <p className="text-sm text-destructive">{error}</p>
          <Button type="button" variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            Try again
          </Button>
        </CardContent>
      ) : (
        <CardContent className="flex items-center gap-2 pt-5 text-sm text-muted-foreground" role="status">
          <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
          Loading…
        </CardContent>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- SMS confirmations

const SMS_COPY: Record<VerticalKey, { booking: string; change: string }> = {
  clinic: { booking: "Appointment booked", change: "Moved or cancelled" },
  real_estate: { booking: "Viewing or lead", change: "Moved or cancelled" },
  home_service: { booking: "Visit booked", change: "Moved or cancelled" },
  ecommerce: { booking: "Order confirmed", change: "Order cancelled" },
};

const REMINDER_HOURS = [0, 1, 2, 4, 12, 24, 48];

function reminderLabel(hours: number): string {
  if (!hours) return "No reminder";
  const span = hours % 24 === 0 ? (hours === 24 ? "1 day" : `${hours / 24} days`) : hours === 1 ? "1 hour" : `${hours} hours`;
  return `${span} before`;
}

export function SmsSection({ data, onSaved }: { data: Integrations; onSaved: (next: Integrations) => void }) {
  const { merchant, vertical, usage } = useWorkspace();
  const toast = useAppToast();
  const sms = data.sms;
  const { draft, dirty, setDraft, reset, commit } = useDraft(sms.settings);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testTo, setTestTo] = useState(merchant.support_phone || merchant.phone || "");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<SmsMessage | null>(null);
  const [messages, setMessages] = useState<SmsMessage[] | null>(null);
  const [loadingMessages, setLoadingMessages] = useState(false);

  const copy = SMS_COPY[vertical.key] ?? SMS_COPY.clinic;
  const live = sms.settings.enabled && sms.platform_ready;
  const recordLabel = t(vertical.record_label, "record").toLowerCase();

  const loadMessages = useCallback(async () => {
    setLoadingMessages(true);
    try {
      setMessages((await integrationsApi.messages({ page_size: 8 })).items);
    } catch {
      setMessages((current) => current ?? []);
    } finally {
      setLoadingMessages(false);
    }
  }, []);
  useEffect(() => {
    void loadMessages();
  }, [loadMessages]);

  const patch = (values: Partial<SmsSettings>) => setDraft((current) => ({ ...current, ...values }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const next = await integrationsApi.updateSms(draft);
      commit(next.sms.settings);
      onSaved(next);
      toast.success(next.sms.settings.enabled ? "SMS settings saved." : "SMS confirmations turned off.");
    } catch (err) {
      setError(formatApiError(err, "Could not save the SMS settings."));
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async (event: FormEvent) => {
    event.preventDefault();
    const to = testTo.trim();
    if (to.replace(/\D/g, "").length < 7) {
      setError("Enter the number with its country code, e.g. +1 617 555 0100.");
      return;
    }
    setTesting(true);
    setTestResult(null);
    setError(null);
    try {
      setTestResult(await integrationsApi.testSms(to));
      void loadMessages();
    } catch (err) {
      setError(formatApiError(err, "Could not send the test text."));
    } finally {
      setTesting(false);
    }
  };

  const testFailed = testResult?.status === "failed" || testResult?.status === "skipped";

  return (
    <SectionCard
      id="sms"
      icon={Smartphone}
      title="SMS confirmations"
      badge={<StatusPill ok={live}>{live ? "On" : sms.settings.enabled ? "Waiting for setup" : "Off"}</StatusPill>}
      description="Booking details and reminders, texted to the customer."
      info={
        <>
          The agent tells callers &ldquo;we&apos;ll text you the details&rdquo;. Changes you make in the portal don&apos;t text anyone — use{" "}
          <span className="font-medium text-foreground">Send SMS</span> on the {recordLabel}&apos;s page.
        </>
      }
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <form onSubmit={submit} noValidate className="grid min-w-0 content-start gap-3">
          {!sms.platform_ready && <SetupNote>Texting isn&apos;t set up on this server yet. Your choices still save.</SetupNote>}
          <SwitchRow title="Text customers" checked={draft.enabled} onChange={(enabled) => patch({ enabled })} />
          <div className={cn("grid gap-3", !draft.enabled && "opacity-60")}>
            <SwitchRow title={copy.booking} checked={draft.on_booking} disabled={!draft.enabled} onChange={(on_booking) => patch({ on_booking })} />
            <SwitchRow title={copy.change} checked={draft.on_change} disabled={!draft.enabled} onChange={(on_change) => patch({ on_change })} />
            {vertical.scheduled && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border p-3">
                <label htmlFor="sms-reminder" className="text-sm font-medium">
                  Reminder
                </label>
                <Select
                  id="sms-reminder"
                  className="h-9 w-auto min-w-[10rem]"
                  disabled={!draft.enabled}
                  value={String(draft.reminder_hours)}
                  onChange={(e) => patch({ reminder_hours: Number(e.target.value) })}
                >
                  {Array.from(new Set([...REMINDER_HOURS, draft.reminder_hours])).sort((a, b) => a - b).map((hours) => (
                    <option key={hours} value={hours}>
                      {reminderLabel(hours)}
                    </option>
                  ))}
                </Select>
              </div>
            )}
          </div>
          <InlineError message={error} />
          <div className="flex flex-wrap gap-2">
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
          </div>
        </form>

        <div className="grid min-w-0 content-start gap-4">
          <UsageMeter label="Texts this month" used={sms.sent_this_month} included={usage.limits.sms} unit="texts" />
          {sms.sender && (
            <p className="text-xs text-muted-foreground">
              From {sms.sender.startsWith("+") ? <span className="font-mono">{sms.sender}</span> : `your Twilio ${sms.sender}`}
            </p>
          )}
          <form onSubmit={sendTest} noValidate className="grid gap-2 rounded-md border border-border bg-surface p-3">
            <div className="flex items-center gap-1.5">
              <label htmlFor="sms-test-to" className="text-[13.5px] font-semibold text-muted-foreground">
                Test text
              </label>
              <InfoTip label="About test texts">On a Twilio trial account, texts only reach numbers verified in your Twilio console.</InfoTip>
            </div>
            <div className="flex gap-2">
              <Input id="sms-test-to" type="tel" inputMode="tel" autoComplete="tel" placeholder="+1 617 555 0100" value={testTo} onChange={(e) => setTestTo(e.target.value)} />
              <Button type="submit" variant="outline" disabled={testing || !sms.platform_ready} aria-label="Send test text">
                {testing ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <Send className="h-4 w-4" aria-hidden />}
              </Button>
            </div>
            {testResult && (
              <p role="status" className={cn("text-xs", testFailed ? "text-destructive" : "text-muted-foreground")}>
                {testFailed ? testResult.error || "The text wasn't sent." : `Sent to ${testResult.to_number}.`}
              </p>
            )}
          </form>
        </div>
      </div>

      <div className="mt-6 grid gap-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Recent texts</h3>
          <Button type="button" variant="ghost" size="sm" onClick={() => void loadMessages()} disabled={loadingMessages}>
            <RefreshCw className={cn("h-3.5 w-3.5", loadingMessages && "animate-spin")} aria-hidden />
            Refresh
          </Button>
        </div>
        {messages === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <SmsMessageList messages={messages} timezone={merchant.timezone} empty="No texts yet." />
        )}
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- calendar sync

function webcal(url: string): string {
  return url.replace(/^https?:\/\//i, "webcal://");
}

const GOOGLE_ADDON = "google_calendar";

/** Two-way Google sync is an add-on below Growth: offer it instead of the Connect button. */
function GoogleUpsell() {
  const toast = useAppToast();
  const [offer, setOffer] = useState<{ price: string; pending: boolean }>({ price: "$9 / mo", pending: false });
  const [requesting, setRequesting] = useState(false);

  useEffect(() => {
    let live = true;
    addonsApi
      .shop()
      .then((shop) => {
        if (!live) return;
        const item = shop.catalog.find((addon) => addon.key === GOOGLE_ADDON);
        setOffer({
          price: item?.price_label || "$9 / mo",
          pending: shop.requests.some((request) => request.addon === GOOGLE_ADDON && request.status === "pending"),
        });
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  const request = async () => {
    setRequesting(true);
    try {
      await addonsApi.request(GOOGLE_ADDON);
      setOffer((current) => ({ ...current, pending: true }));
      toast.success("Requested — we'll switch it on shortly.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not send the request."));
    } finally {
      setRequesting(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-dashed border-border bg-surface p-3">
      <p className="text-sm">
        <span className="font-medium">Two-way Google Calendar</span> <span className="text-muted-foreground">· {offer.price}</span>
      </p>
      {offer.pending ? (
        <StatusPill ok={false}>Requested</StatusPill>
      ) : (
        <Button type="button" size="sm" onClick={() => void request()} disabled={requesting}>
          {requesting && <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden />}
          Request
        </Button>
      )}
    </div>
  );
}

export function CalendarSection({ data, onSaved }: { data: Integrations; onSaved: (next: Integrations) => void }) {
  const { vertical } = useWorkspace();
  const toast = useAppToast();
  const { copied, copy } = useCopy();
  const calendar = data.calendar;
  const google = calendar.google;
  const [rotating, setRotating] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [googleSaving, setGoogleSaving] = useState(false);
  const [calendars, setCalendars] = useState<{ key: string; items: GoogleCalendarOption[]; error: string | null } | null>(null);

  const records = t(vertical.record_label_plural, "bookings").toLowerCase();
  const itemLabel = t(vertical.catalog_label, "item").toLowerCase();
  const itemsLabel = t(vertical.catalog_label_plural, "Items");
  // Per-item busy calendars only where the engine books per item (a doctor's own diary).
  const perItemBusy = vertical.catalog_fields.some((field) => field.key === "calendar_ics");
  const connected = google.available && google.connected;
  const calendarsKey = connected ? google.email || "connected" : "";
  const googleCalendars = calendars && calendars.key === calendarsKey ? calendars : null;
  const syncedAt = Boolean(calendar.feed_url) && calendar.public;

  useEffect(() => {
    if (!calendarsKey) return;
    let live = true;
    integrationsApi
      .googleCalendars()
      .then((result) => live && setCalendars({ key: calendarsKey, items: result.items, error: null }))
      .catch((err) => live && setCalendars({ key: calendarsKey, items: [], error: formatApiError(err, "Could not list your Google calendars.") }));
    return () => {
      live = false;
    };
  }, [calendarsKey]);

  const rotate = async () => {
    if (calendar.feed_url && !window.confirm("Create a new feed link?\n\nCalendars subscribed to the old link stop updating — subscribe again with the new one.")) return;
    setRotating(true);
    try {
      onSaved(await integrationsApi.rotateFeed());
      toast.success(calendar.feed_url ? "New feed link created." : "Feed link created.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not create the feed link."));
    } finally {
      setRotating(false);
    }
  };

  const connect = async () => {
    setConnecting(true);
    try {
      const { url } = await integrationsApi.googleConnectUrl();
      window.location.assign(url);
    } catch (err) {
      toast.error(formatApiError(err, "Could not start the Google sign-in."));
      setConnecting(false);
    }
  };

  const updateGoogle = async (values: { calendar_id?: string; check_busy?: boolean }) => {
    setGoogleSaving(true);
    try {
      onSaved(await integrationsApi.updateGoogle(values));
      toast.success("Google Calendar settings saved.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not save the Google Calendar settings."));
    } finally {
      setGoogleSaving(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm(`Disconnect ${google.email || "Google Calendar"}?\n\nNew ${records} stop appearing there and its busy times are no longer checked. Events already created stay.`)) return;
    setGoogleSaving(true);
    try {
      onSaved(await integrationsApi.disconnectGoogle());
      toast.success("Google Calendar disconnected.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not disconnect Google Calendar."));
    } finally {
      setGoogleSaving(false);
    }
  };

  return (
    <SectionCard
      id="calendar"
      icon={CalendarDays}
      title="Calendar sync"
      badge={<StatusPill ok={connected || syncedAt}>{connected ? "Google connected" : syncedAt ? "Feed ready" : "Not connected"}</StatusPill>}
      description={`New ${records} land in your calendar; busy times are never offered.`}
    >
      <div className="grid gap-6">
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Google, two-way */}
          <div className="grid min-w-0 content-start gap-3 rounded-md border border-border p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">Google Calendar</h3>
              {connected && <StatusPill ok>Connected</StatusPill>}
            </div>
            {!google.available ? (
              <SetupNote>
                <span className="inline-flex flex-wrap items-center gap-1">
                  Google sign-in isn&apos;t set up on this server.
                  <InfoTip label="Server setup" width={320}>
                    Set <span className="font-mono">GOOGLE_CLIENT_ID</span> and <span className="font-mono">GOOGLE_CLIENT_SECRET</span> (an OAuth Web client) and add
                    this redirect URI: <span className="break-all font-mono text-foreground">{google.redirect_uri}</span>
                  </InfoTip>
                </span>
              </SetupNote>
            ) : connected ? (
              <>
                <p className="text-sm">
                  Connected as <span className="font-medium">{google.email || "your Google account"}</span>
                </p>
                <div className="grid gap-1.5">
                  <label htmlFor="google-calendar" className="text-[13.5px] font-semibold text-muted-foreground">
                    Calendar
                  </label>
                  <Select
                    id="google-calendar"
                    value={google.calendar_id}
                    disabled={googleSaving || !googleCalendars?.items.length}
                    onChange={(e) => void updateGoogle({ calendar_id: e.target.value })}
                  >
                    {!googleCalendars?.items.some((option) => option.id === google.calendar_id) && (
                      <option value={google.calendar_id}>{google.calendar_id === "primary" ? "Main calendar" : google.calendar_id}</option>
                    )}
                    {googleCalendars?.items.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.name}
                        {option.primary ? " (main)" : ""}
                      </option>
                    ))}
                  </Select>
                  {googleCalendars?.error && <p className="text-xs text-destructive">{googleCalendars.error}</p>}
                </div>
                <SwitchRow
                  title="Block busy times"
                  checked={google.check_busy}
                  disabled={googleSaving}
                  onChange={(check_busy) => void updateGoogle({ check_busy })}
                />
                <div>
                  <Button type="button" variant="outline" size="sm" onClick={() => void disconnect()} disabled={googleSaving}>
                    <Unlink className="h-3.5 w-3.5" aria-hidden />
                    Disconnect
                  </Button>
                </div>
              </>
            ) : !google.included ? (
              <GoogleUpsell />
            ) : (
              <div>
                <Button type="button" onClick={() => void connect()} disabled={connecting}>
                  {connecting ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <CalendarSync className="h-4 w-4" aria-hidden />}
                  Connect Google Calendar
                </Button>
              </div>
            )}
          </div>

          {/* Subscription feed, any calendar app */}
          <div className="grid min-w-0 content-start gap-3 rounded-md border border-border p-4">
            <div className="flex items-center gap-1.5">
              <h3 className="text-sm font-semibold">Calendar feed</h3>
              <InfoTip label="How to subscribe" width={320}>
                Read-only, for Google, Outlook or Apple. Google: <span className="text-foreground">Other calendars → + → From URL</span>. Outlook:{" "}
                <span className="text-foreground">Add calendar → Subscribe from web</span>. Apple: <span className="text-foreground">File → New Calendar Subscription</span>.
                Apps refresh every few hours.
              </InfoTip>
            </div>
            {calendar.feed_url ? (
              <>
                <div className="flex min-w-0 gap-2">
                  <Input readOnly value={calendar.feed_url} aria-label="Calendar feed link" className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
                  <CopyButton id="feed" text={calendar.feed_url} copied={copied} onCopy={copy} />
                </div>
                {!calendar.public && <SetupNote>Calendar apps can&apos;t reach this local link yet.</SetupNote>}
                <div className="flex flex-wrap gap-2">
                  {calendar.public && (
                    <Button asChild variant="outline" size="sm">
                      <a href={webcal(calendar.feed_url)}>
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                        Open in app
                      </a>
                    </Button>
                  )}
                  <Button type="button" variant="ghost" size="sm" onClick={() => void rotate()} disabled={rotating}>
                    <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                    New link
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">Keep this link private.</p>
              </>
            ) : (
              <div>
                <Button type="button" variant="outline" onClick={() => void rotate()} disabled={rotating}>
                  {rotating ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <CalendarDays className="h-4 w-4" aria-hidden />}
                  Create feed link
                </Button>
              </div>
            )}
          </div>
        </div>

        <BusyCalendarsBlock urls={calendar.busy_ics_urls} onSaved={onSaved} />

        {calendar.items.length > 0 && (
          <div className="grid gap-2">
            <div>
              <h3 className="text-sm font-semibold">{itemsLabel}</h3>
              <p className="text-xs text-muted-foreground">
                {perItemBusy ? `Each ${itemLabel}'s feed and busy calendar.` : `A feed per ${itemLabel}.`}
              </p>
            </div>
            <ul className="divide-y divide-border rounded-md border border-border">
              {calendar.items.map((item) => (
                <ItemCalendarRow
                  key={item.id}
                  item={item}
                  perItemBusy={perItemBusy}
                  googleCalendars={connected && perItemBusy ? googleCalendars?.items ?? [] : null}
                  copied={copied}
                  copy={copy}
                  onSaved={onSaved}
                />
              ))}
            </ul>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

const CALENDAR_LINK = /^(https?|webcal):\/\/\S+$/i;

function BusyCalendarsBlock({ urls, onSaved }: { urls: string[]; onSaved: (next: Integrations) => void }) {
  const toast = useAppToast();
  const source = useMemo(() => ({ urls: urls.length ? urls : [""] }), [urls]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checks, setChecks] = useState<Record<string, CalendarCheck | "checking">>({});

  const setUrl = (index: number, value: string) => setDraft((current) => ({ urls: current.urls.map((url, i) => (i === index ? value : url)) }));
  const remove = (index: number) => setDraft((current) => ({ urls: current.urls.length > 1 ? current.urls.filter((_, i) => i !== index) : [""] }));
  const add = () => setDraft((current) => ({ urls: [...current.urls, ""] }));

  const check = async (url: string) => {
    setChecks((current) => ({ ...current, [url]: "checking" }));
    try {
      const result = await integrationsApi.checkCalendar(url);
      setChecks((current) => ({ ...current, [url]: result }));
    } catch (err) {
      setChecks((current) => ({ ...current, [url]: { ok: false, error: formatApiError(err, "Could not check the link.") } }));
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const cleaned = draft.urls.map((url) => url.trim()).filter(Boolean);
    if (cleaned.some((url) => !CALENDAR_LINK.test(url))) {
      setError("Calendar links start with https:// (or webcal://).");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const next = await integrationsApi.updateCalendar({ busy_ics_urls: cleaned });
      commit({ urls: next.calendar.busy_ics_urls.length ? next.calendar.busy_ics_urls : [""] });
      onSaved(next);
      toast.success(cleaned.length ? "Busy calendars saved." : "Busy calendars removed.");
    } catch (err) {
      setError(formatApiError(err, "Could not save the busy calendars."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="grid gap-3 rounded-md border border-border p-4">
      <div>
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold">Busy calendars</h3>
          <InfoTip label="Where to find an iCal link" width={320}>
            Paste a calendar&apos;s private iCal address — Google: <span className="text-foreground">Settings → Secret address in iCal format</span>; Outlook:{" "}
            <span className="text-foreground">Publish a calendar → ICS</span>; or iCloud.
          </InfoTip>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">Their events block those times for everyone.</p>
      </div>
      {draft.urls.map((url, index) => {
        const trimmed = url.trim();
        const result = checks[trimmed];
        return (
          <div key={index} className="grid gap-1">
            <div className="flex min-w-0 gap-2">
              <Input
                value={url}
                aria-label={`Busy calendar link ${index + 1}`}
                placeholder="https://calendar.google.com/calendar/ical/…/basic.ics"
                className="font-mono text-xs"
                onChange={(e) => setUrl(index, e.target.value)}
              />
              <Button type="button" variant="outline" size="sm" className="h-10" disabled={!CALENDAR_LINK.test(trimmed) || result === "checking"} onClick={() => void check(trimmed)}>
                {result === "checking" ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Play className="h-3.5 w-3.5" aria-hidden />}
                Check
              </Button>
              <Button type="button" variant="ghost" size="sm" className="h-10" aria-label={`Remove busy calendar link ${index + 1}`} onClick={() => remove(index)}>
                <X className="h-3.5 w-3.5" aria-hidden />
              </Button>
            </div>
            {result && result !== "checking" && (
              <p role="status" className={cn("text-xs", result.ok ? "text-muted-foreground" : "text-destructive")}>
                {result.ok ? `Works — ${result.busy_count} busy ${result.busy_count === 1 ? "time" : "times"} in the next 2 weeks.` : result.error}
              </p>
            )}
          </div>
        );
      })}
      <InlineError message={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={add} disabled={draft.urls.length >= 10}>
          <Plus className="h-3.5 w-3.5" aria-hidden />
          Add link
        </Button>
        <span className="flex-1" />
        {dirty && (
          <Button type="button" variant="ghost" size="sm" onClick={reset} disabled={saving}>
            Discard
          </Button>
        )}
        <Button type="submit" size="sm" disabled={saving || !dirty}>
          {saving ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Check className="h-3.5 w-3.5" aria-hidden />}
          Save
        </Button>
      </div>
    </form>
  );
}

function ItemCalendarRow({
  item,
  perItemBusy,
  googleCalendars,
  copied,
  copy,
  onSaved,
}: {
  item: CalendarItem;
  perItemBusy: boolean;
  /** null = no Google column. */
  googleCalendars: GoogleCalendarOption[] | null;
  copied: string | null;
  copy: (id: string, text: string) => void;
  onSaved: (next: Integrations) => void;
}) {
  const toast = useAppToast();
  const source = useMemo(() => ({ calendar_ics: item.calendar_ics, google_calendar_id: item.google_calendar_id }), [item]);
  const { draft, dirty, setDraft, commit } = useDraft(source);
  const [saving, setSaving] = useState(false);
  const linkOk = !draft.calendar_ics.trim() || CALENDAR_LINK.test(draft.calendar_ics.trim());

  const save = async () => {
    if (!linkOk) {
      toast.error("Calendar links start with https:// (or webcal://).");
      return;
    }
    setSaving(true);
    try {
      const values = { calendar_ics: draft.calendar_ics.trim(), ...(googleCalendars ? { google_calendar_id: draft.google_calendar_id } : {}) };
      const next = await integrationsApi.updateItemCalendar(item.id, values);
      const saved = next.calendar.items.find((row) => row.id === item.id);
      if (saved) commit({ calendar_ics: saved.calendar_ics, google_calendar_id: saved.google_calendar_id });
      onSaved(next);
      toast.success(`Saved ${item.name}'s calendar.`);
    } catch (err) {
      toast.error(formatApiError(err, "Could not save the calendar."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <li className={cn("grid gap-3 p-3", perItemBusy && "md:grid-cols-[minmax(0,11rem)_minmax(0,1fr)_auto] md:items-center")}>
      <div className="flex min-w-0 items-center justify-between gap-2">
        <span className="truncate text-sm font-medium">{item.name}</span>
        {!perItemBusy && <CopyButton id={`feed-${item.id}`} text={item.feed_url} copied={copied} onCopy={copy} label="Copy feed" />}
      </div>
      {perItemBusy && (
        <>
          <div className={cn("grid min-w-0 gap-2", googleCalendars && "sm:grid-cols-[minmax(0,1fr)_12rem]")}>
            <Input
              value={draft.calendar_ics}
              aria-label={`${item.name}'s busy calendar (iCal link)`}
              aria-invalid={!linkOk || undefined}
              placeholder="Busy calendar — iCal link (optional)"
              className="h-9 font-mono text-xs"
              onChange={(e) => setDraft((current) => ({ ...current, calendar_ics: e.target.value }))}
            />
            {googleCalendars && (
              <Select
                aria-label={`${item.name}'s Google calendar`}
                className="h-9"
                value={draft.google_calendar_id}
                onChange={(e) => setDraft((current) => ({ ...current, google_calendar_id: e.target.value }))}
              >
                <option value="">Business calendar</option>
                {draft.google_calendar_id && !googleCalendars.some((option) => option.id === draft.google_calendar_id) && (
                  <option value={draft.google_calendar_id}>{draft.google_calendar_id}</option>
                )}
                {googleCalendars.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </Select>
            )}
          </div>
          <div className="flex gap-2">
            <CopyButton id={`feed-${item.id}`} text={item.feed_url} copied={copied} onCopy={copy} label="Copy feed" />
            <Button type="button" size="sm" disabled={!dirty || saving} onClick={() => void save()}>
              {saving ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Check className="h-3.5 w-3.5" aria-hidden />}
              Save
            </Button>
          </div>
        </>
      )}
    </li>
  );
}

// ---------------------------------------------------------------- back from Google's consent screen

const GOOGLE_RETURN: Record<string, { ok: boolean; text: string }> = {
  connected: { ok: true, text: "Google Calendar connected." },
  denied: { ok: false, text: "Google sign-in was cancelled." },
  expired: { ok: false, text: "That Google sign-in expired — connect again." },
  failed: { ok: false, text: "Google didn't complete the connection — try again." },
};

/**
 * The OAuth callback redirects to `/settings?tab=calendar&google=connected|denied|expired|failed`.
 * Toasts the result once and drops `google` from the address (other params and the hash stay).
 */
export function useGoogleCalendarReturn() {
  const toast = useAppToast();
  const handled = useRef(false);
  useEffect(() => {
    if (handled.current) return;
    handled.current = true;
    const params = new URLSearchParams(window.location.search);
    const status = params.get("google");
    if (!status) return;
    const result = GOOGLE_RETURN[status] ?? GOOGLE_RETURN.failed;
    if (result.ok) toast.success(result.text);
    else toast.error(result.text);
    params.delete("google");
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
  }, [toast]);
}
