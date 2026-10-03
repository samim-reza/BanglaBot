"use client";

/**
 * Add-ons hub: website chat widget, SMS confirmations, calendar sync, webhooks,
 * the phone line, outbound calling, recordings and plan usage. Every save refreshes the workspace so the shell
 * and the other pages see the new values.
 */

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CalendarDays,
  CalendarSync,
  Check,
  CircleCheck,
  Copy,
  CreditCard,
  Eye,
  EyeOff,
  ExternalLink,
  FileText,
  LoaderCircle,
  MessageSquare,
  Phone,
  PhoneOutgoing,
  Play,
  RefreshCw,
  RotateCcw,
  Send,
  Smartphone,
  TriangleAlert,
  Unlink,
  Webhook,
  X,
  type LucideIcon,
} from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SmsMessageList } from "@/components/sms-messages";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import {
  formatApiError,
  integrationsApi,
  merchantApi,
  type CalendarCheck,
  type CalendarItem,
  type GoogleCalendarOption,
  type Integrations,
  type Merchant,
  type SmsMessage,
  type SmsSettings,
  type VerticalKey,
} from "@/services/api";

// ---------------------------------------------------------------- helpers

const DEFAULT_WIDGET_COLOR = "#0f766e";
const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
/** The widget's host element is `position:fixed` with this z-index (see backend/app/static/widget.js). */
/** The widget marks its host element with this attribute (backend/app/static/widget.js). */
const WIDGET_HOST_ATTRIBUTE = "data-agent-widget";
const PREVIEW_ATTR = "data-agent-widget-preview";

type WidgetWindow = Window & { __agentWidgetLoaded?: boolean };

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** A form draft over server values (see the settings page for the same pattern). */
function useDraft<T>(source: T) {
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

function useCopy() {
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

function CopyButton({ id, text, copied, onCopy, label = "Copy", disabled }: { id: string; text: string; copied: string | null; onCopy: (id: string, text: string) => void; label?: string; disabled?: boolean }) {
  const done = copied === id;
  return (
    <Button type="button" variant="outline" size="sm" disabled={disabled || !text} onClick={() => onCopy(id, text)}>
      {done ? <Check className="h-3.5 w-3.5 text-primary" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
      <span aria-live="polite">{done ? "Copied" : label}</span>
    </Button>
  );
}

function SectionCard({
  id,
  icon: Icon,
  title,
  description,
  badge,
  className,
  children,
}: {
  id: string;
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  badge?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Card id={id} role="region" aria-labelledby={`${id}-title`} className={cn("scroll-mt-24", className)}>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle id={`${id}-title`} className="flex items-center gap-2">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-accent text-accent-foreground">
              <Icon className="h-4 w-4" aria-hidden />
            </span>
            {title}
          </CardTitle>
          {badge}
        </div>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function StatusPill({ ok, children }: { ok: boolean; children: React.ReactNode }) {
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

function InlineError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {message}
    </p>
  );
}

function CodeBlock({ code, label }: { code: string; label: string }) {
  return (
    <pre aria-label={label} className="max-h-96 overflow-auto rounded-md border border-border bg-surface p-3 text-[12.5px] leading-relaxed">
      <code className="font-mono">{code}</code>
    </pre>
  );
}

function browserOrigin(): string {
  return typeof window === "undefined" ? "" : window.location.origin;
}

function isLocalOrigin(origin: string): boolean {
  try {
    const host = new URL(origin).hostname;
    return host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0" || host.endsWith(".local");
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------- widget preview (injects the real widget.js)

function removeWidgetPreview() {
  if (typeof document === "undefined") return;
  document.querySelectorAll(`script[${PREVIEW_ATTR}]`).forEach((node) => node.remove());
  document.querySelectorAll<HTMLElement>("body > div").forEach((node) => {
    if (node.hasAttribute(WIDGET_HOST_ATTRIBUTE)) node.remove();
  });
  const win = window as WidgetWindow;
  try {
    delete win.__agentWidgetLoaded;
  } catch {
    win.__agentWidgetLoaded = undefined;
  }
}

function injectWidgetPreview(origin: string, key: string) {
  removeWidgetPreview();
  const script = document.createElement("script");
  script.src = `${origin}/api/public/widget.js`;
  script.async = true;
  script.setAttribute("data-key", key);
  script.setAttribute(PREVIEW_ATTR, "");
  document.body.appendChild(script);
}

// ---------------------------------------------------------------- website chat widget

type WidgetForm = { enabled: boolean; title: string; subtitle: string; color: string; position: "left" | "right" };

function widgetFrom(merchant: Merchant): WidgetForm {
  const look = merchant.widget_settings ?? {};
  return {
    enabled: Boolean(merchant.widget_enabled),
    title: look.title ?? "",
    subtitle: look.subtitle ?? "",
    color: look.color && HEX_COLOR.test(look.color) ? look.color.toLowerCase() : DEFAULT_WIDGET_COLOR,
    position: look.position === "left" ? "left" : "right",
  };
}

function WidgetMock({ form, businessName, greeting }: { form: WidgetForm; businessName: string; greeting: string }) {
  const color = HEX_COLOR.test(form.color) ? form.color : DEFAULT_WIDGET_COLOR;
  const side = form.position === "left" ? "left-3" : "right-3";
  return (
    <div
      className={cn("relative h-64 overflow-hidden rounded-md border border-border bg-surface", !form.enabled && "opacity-60 grayscale")}
      role="img"
      aria-label={`Preview of the chat widget: ${form.title || businessName}, ${form.position} corner`}
    >
      {/* A stand-in "website" behind the widget. */}
      <div className="space-y-2 p-4" aria-hidden>
        <div className="h-3 w-1/3 rounded bg-border" />
        <div className="h-2 w-3/4 rounded bg-border/70" />
        <div className="h-2 w-2/3 rounded bg-border/70" />
        <div className="h-2 w-1/2 rounded bg-border/70" />
      </div>
      <div className={cn("absolute bottom-[4.25rem] w-[min(15rem,calc(100%-1.5rem))] overflow-hidden rounded-xl bg-white shadow-lg", side)} aria-hidden>
        <div className="px-3 py-2 text-white" style={{ background: color }}>
          <b className="block truncate text-[13px]">{form.title || businessName}</b>
          <span className="block truncate text-[11px] opacity-90">{form.subtitle || "We usually reply instantly"}</span>
        </div>
        <div className="space-y-1.5 bg-slate-50 p-2.5">
          <div className="w-fit max-w-[85%] rounded-lg rounded-bl-sm border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-800">{greeting}</div>
          <div className="ml-auto w-fit max-w-[85%] rounded-lg rounded-br-sm px-2 py-1 text-[11px] text-white" style={{ background: color }}>
            Are you open today?
          </div>
        </div>
      </div>
      <div className={cn("absolute bottom-3 flex h-11 w-11 items-center justify-center rounded-full text-white shadow-lg", side)} style={{ background: color }} aria-hidden>
        <MessageSquare className="h-5 w-5" />
      </div>
    </div>
  );
}

function WidgetSection() {
  const { merchant, public_base_url, refresh } = useWorkspace();
  const toast = useAppToast();
  const { copied, copy } = useCopy();
  const source = useMemo(() => widgetFrom(merchant), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const [saving, setSaving] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const injected = useRef(false);
  useEffect(() => {
    injected.current = previewing;
  }, [previewing]);

  const portalOrigin = browserOrigin();
  const origin = (public_base_url || portalOrigin).replace(/\/+$/, "");
  const key = merchant.widget_key;
  const snippet = key ? `<script src="${origin}/api/public/widget.js" data-key="${key}" async></script>` : "";
  const live = merchant.widget_enabled && Boolean(key);
  const colorOk = HEX_COLOR.test(draft.color);
  const greeting = merchant.custom_greeting?.trim() || `Hi, welcome to ${merchant.business_name}!`;

  // Leaving the page takes the preview widget with it.
  useEffect(
    () => () => {
      if (injected.current) removeWidgetPreview();
    },
    [],
  );

  const patch = (values: Partial<WidgetForm>) => setDraft((current) => ({ ...current, ...values }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!colorOk) {
      setError("The color must be a hex value like #0f766e.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await merchantApi.updateMe({
        widget_enabled: draft.enabled,
        widget_settings: { title: draft.title.trim(), subtitle: draft.subtitle.trim(), color: draft.color, position: draft.position },
      });
      commit(widgetFrom(updated));
      await refresh();
      toast.success(updated.widget_enabled ? "Chat widget saved." : "Chat widget turned off.");
      if (previewing) {
        if (updated.widget_enabled && updated.widget_key) injectWidgetPreview(portalOrigin, updated.widget_key);
        else {
          removeWidgetPreview();
          setPreviewing(false);
        }
      }
    } catch (err) {
      setError(formatApiError(err, "Could not save the chat widget."));
    } finally {
      setSaving(false);
    }
  };

  const rotate = async () => {
    if (!window.confirm("Rotate the widget key?\n\nThe snippet already on your website stops working until you replace it with the new one.")) return;
    setRotating(true);
    try {
      const updated = await merchantApi.rotateWidgetKey();
      await refresh();
      toast.success("New widget key created — update the snippet on your website.");
      if (previewing && updated.widget_enabled && updated.widget_key) injectWidgetPreview(portalOrigin, updated.widget_key);
    } catch (err) {
      toast.error(formatApiError(err, "Could not rotate the widget key."));
    } finally {
      setRotating(false);
    }
  };

  const preview = () => {
    if (!live) return;
    injectWidgetPreview(portalOrigin, key);
    setPreviewing(true);
  };

  const stopPreview = () => {
    removeWidgetPreview();
    setPreviewing(false);
  };

  return (
    <SectionCard
      id="widget"
      icon={MessageSquare}
      title="Website chat widget"
      badge={<StatusPill ok={merchant.widget_enabled}>{merchant.widget_enabled ? "On" : "Off"}</StatusPill>}
      description="The same agent as your phone line, typed — a chat bubble on your own website that answers questions and books."
    >
      <form onSubmit={submit} noValidate className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <div className="grid min-w-0 gap-4">
          <label className="flex cursor-pointer items-start justify-between gap-4 rounded-md border border-border p-3">
            <span className="min-w-0">
              <span className="block text-sm font-medium">Show the chat widget on my website</span>
              <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
                When off, the snippet stays on your site but shows nothing. Website chats count towards your plan.
              </span>
            </span>
            <input type="checkbox" role="switch" className="peer sr-only" checked={draft.enabled} onChange={(e) => patch({ enabled: e.target.checked })} />
            <span
              aria-hidden
              className="relative mt-0.5 inline-flex h-5 w-9 shrink-0 rounded-full bg-input transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-white after:shadow after:transition-transform peer-checked:bg-primary peer-checked:after:translate-x-4 peer-focus-visible:ring-2 peer-focus-visible:ring-ring"
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5 text-sm">
              <label htmlFor="widget-title" className="text-[13.5px] font-semibold text-muted-foreground">
                Title
              </label>
              <Input id="widget-title" value={draft.title} maxLength={60} placeholder={merchant.business_name} onChange={(e) => patch({ title: e.target.value })} />
            </div>
            <div className="flex flex-col gap-1.5 text-sm">
              <label htmlFor="widget-subtitle" className="text-[13.5px] font-semibold text-muted-foreground">
                Subtitle
              </label>
              <Input id="widget-subtitle" value={draft.subtitle} maxLength={80} placeholder="We usually reply instantly" onChange={(e) => patch({ subtitle: e.target.value })} />
            </div>
            <div className="flex flex-col gap-1.5 text-sm">
              <label htmlFor="widget-color-hex" className="text-[13.5px] font-semibold text-muted-foreground">
                Color
              </label>
              <div className="flex gap-2">
                <input
                  type="color"
                  aria-label="Pick a color"
                  value={colorOk ? draft.color : DEFAULT_WIDGET_COLOR}
                  onChange={(e) => patch({ color: e.target.value.toLowerCase() })}
                  className="h-10 w-12 shrink-0 cursor-pointer rounded-md border border-input bg-card p-1"
                />
                <Input
                  id="widget-color-hex"
                  value={draft.color}
                  maxLength={7}
                  spellCheck={false}
                  autoComplete="off"
                  aria-invalid={!colorOk}
                  className={cn("font-mono", !colorOk && "border-destructive")}
                  onChange={(e) => {
                    const raw = e.target.value.trim();
                    patch({ color: (raw.startsWith("#") ? raw : `#${raw}`).toLowerCase() });
                  }}
                />
              </div>
            </div>
            <fieldset className="flex flex-col gap-1.5 text-sm">
              <legend className="mb-1.5 text-[13.5px] font-semibold text-muted-foreground">Position</legend>
              <div className="inline-flex w-full rounded-md border border-input bg-card p-0.5">
                {(["left", "right"] as const).map((position) => (
                  <label
                    key={position}
                    className={cn(
                      "flex h-9 flex-1 cursor-pointer items-center justify-center rounded px-4 text-sm font-medium capitalize transition has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
                      draft.position === position ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                    )}
                  >
                    <input type="radio" className="sr-only" name="widget-position" value={position} checked={draft.position === position} onChange={() => patch({ position })} />
                    Bottom {position}
                  </label>
                ))}
              </div>
            </fieldset>
          </div>

          <InlineError message={error} />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" disabled={!dirty || saving}>
              {saving && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
              Save widget
            </Button>
            {dirty && (
              <Button type="button" variant="ghost" size="sm" disabled={saving} onClick={() => { reset(); setError(null); }}>
                <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                Discard
              </Button>
            )}
            <span className="text-xs text-muted-foreground" aria-live="polite">
              {dirty ? "Unsaved changes" : ""}
            </span>
          </div>
        </div>

        <div className="min-w-0">
          <p className="mb-1.5 text-[13.5px] font-semibold text-muted-foreground">Look</p>
          <WidgetMock form={draft} businessName={merchant.business_name} greeting={greeting} />
        </div>
      </form>

      <div className="mt-6 space-y-3 border-t border-border pt-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-sm font-semibold">Embed code</h4>
          <div className="flex flex-wrap gap-2">
            <CopyButton id="snippet" text={snippet} copied={copied} onCopy={copy} label="Copy code" />
            <Button type="button" variant="outline" size="sm" disabled={rotating || !key} onClick={rotate}>
              <RefreshCw className={cn("h-3.5 w-3.5", rotating && "animate-spin")} aria-hidden />
              Rotate key
            </Button>
          </div>
        </div>
        {snippet ? (
          <div className={cn("transition", !merchant.widget_enabled && "opacity-50")}>
            <CodeBlock code={snippet} label="Widget embed code" />
          </div>
        ) : (
          <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">Turn the widget on and save to get your embed code.</p>
        )}
        {snippet && !merchant.widget_enabled && (
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            The widget is off — this code shows nothing until you turn it on and save.
          </p>
        )}
        <div className="space-y-1.5 text-xs leading-relaxed text-muted-foreground">
          <p>
            Paste it just before <code className="rounded bg-secondary px-1 font-mono">&lt;/body&gt;</code> on every page where the chat should appear.
          </p>
          {public_base_url ? (
            <p>
              The code loads the widget from your agent server&apos;s public address (<span className="font-mono">{public_base_url}</span>). Loading it from this
              portal&apos;s address (<span className="font-mono">{portalOrigin}</span>) works too — the portal forwards <span className="font-mono">/api</span> to the same
              server.
            </p>
          ) : (
            <p>
              The code loads the widget from this portal&apos;s address, which forwards <span className="font-mono">/api</span> to your agent server. Once your server has a
              public address, loading it from there works the same way.
            </p>
          )}
          {isLocalOrigin(origin) && (
            <p className="flex items-start gap-2 font-medium text-amber-700 dark:text-amber-300">
              <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              This address only works on your own computer — use your public address on a live website.
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-surface p-3">
          <Button type="button" size="sm" variant={previewing ? "outline" : "default"} disabled={!live} onClick={preview}>
            {previewing ? <RefreshCw className="h-3.5 w-3.5" aria-hidden /> : <Play className="h-3.5 w-3.5" aria-hidden />}
            {previewing ? "Reload preview" : "Preview on this page"}
          </Button>
          {previewing && (
            <Button type="button" size="sm" variant="ghost" onClick={stopPreview}>
              <X className="h-3.5 w-3.5" aria-hidden />
              Remove preview
            </Button>
          )}
          <p className="min-w-0 flex-1 basis-56 text-xs text-muted-foreground" aria-live="polite">
            {!live
              ? "Turn the widget on and save to preview it here."
              : previewing
                ? `The chat bubble is in the bottom ${merchant.widget_settings?.position === "left" ? "left" : "right"} corner of this page — try it.`
                : dirty
                  ? "The preview shows your saved settings — save first to see your changes."
                  : "Loads your real widget on this page, exactly as visitors will see it."}
          </p>
        </div>
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- SMS confirmations + calendar sync (one GET /api/integrations)

function useIntegrations() {
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
  useEffect(() => {
    void load();
  }, [load]);
  return { data, setData, error, reload: load };
}

function SwitchRow({ title, hint, checked, onChange, disabled }: { title: string; hint?: React.ReactNode; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
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

function SetupNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-md border border-border bg-surface p-2.5 text-xs leading-relaxed text-muted-foreground">
      <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="min-w-0">{children}</span>
    </p>
  );
}

const SMS_COPY: Record<VerticalKey, { booking: string; change: string; reminder: string }> = {
  clinic: { booking: "When the agent books an appointment", change: "When an appointment is moved or cancelled", reminder: "before each appointment" },
  real_estate: { booking: "When the agent books a viewing or takes a lead", change: "When a viewing is moved or cancelled", reminder: "before each viewing" },
  home_service: { booking: "When the agent books a visit", change: "When a visit is moved or cancelled", reminder: "before each visit" },
  ecommerce: { booking: "When a customer confirms their order on the call", change: "When a customer cancels their order on the call", reminder: "" },
};

const REMINDER_HOURS = [0, 1, 2, 4, 12, 24, 48];

function reminderLabel(hours: number, when: string): string {
  if (!hours) return "No reminder";
  const span = hours % 24 === 0 ? (hours === 24 ? "1 day" : `${hours / 24} days`) : hours === 1 ? "1 hour" : `${hours} hours`;
  return `${span} ${when}`;
}

function SmsSection({ data, onSaved }: { data: Integrations; onSaved: (next: Integrations) => void }) {
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
      setError("Enter the number to text, with its country code — for example +1 617 555 0100.");
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

  return (
    <SectionCard
      id="sms"
      icon={Smartphone}
      title="SMS confirmations"
      badge={<StatusPill ok={live}>{live ? "On" : sms.settings.enabled ? "Waiting for setup" : "Off"}</StatusPill>}
      description="A text to the customer with the details after the agent books, when it changes, and a reminder before — fewer no-shows, fewer “what time was it?” calls."
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <form onSubmit={submit} noValidate className="grid min-w-0 content-start gap-3">
          {!sms.platform_ready && (
            <SetupNote>
              Texting isn&apos;t set up on this server yet — it needs Twilio credentials and a sender (<span className="font-mono">TWILIO_MESSAGING_SERVICE_SID</span>,{" "}
              <span className="font-mono">TWILIO_SMS_FROM</span> or the calling number). You can save your choices now; texts start once it is.
            </SetupNote>
          )}
          <SwitchRow
            title="Text customers automatically"
            hint="The agent also tells callers “we'll text you the details” at the end of the call."
            checked={draft.enabled}
            onChange={(enabled) => patch({ enabled })}
          />
          <div className={cn("grid gap-3", !draft.enabled && "opacity-60")}>
            <SwitchRow title={copy.booking} checked={draft.on_booking} disabled={!draft.enabled} onChange={(on_booking) => patch({ on_booking })} />
            <SwitchRow title={copy.change} checked={draft.on_change} disabled={!draft.enabled} onChange={(on_change) => patch({ on_change })} />
            {vertical.scheduled && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border p-3">
                <label htmlFor="sms-reminder" className="text-sm font-medium">
                  Reminder text
                </label>
                <Select
                  id="sms-reminder"
                  className="h-9 w-auto min-w-[13rem]"
                  disabled={!draft.enabled}
                  value={String(draft.reminder_hours)}
                  onChange={(e) => patch({ reminder_hours: Number(e.target.value) })}
                >
                  {Array.from(new Set([...REMINDER_HOURS, draft.reminder_hours])).sort((a, b) => a - b).map((hours) => (
                    <option key={hours} value={hours}>
                      {reminderLabel(hours, copy.reminder)}
                    </option>
                  ))}
                </Select>
              </div>
            )}
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Changes you make yourself in the portal don&apos;t text the customer — use <span className="font-medium text-foreground">Send SMS</span> on the{" "}
            {t(vertical.record_label, "record").toLowerCase()}&apos;s page.
          </p>
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
          <UsageMeter label="Texts this month" used={sms.sent_this_month} included={usage.plan.included_sms} unit="texts" />
          {sms.sender && <p className="text-xs text-muted-foreground">Sent from {sms.sender.startsWith("+") ? <span className="font-mono">{sms.sender}</span> : `your Twilio ${sms.sender}`}.</p>}
          <form onSubmit={sendTest} noValidate className="grid gap-2 rounded-md border border-border bg-surface p-3">
            <label htmlFor="sms-test-to" className="text-[13.5px] font-semibold text-muted-foreground">
              Send yourself a test text
            </label>
            <div className="flex gap-2">
              <Input id="sms-test-to" type="tel" inputMode="tel" autoComplete="tel" placeholder="+1 617 555 0100" value={testTo} onChange={(e) => setTestTo(e.target.value)} />
              <Button type="submit" variant="outline" disabled={testing || !sms.platform_ready} aria-label="Send test text">
                {testing ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <Send className="h-4 w-4" aria-hidden />}
              </Button>
            </div>
            {testResult && (
              <p role="status" className={cn("text-xs", testResult.status === "failed" || testResult.status === "skipped" ? "text-destructive" : "text-muted-foreground")}>
                {testResult.status === "failed" || testResult.status === "skipped" ? testResult.error || "The text wasn't sent." : `Sent to ${testResult.to_number} — it should arrive in a few seconds.`}
              </p>
            )}
            <p className="text-xs leading-relaxed text-muted-foreground">On a Twilio trial account, texts only reach numbers verified in your Twilio console.</p>
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
          <SmsMessageList messages={messages} timezone={merchant.timezone} empty="No texts yet — they show up here with their delivery status." />
        )}
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- calendar sync

function webcal(url: string): string {
  return url.replace(/^https?:\/\//i, "webcal://");
}

function CalendarSection({ data, onSaved }: { data: Integrations; onSaved: (next: Integrations) => void }) {
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
      description={`Every ${t(vertical.record_label, "booking").toLowerCase()} the agent makes lands in your calendar, and times you're busy there are never offered to callers.`}
    >
      <div className="grid gap-6">
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Google, two-way */}
          <div className="grid min-w-0 content-start gap-3 rounded-md border border-border p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">Google Calendar · two-way</h3>
              {connected && <StatusPill ok>Connected</StatusPill>}
            </div>
            {!google.available ? (
              <SetupNote>
                Not set up on this server yet. Create an OAuth client (Web application) in Google Cloud Console, set{" "}
                <span className="font-mono">GOOGLE_CLIENT_ID</span> and <span className="font-mono">GOOGLE_CLIENT_SECRET</span>, and add this redirect URI:{" "}
                <span className="break-all font-mono text-foreground">{google.redirect_uri}</span>
              </SetupNote>
            ) : connected ? (
              <>
                <p className="text-sm">
                  Signed in as <span className="font-medium">{google.email || "your Google account"}</span>. New {records} appear instantly and follow every change.
                </p>
                <div className="grid gap-1.5">
                  <label htmlFor="google-calendar" className="text-[13.5px] font-semibold text-muted-foreground">
                    Write {records} to
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
                  title="Don't offer times I'm busy"
                  hint="Events on this calendar block those times for callers. Our own bookings are already counted."
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
            ) : (
              <>
                <p className="text-sm text-muted-foreground">
                  Sign in with Google: {records} are added, moved and removed in your calendar as they happen, and your existing events keep callers away from busy times.
                </p>
                <div>
                  <Button type="button" onClick={() => void connect()} disabled={connecting}>
                    {connecting ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <CalendarSync className="h-4 w-4" aria-hidden />}
                    Connect Google Calendar
                  </Button>
                </div>
              </>
            )}
          </div>

          {/* Subscription feed, any calendar app */}
          <div className="grid min-w-0 content-start gap-3 rounded-md border border-border p-4">
            <h3 className="text-sm font-semibold">Calendar feed · Google, Outlook, Apple</h3>
            {calendar.feed_url ? (
              <>
                <div className="flex min-w-0 gap-2">
                  <Input readOnly value={calendar.feed_url} aria-label="Calendar feed link" className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
                  <CopyButton id="feed" text={calendar.feed_url} copied={copied} onCopy={copy} />
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  Subscribe in Google Calendar (<span className="text-foreground">Other calendars → + → From URL</span>), Outlook (
                  <span className="text-foreground">Add calendar → Subscribe from web</span>) or Apple Calendar (<span className="text-foreground">File → New Calendar Subscription</span>).
                  Calendar apps refresh subscriptions every few hours.
                </p>
                {!calendar.public && (
                  <SetupNote>This link points at a local address — calendar apps can&apos;t reach it until the server&apos;s PUBLIC_BASE_URL is a public https address.</SetupNote>
                )}
                <div className="flex flex-wrap gap-2">
                  {calendar.public && (
                    <Button asChild variant="outline" size="sm">
                      <a href={webcal(calendar.feed_url)}>
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                        Open in calendar app
                      </a>
                    </Button>
                  )}
                  <Button type="button" variant="ghost" size="sm" onClick={() => void rotate()} disabled={rotating}>
                    <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                    New link
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">Anyone with the link can see your {records} — treat it like a password.</p>
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">A private link any calendar app can subscribe to — read-only, no sign-in needed.</p>
                <div>
                  <Button type="button" variant="outline" onClick={() => void rotate()} disabled={rotating}>
                    {rotating ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <CalendarDays className="h-4 w-4" aria-hidden />}
                    Create feed link
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>

        <BusyCalendarsBlock urls={calendar.busy_ics_urls} onSaved={onSaved} />

        {calendar.items.length > 0 && (
          <div className="grid gap-2">
            <div>
              <h3 className="text-sm font-semibold">{itemsLabel}</h3>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {perItemBusy
                  ? `Each ${itemLabel}'s own feed, and the calendar that holds their own busy times — the agent never books over them.`
                  : `A feed per ${itemLabel}, for whoever looks after it.`}
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
        <h3 className="text-sm font-semibold">Busy calendars (iCal links)</h3>
        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
          Any calendar&apos;s private iCal address — Google (Settings → <span className="text-foreground">Secret address in iCal format</span>), Outlook (
          <span className="text-foreground">Publish a calendar → ICS</span>) or iCloud. Its events block those times for the whole business.
        </p>
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
          + Add another
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

const GOOGLE_RETURN: Record<string, { ok: boolean; text: string }> = {
  connected: { ok: true, text: "Google Calendar connected — new bookings will appear there." },
  denied: { ok: false, text: "Google sign-in was cancelled." },
  expired: { ok: false, text: "That Google sign-in expired — press Connect again." },
  failed: { ok: false, text: "Google didn't complete the connection — try again." },
};

function IntegrationsSections() {
  const { vertical } = useWorkspace();
  const toast = useAppToast();
  const { data, setData, error, reload } = useIntegrations();
  const handled = useRef(false);
  const loaded = data !== null;

  // Back from Google's consent screen: /addons?google=connected#calendar
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

  // The anchor (#sms / #calendar) exists only once the settings have loaded.
  useEffect(() => {
    if (!loaded) return;
    const id = window.location.hash.slice(1);
    if (id === "sms" || id === "calendar") document.getElementById(id)?.scrollIntoView({ block: "start" });
  }, [loaded]);

  if (error && !data) {
    return (
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-6">
          <p className="text-sm text-destructive">{error}</p>
          <Button type="button" variant="outline" size="sm" onClick={() => void reload()}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            Try again
          </Button>
        </CardContent>
      </Card>
    );
  }
  if (!data) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground">
          <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
          Loading SMS and calendar settings…
        </CardContent>
      </Card>
    );
  }
  return (
    <>
      <SmsSection data={data} onSaved={setData} />
      {vertical.scheduled && <CalendarSection data={data} onSaved={setData} />}
    </>
  );
}

// ---------------------------------------------------------------- webhooks

const NODE_SNIPPET = `// Node.js + Express
import crypto from "node:crypto";
import express from "express";

const app = express();
const SECRET = process.env.AGENT_WEBHOOK_SECRET;

// Use the RAW body: the signature is over the exact bytes we sent.
app.post("/agent-webhook", express.raw({ type: "application/json" }), (req, res) => {
  const expected = "sha256=" + crypto.createHmac("sha256", SECRET).update(req.body).digest("hex");
  const received = req.get("X-Agent-Signature") || "";
  const valid =
    received.length === expected.length &&
    crypto.timingSafeEqual(Buffer.from(received), Buffer.from(expected));
  if (!valid) return res.sendStatus(401);

  const event = JSON.parse(req.body.toString("utf8"));
  if (event.event === "call.completed") {
    // event.call.outcome, event.record?.status, …
  }
  res.sendStatus(200);
});`;

const PYTHON_SNIPPET = `# Python (Flask shown; any framework works)
import hashlib, hmac, json, os
from flask import Flask, abort, request

app = Flask(__name__)
SECRET = os.environ["AGENT_WEBHOOK_SECRET"].encode()

def is_valid(raw_body: bytes, header: str) -> bool:
    expected = "sha256=" + hmac.new(SECRET, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")

@app.post("/agent-webhook")
def agent_webhook():
    raw = request.get_data()  # the raw bytes, before any JSON parsing
    if not is_valid(raw, request.headers.get("X-Agent-Signature", "")):
        abort(401)
    event = json.loads(raw)
    if event["event"] == "call.completed":
        pass  # event["call"]["outcome"], event["record"], …
    return "", 200`;

function exampleEvent(merchant: Merchant, vertical: string, recordKind: string): string {
  const payload = {
    event: "call.completed",
    sent_at: "2026-10-03T14:32:10.512845+00:00",
    account: { id: merchant.id, business_name: merchant.business_name, vertical },
    call: {
      id: "5f0c2a9e-…",
      direction: "inbound",
      flow: `${vertical}.inbound`,
      caller_number: "+14155550100",
      outcome: "booked",
      duration_secs: 94,
      language: merchant.language || "en",
      transcript: `Agent: Hello, thank you for calling ${merchant.business_name}.\nCustomer: …`,
    },
    record: {
      id: "9b1e7c44-…",
      kind: recordKind,
      status: "confirmed",
      customer_name: "Jane Doe",
      customer_phone: "+14155550100",
      address: null,
      summary: "…",
      amount: "0.00",
      currency: merchant.currency || "USD",
      scheduled_at: "2026-10-06T09:30:00+00:00",
      catalog_item_id: null,
      details: {},
      collected: {},
    },
  };
  return JSON.stringify(payload, null, 2);
}

type TestResult = { ok: boolean; status?: number; error?: string };

function WebhookSection() {
  const { merchant, vertical, refresh } = useWorkspace();
  const toast = useAppToast();
  const { copied, copy } = useCopy();
  const source = useMemo(() => ({ url: merchant.webhook_url ?? "" }), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const [saving, setSaving] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TestResult | null>(null);
  const [reveal, setReveal] = useState(false);
  const [lang, setLang] = useState<"node" | "python">("node");

  const urlOk = !draft.url.trim() || /^https?:\/\/\S+$/.test(draft.url.trim());
  const secret = merchant.webhook_secret;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!urlOk) {
      setError("The URL must start with http:// or https://");
      return;
    }
    setSaving(true);
    setError(null);
    setResult(null);
    try {
      const updated = await merchantApi.updateMe({ webhook_url: draft.url.trim() });
      commit({ url: updated.webhook_url ?? "" });
      await refresh();
      toast.success(updated.webhook_url ? "Webhook URL saved." : "Webhooks turned off.");
    } catch (err) {
      setError(formatApiError(err, "Could not save the webhook URL."));
    } finally {
      setSaving(false);
    }
  };

  const rotate = async () => {
    if (!window.confirm("Rotate the signing secret?\n\nEvents are signed with the new secret right away — update your receiver, or it will reject them.")) return;
    setRotating(true);
    try {
      await merchantApi.rotateWebhookSecret();
      await refresh();
      setReveal(true);
      toast.success("New signing secret created.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not rotate the secret."));
    } finally {
      setRotating(false);
    }
  };

  const sendTest = async () => {
    setTesting(true);
    setResult(null);
    try {
      setResult(await merchantApi.testWebhook());
    } catch (err) {
      setResult({ ok: false, error: formatApiError(err, "Could not send the test event.") });
    } finally {
      setTesting(false);
    }
  };

  const canTest = Boolean(merchant.webhook_url) && !dirty;

  return (
    <SectionCard
      id="webhooks"
      icon={Webhook}
      title="Webhooks"
      badge={<StatusPill ok={Boolean(merchant.webhook_url)}>{merchant.webhook_url ? "Active" : "Not set"}</StatusPill>}
      description="Get every finished call and chat in your own system — CRM, spreadsheet, Zapier or your code. We POST signed JSON to your URL."
    >
      <form onSubmit={submit} noValidate className="space-y-3">
        <div className="flex flex-col gap-1.5 text-sm">
          <label htmlFor="webhook-url" className="text-[13.5px] font-semibold text-muted-foreground">
            Endpoint URL
          </label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              id="webhook-url"
              type="url"
              inputMode="url"
              value={draft.url}
              maxLength={500}
              spellCheck={false}
              placeholder="https://example.com/agent-webhook"
              aria-invalid={!urlOk}
              aria-describedby="webhook-url-hint"
              className={cn("font-mono", !urlOk && "border-destructive")}
              onChange={(e) => setDraft(() => ({ url: e.target.value }))}
            />
            <div className="flex shrink-0 gap-2">
              <Button type="submit" size="sm" className="h-10 flex-1 sm:flex-none" disabled={!dirty || saving}>
                {saving && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
                Save
              </Button>
              {dirty && (
                <Button type="button" variant="ghost" size="sm" className="h-10" disabled={saving} onClick={() => { reset(); setError(null); }}>
                  Discard
                </Button>
              )}
            </div>
          </div>
          <p id="webhook-url-hint" className="text-xs text-muted-foreground">
            Leave empty to turn webhooks off. We wait up to 6 seconds for a 2xx answer and don&apos;t retry.
          </p>
        </div>
        <InlineError message={error} />
      </form>

      <div className="mt-5 grid gap-4 border-t border-border pt-5 md:grid-cols-2">
        <div className="min-w-0 space-y-2">
          <h4 className="text-sm font-semibold">Signing secret</h4>
          {secret ? (
            <>
              <div className="flex min-w-0 items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-md border border-border bg-surface px-3 py-2 font-mono text-[12.5px]" aria-label="Signing secret">
                  {reveal ? secret : "•".repeat(Math.min(32, secret.length))}
                </code>
                <Button type="button" variant="outline" size="icon" className="h-9 w-9 shrink-0" aria-label={reveal ? "Hide secret" : "Reveal secret"} aria-pressed={reveal} onClick={() => setReveal((value) => !value)}>
                  {reveal ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <CopyButton id="secret" text={secret} copied={copied} onCopy={copy} label="Copy secret" />
                <Button type="button" variant="outline" size="sm" disabled={rotating} onClick={rotate}>
                  <RefreshCw className={cn("h-3.5 w-3.5", rotating && "animate-spin")} aria-hidden />
                  Rotate secret
                </Button>
              </div>
            </>
          ) : (
            <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">A secret is created when you save a URL.</p>
          )}
        </div>
        <div className="min-w-0 space-y-2">
          <h4 className="text-sm font-semibold">Test delivery</h4>
          <p className="text-xs text-muted-foreground">
            Sends a <code className="rounded bg-secondary px-1 font-mono">test</code> event to your saved URL.
          </p>
          <Button type="button" variant="outline" size="sm" disabled={!canTest || testing} onClick={sendTest}>
            {testing ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Send className="h-3.5 w-3.5" aria-hidden />}
            Send test event
          </Button>
          {!merchant.webhook_url && <p className="text-xs text-muted-foreground">Save a URL first.</p>}
          {merchant.webhook_url && dirty && <p className="text-xs text-muted-foreground">Save your URL change first.</p>}
          <div aria-live="polite">
            {result &&
              (result.ok ? (
                <p className="flex items-start gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-[#065f46] dark:text-emerald-300">
                  <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  Delivered — your endpoint answered HTTP {result.status ?? "2xx"}.
                </p>
              ) : (
                <p className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  <span className="min-w-0 break-words">
                    {result.status ? `Not delivered — your endpoint answered HTTP ${result.status}.` : `Not delivered — ${result.error || "your endpoint could not be reached"}.`}
                  </span>
                </p>
              ))}
          </div>
        </div>
      </div>

      <details className="group mt-5 rounded-md border border-border">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-semibold [&::-webkit-details-marker]:hidden">
          <span className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" aria-hidden />
            Developer docs: events and signature check
          </span>
          <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-90" aria-hidden />
        </summary>
        <div className="space-y-4 border-t border-border px-4 py-4 text-sm">
          <div className="space-y-2">
            <h5 className="font-semibold">Events</h5>
            <ul className="space-y-1 text-muted-foreground">
              <li>
                <code className="rounded bg-secondary px-1 font-mono text-foreground">call.completed</code> — a phone call, test call or chat has ended.{" "}
                <code className="font-mono">record</code> is the {t(vertical.record_label, "record").toLowerCase()} it handled, or <code className="font-mono">null</code>.
              </li>
              <li>
                <code className="rounded bg-secondary px-1 font-mono text-foreground">test</code> — sent by the &quot;Send test event&quot; button.
              </li>
            </ul>
            <CodeBlock label="Example call.completed event" code={exampleEvent(merchant, vertical.key, vertical.record_kind)} />
          </div>
          <div className="space-y-2">
            <h5 className="font-semibold">Verify the signature</h5>
            <p className="text-muted-foreground">
              Every request carries <code className="rounded bg-secondary px-1 font-mono text-foreground">X-Agent-Signature: sha256=&lt;hex&gt;</code> — the HMAC-SHA256 of the
              raw request body, keyed with your signing secret. Compute it over the exact bytes you received (before parsing JSON) and compare in constant time; reject
              the request if it doesn&apos;t match.
            </p>
            <div role="tablist" aria-label="Code language" className="inline-flex rounded-md border border-input bg-card p-0.5">
              {(
                [
                  ["node", "Node.js"],
                  ["python", "Python"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={lang === value}
                  onClick={() => setLang(value)}
                  className={cn(
                    "h-8 rounded px-3 text-[13px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    lang === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="relative">
              <CodeBlock label={lang === "node" ? "Node.js example" : "Python example"} code={lang === "node" ? NODE_SNIPPET : PYTHON_SNIPPET} />
              <div className="absolute right-2 top-2">
                <CopyButton id={`code-${lang}`} text={lang === "node" ? NODE_SNIPPET : PYTHON_SNIPPET} copied={copied} onCopy={copy} />
              </div>
            </div>
          </div>
        </div>
      </details>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- phone line / outbound / recordings

function PhoneLineSection() {
  const { merchant, telephony } = useWorkspace();
  const { copied, copy } = useCopy();
  const number = merchant.inbound_number?.trim();
  return (
    <SectionCard
      id="phone"
      icon={Phone}
      title="Phone line"
      badge={<StatusPill ok={telephony.twilio_configured}>{telephony.twilio_configured ? "Calling ready" : "Calling not set up"}</StatusPill>}
    >
      <div className="space-y-3 text-sm">
        {number ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-lg font-semibold tabular-nums">{number}</span>
              <CopyButton id="number" text={number} copied={copied} onCopy={copy} />
            </div>
            <p className="text-muted-foreground">Forward your business number to this number to let your agent answer your calls.</p>
          </>
        ) : (
          <p className="text-muted-foreground">
            No phone number yet — ask your admin to assign a number. Until then, try your agent with a{" "}
            <Link href="/test" className="font-medium text-primary underline-offset-2 hover:underline">
              browser call or chat
            </Link>
            .
          </p>
        )}
        {!telephony.twilio_configured && (
          <p className="flex items-start gap-2 rounded-md border border-border bg-surface p-2.5 text-xs text-muted-foreground">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            Phone calling isn&apos;t set up on this server yet — browser test calls and chat still work.
          </p>
        )}
        {telephony.twilio_configured && telephony.platform_number && (
          <p className="text-xs text-muted-foreground">
            Calls your agent makes show <span className="font-mono">{telephony.platform_number}</span> as the caller ID.
          </p>
        )}
      </div>
    </SectionCard>
  );
}

function OutboundSection() {
  const { vertical, telephony } = useWorkspace();
  const label = t(vertical.outbound_label, "Outbound calls");
  const plural = t(vertical.record_label_plural, "records");
  const singular = t(vertical.record_label, "record").toLowerCase();
  return (
    <SectionCard id="outbound" icon={PhoneOutgoing} title="Outbound calling" badge={<span className="text-xs font-medium text-muted-foreground">{label}</span>}>
      <div className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          {label}s: your agent phones customers about their {plural.toLowerCase()}. Call one {singular} from its page, everyone who still needs a call with{" "}
          <span className="font-medium text-foreground">Call all</span>, or schedule an <span className="font-medium text-foreground">auto-call</span> to run at a set time —
          both live on the {plural} page.
        </p>
        {!telephony.twilio_configured && <p className="text-xs text-muted-foreground">Needs phone calling to be set up on the server.</p>}
        <Button asChild variant="outline" size="sm">
          <Link href="/orders">
            Open {plural}
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </Button>
      </div>
    </SectionCard>
  );
}

function RecordingsSection() {
  return (
    <SectionCard id="recordings" icon={FileText} title="Recordings & transcripts">
      <div className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          Phone calls are recorded, and every call and chat — including test calls and website chats — gets a transcript and an outcome you can review.
        </p>
        <Button asChild variant="outline" size="sm">
          <Link href="/calls">
            Open call history
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </Button>
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- plan & usage

const NEXT_PLAN: Record<string, string> = { trial: "growth", starter: "growth", growth: "pro", pro: "enterprise" };

/** Plan prices are list prices in USD: "$149", "$0.22". */
function usd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatNumber(value: number, digits = 1): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function UsageMeter({ label, used, included, unit }: { label: string; used: number; included: number; unit: string }) {
  const unlimited = !included;
  const pct = unlimited ? 0 : Math.min(100, (used / included) * 100);
  const over = !unlimited && used > included;
  const near = !unlimited && !over && pct >= 80;
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          <span className="font-semibold text-foreground">{formatNumber(used)}</span>
          {unlimited ? ` ${unit} · custom volume` : ` / ${formatNumber(included, 0)} ${unit}`}
        </span>
      </div>
      {!unlimited && (
        <div
          role="meter"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={included}
          aria-valuenow={Math.min(used, included)}
          aria-valuetext={`${formatNumber(used)} of ${formatNumber(included, 0)} ${unit}`}
          className="mt-2 h-2 overflow-hidden rounded-full bg-secondary"
        >
          <div className={cn("h-full rounded-full transition-[width]", over ? "bg-destructive" : near ? "bg-amber-500" : "bg-primary")} style={{ width: `${pct}%` }} />
        </div>
      )}
      {(over || near) && (
        <p className={cn("mt-1.5 flex items-center gap-1.5 text-xs font-medium", over ? "text-destructive" : "text-amber-700 dark:text-amber-300")}>
          <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
          {over ? "Over your plan's allowance" : "Close to your plan's allowance"}
        </p>
      )}
    </div>
  );
}

function PlanSection() {
  const { usage } = useWorkspace();
  const plan = usage.plan;
  const periodStart = new Date(usage.period_start);
  const since = Number.isNaN(periodStart.getTime())
    ? ""
    : new Intl.DateTimeFormat("en-US", { day: "numeric", month: "short", timeZone: "UTC" }).format(periodStart);
  const overageCost = usage.overage_minutes * plan.overage_per_minute;
  const nextPlan = NEXT_PLAN[plan.key];
  const contactHref = nextPlan ? `/contact?plan=${nextPlan}` : "/contact";

  return (
    <SectionCard
      id="plan"
      icon={CreditCard}
      title="Plan & usage"
      description={since ? `This month, since ${since} (UTC).` : "This month."}
      badge={
        <Button asChild size="sm">
          <Link href={contactHref} target="_blank" rel="noopener">
            {nextPlan ? "Upgrade" : "Talk to us"}
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </Button>
      }
    >
      <div className="grid gap-6 md:grid-cols-[14rem_minmax(0,1fr)]">
        <div className="min-w-0 rounded-md border border-border bg-surface p-4">
          <p className="text-[13px] font-medium text-muted-foreground">Current plan</p>
          <p className="mt-1 text-xl font-bold">{plan.name}</p>
          <p className="mt-0.5 text-sm tabular-nums text-muted-foreground">{plan.price_month ? `${usd(plan.price_month)} / month` : "Free"}</p>
          {plan.tagline && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{plan.tagline}</p>}
        </div>
        <div className="grid min-w-0 gap-5">
          <UsageMeter label="Call minutes" used={usage.minutes} included={plan.included_minutes} unit="min" />
          <div className="grid gap-3 text-sm sm:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">Minutes left</p>
              <p className="font-semibold tabular-nums">{usage.minutes_left === null ? "—" : formatNumber(usage.minutes_left)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Calls</p>
              <p className="font-semibold tabular-nums">{usage.calls.toLocaleString("en-US")}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Overage</p>
              <p className="font-semibold tabular-nums">
                {usage.overage_minutes > 0 ? `${formatNumber(usage.overage_minutes)} min · ${usd(overageCost)}` : "None"}
              </p>
              {plan.overage_per_minute > 0 && <p className="text-xs text-muted-foreground">{usd(plan.overage_per_minute)} per extra minute</p>}
            </div>
          </div>
          <UsageMeter label="Website chats" used={usage.chats} included={plan.included_chats} unit="chats" />
          <UsageMeter label="Texts (SMS)" used={usage.sms ?? 0} included={plan.included_sms ?? 0} unit="texts" />
          <p className="text-xs text-muted-foreground">
            Phone calls (inbound and outbound), website chats and texts count. Browser test calls and test chats are free.
          </p>
        </div>
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- page

export default function AddonsPage() {
  const { vertical } = useWorkspace();
  const outbound = vertical.directions.includes("outbound");
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader title="Add-ons" subtitle="Website chat, SMS, calendar sync, webhooks, your phone line and what you've used this month." />
      <WidgetSection />
      <IntegrationsSections />
      <WebhookSection />
      <div className={cn("grid gap-6", outbound ? "lg:grid-cols-3" : "md:grid-cols-2")}>
        <PhoneLineSection />
        {outbound && <OutboundSection />}
        <RecordingsSection />
      </div>
      <PlanSection />
    </div>
  );
}
