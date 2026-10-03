"use client";

/** Website chat widget: look, embed code and a live preview (injects the real widget.js). */

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle, MessageSquare, Play, RefreshCw, RotateCcw, TriangleAlert, X } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDraft, useCopy, CopyButton, SectionCard, StatusPill, InlineError, CodeBlock, SwitchRow, browserOrigin, isLocalOrigin } from "@/components/portal/kit";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";
import { formatApiError, merchantApi, type Merchant } from "@/services/api";

const DEFAULT_WIDGET_COLOR = "#0f766e";
const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
/** The widget marks its host element with this attribute (backend/app/static/widget.js). */
const WIDGET_HOST_ATTRIBUTE = "data-agent-widget";
const PREVIEW_ATTR = "data-agent-widget-preview";

type WidgetWindow = Window & { __agentWidgetLoaded?: boolean };

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

export function WidgetSection() {
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
    if (!window.confirm("Rotate the widget key?\n\nThe code on your website stops working until you replace it.")) return;
    setRotating(true);
    try {
      const updated = await merchantApi.rotateWidgetKey();
      await refresh();
      toast.success("New key created — update the code on your website.");
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
      id="web-chat"
      icon={MessageSquare}
      title="Website chat"
      badge={<StatusPill ok={merchant.widget_enabled}>{merchant.widget_enabled ? "On" : "Off"}</StatusPill>}
    >
      <form onSubmit={submit} noValidate className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <div className="grid min-w-0 gap-4">
          <SwitchRow title="Show on my website" checked={draft.enabled} onChange={(enabled) => patch({ enabled })} />

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
              Save
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
          <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">Turn it on and save to get the code.</p>
        )}
        {snippet && (
          <p className="text-xs text-muted-foreground">
            Paste before <code className="rounded bg-secondary px-1 font-mono">&lt;/body&gt;</code> on each page.
          </p>
        )}
        {isLocalOrigin(origin) && (
          <p className="flex items-start gap-2 text-xs font-medium text-amber-700 dark:text-amber-300">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            Local address — it won&apos;t work on a live website.
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-surface p-3">
          <Button type="button" size="sm" variant={previewing ? "outline" : "default"} disabled={!live} onClick={preview}>
            {previewing ? <RefreshCw className="h-3.5 w-3.5" aria-hidden /> : <Play className="h-3.5 w-3.5" aria-hidden />}
            {previewing ? "Reload preview" : "Preview here"}
          </Button>
          {previewing && (
            <Button type="button" size="sm" variant="ghost" onClick={stopPreview}>
              <X className="h-3.5 w-3.5" aria-hidden />
              Remove preview
            </Button>
          )}
          <p className="min-w-0 flex-1 basis-56 text-xs text-muted-foreground" aria-live="polite">
            {!live
              ? "Turn it on and save to preview."
              : previewing
                ? `See the bubble, bottom ${merchant.widget_settings?.position === "left" ? "left" : "right"}.`
                : dirty
                  ? "Save first to preview changes."
                  : ""}
          </p>
        </div>
      </div>
    </SectionCard>
  );
}
