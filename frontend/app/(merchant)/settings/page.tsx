"use client";

/**
 * Account settings: one card per concern, each with its own draft, dirty state
 * and Save button. Values come from the workspace (`useWorkspace()`); after a
 * save the card adopts what the server returned and the workspace is refreshed
 * so the shell (business name, plan, …) updates too.
 */

import { FormEvent, createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  BookOpenText,
  Bot,
  Building2,
  Eye,
  EyeOff,
  Globe,
  KeyRound,
  LoaderCircle,
  Plus,
  RotateCcw,
  Route,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  type LucideIcon,
} from "lucide-react";

import { ApiError } from "@/components/api-error";
import { useAppToast } from "@/components/app-toast";
import { PageHeader } from "@/components/page-header";
import { SchemaFields, compactValues, type FormValues } from "@/components/schema-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { formatInZone, money, t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import {
  formatApiError,
  merchantApi,
  type FieldSpec,
  type FlowPreview,
  type Language,
  type Merchant,
  type VerticalKey,
  type VerticalSpec,
  type VoicePersona,
} from "@/services/api";

// ---------------------------------------------------------------- constants

const GREETING_MAX = 300;
const KNOWLEDGE_MAX = 8000;
/** The agent reads the whole knowledge base; past this length, nudge the owner to keep it focused. */
const KNOWLEDGE_USED = 7000;
const SILENCE_OPTIONS = [5, 6, 8, 10, 12, 15, 20, 25, 30];
const MAX_CALL_OPTIONS = [0, 120, 180, 240, 300, 420, 600, 900];
const MAX_TIME_WINDOWS = 6;

const COMMON_TIME_ZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Phoenix",
  "America/Los_Angeles",
  "America/Anchorage",
  "Pacific/Honolulu",
  "America/Toronto",
  "America/Vancouver",
  "America/Halifax",
  "America/Mexico_City",
  "America/Sao_Paulo",
  "Europe/London",
  "Europe/Dublin",
  "Europe/Lisbon",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Madrid",
  "Europe/Rome",
  "Europe/Amsterdam",
  "Europe/Istanbul",
  "Africa/Cairo",
  "Africa/Lagos",
  "Africa/Nairobi",
  "Africa/Johannesburg",
  "Asia/Riyadh",
  "Asia/Dubai",
  "Asia/Karachi",
  "Asia/Kolkata",
  "Asia/Dhaka",
  "Asia/Bangkok",
  "Asia/Singapore",
  "Asia/Hong_Kong",
  "Asia/Shanghai",
  "Asia/Tokyo",
  "Asia/Seoul",
  "Australia/Perth",
  "Australia/Brisbane",
  "Australia/Sydney",
  "Australia/Melbourne",
  "Pacific/Auckland",
];

const KNOWLEDGE_EXAMPLES: Record<VerticalKey, string> = {
  ecommerce: `About us: [Store name] sells [what you sell] online.
Delivery: [2–4 business days] within [country]; express delivery in [1 day] for [$9.99].
Payment: cash on delivery for orders under [$300]; cards and PayPal online.
Returns: free returns within [30 days] for unused items with tags; refunds within [5–7 days].
Exchanges: size exchanges are free.
Address changes: possible until the order is dispatched.
Support hours: [Monday–Saturday, 9am–7pm].
FAQ — Do you ship abroad? [Not yet — only within the country.]
FAQ — How do I track my order? [A tracking link is sent by SMS once it ships.]`,
  clinic: `Address: [450 Main Street, Suite 200, City] — [across from the station; free parking behind the building].
Opening hours: [Mon–Fri 8am–6pm, Sat 9am–1pm, closed Sunday].
Insurance: we accept [Aetna, Cigna, Blue Cross]; self-pay patients are welcome.
New patients: please arrive [15 minutes] early with a photo ID [and insurance card].
Cancellations: please give at least [24 hours] notice.
Walk-ins: seen only for urgent issues, subject to availability.
Test results: discussed at a follow-up visit, not over the phone.
FAQ — Do you see children? [Yes, our pediatrician sees children from birth to 16.]
FAQ — Is there wheelchair access? [Yes, step-free entrance and lift.]`,
  real_estate: `Office: [120 Harbor Drive, City]. Office hours [Mon–Sat 9am–6pm].
Areas we cover: [Downtown, Riverside, North Hills].
Fees: buyers pay [no agency fee]; sellers pay [a 3% commission, negotiable].
Rentals: [one month's deposit plus the first month's rent]; pets [allowed in some listings].
Viewings: always with a licensed agent; please bring a photo ID.
Mortgages: we work with [lender name] for pre-approvals.
Selling: free valuation visit within [48 hours].
FAQ — Can I view on Sunday? [By appointment only.]
FAQ — Are prices negotiable? [Some are — the agent confirms at the viewing.]`,
  home_service: `Company: [Name], licensed and insured in [areas].
Call-out charge: [$79], waived if you go ahead with the repair.
Payment: [cards, Apple Pay, cash]; payment after the job is done.
Warranty: [90-day] workmanship warranty on all repairs.
Arrival: the technician calls [30 minutes] before arriving.
Same-day visits: depend on availability.
Hours: [Mon–Sat 8am–6pm]; [no Sunday visits].
FAQ — Do you bring parts? [Common parts are on the van; others within 2 days.]
FAQ — Do you give quotes over the phone? [Only the call-out charge and the usual price range — the technician quotes after inspection.]`,
};

// ---------------------------------------------------------------- helpers

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * A form draft over server values. When the server values change (after a
 * workspace refresh) an untouched draft follows them; an edited one is kept.
 * `commit()` adopts freshly saved values as the new baseline.
 */
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

/** Saving state + inline error for one card. */
function useSaver() {
  const toast = useAppToast();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(
    async (task: () => Promise<void>, success: string, fallback = "Could not save your changes.") => {
      setSaving(true);
      setError(null);
      try {
        await task();
        toast.success(success);
        return true;
      } catch (err) {
        setError(formatApiError(err, fallback));
        return false;
      } finally {
        setSaving(false);
      }
    },
    [toast],
  );
  return { saving, error, setError, run };
}

function validTimeZone(zone: string): boolean {
  if (!zone.trim()) return false;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: zone.trim() });
    return true;
  } catch {
    return false;
  }
}

/** Page-level registry of which cards have unsaved edits (for the nav dots and the unload guard). */
const DirtyContext = createContext<(id: string, dirty: boolean) => void>(() => undefined);

function useReportDirty(id: string, dirty: boolean) {
  const report = useContext(DirtyContext);
  useEffect(() => {
    report(id, dirty);
  }, [id, dirty, report]);
  useEffect(() => () => report(id, false), [id, report]);
}

// ---------------------------------------------------------------- building blocks

function SectionCard({
  id,
  icon: Icon,
  title,
  description,
  children,
}: {
  id: string;
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card id={id} role="region" className="scroll-mt-24" aria-labelledby={`${id}-title`}>
      <CardHeader>
        <CardTitle id={`${id}-title`} className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" aria-hidden />
          {title}
        </CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function FormRow({
  id,
  label,
  hint,
  aside,
  className,
  children,
}: {
  id: string;
  label: string;
  hint?: React.ReactNode;
  aside?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5 text-sm", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-[13.5px] font-semibold text-muted-foreground">
          {label}
        </label>
        {aside}
      </div>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="text-xs leading-relaxed text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}

function Counter({ value, max, warnAt }: { value: number; max: number; warnAt?: number }) {
  const over = value > max;
  const warn = warnAt !== undefined && value > warnAt;
  return (
    <span
      className={cn(
        "shrink-0 text-xs tabular-nums",
        over ? "font-semibold text-destructive" : warn ? "font-medium text-amber-700 dark:text-amber-300" : "text-muted-foreground",
      )}
      aria-live="polite"
    >
      {value.toLocaleString("en-US")} / {max.toLocaleString("en-US")}
    </span>
  );
}

function Segmented<T extends string>({
  name,
  label,
  value,
  options,
  onChange,
}: {
  name: string;
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-1.5 text-sm">
      <legend className="mb-1.5 text-[13.5px] font-semibold text-muted-foreground">{label}</legend>
      <div className="inline-flex w-full rounded-md border border-input bg-card p-0.5 sm:w-auto">
        {options.map((option) => {
          const active = option.value === value;
          return (
            <label
              key={option.value}
              className={cn(
                "flex h-9 flex-1 cursor-pointer items-center justify-center rounded px-4 text-sm font-medium transition has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring sm:flex-none",
                active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
              )}
            >
              <input
                type="radio"
                className="sr-only"
                name={name}
                value={option.value}
                checked={active}
                onChange={() => onChange(option.value)}
              />
              {option.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 rounded-md border border-border p-3">
      <span className="min-w-0">
        <span className="block text-sm font-medium">{label}</span>
        {description && <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">{description}</span>}
      </span>
      <input type="checkbox" role="switch" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span
        aria-hidden
        className="relative mt-0.5 inline-flex h-5 w-9 shrink-0 rounded-full bg-input transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-white after:shadow after:transition-transform peer-checked:bg-primary peer-checked:after:translate-x-4 peer-focus-visible:ring-2 peer-focus-visible:ring-ring"
      />
    </label>
  );
}

function SaveBar({
  dirty,
  saving,
  error,
  onReset,
  label = "Save changes",
}: {
  dirty: boolean;
  saving: boolean;
  error: string | null;
  onReset: () => void;
  label?: string;
}) {
  return (
    <div className="mt-5 space-y-3 border-t border-border pt-4">
      {error && (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {saving ? (
            "Saving…"
          ) : dirty ? (
            <span className="inline-flex items-center gap-1.5 font-medium text-amber-700 dark:text-amber-300">
              <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
              Unsaved changes
            </span>
          ) : (
            "No unsaved changes"
          )}
        </p>
        <div className="flex gap-2">
          {dirty && (
            <Button type="button" variant="ghost" size="sm" onClick={onReset} disabled={saving}>
              <RotateCcw className="h-3.5 w-3.5" aria-hidden />
              Discard
            </Button>
          )}
          <Button type="submit" size="sm" disabled={!dirty || saving} className="flex-1 sm:flex-none">
            {saving && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
            {label}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- business profile

type ProfileForm = { business_name: string; owner_name: string; phone: string; email: string; support_phone: string };

function profileFrom(merchant: Merchant): ProfileForm {
  return {
    business_name: merchant.business_name ?? "",
    owner_name: merchant.owner_name ?? "",
    phone: merchant.phone ?? "",
    email: merchant.email ?? "",
    support_phone: merchant.support_phone ?? "",
  };
}

function ProfileSection({ onSaved }: { onSaved: () => void }) {
  const { merchant, refresh } = useWorkspace();
  const source = useMemo(() => profileFrom(merchant), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  useReportDirty("profile", dirty);

  const set = (key: keyof ProfileForm) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!draft.business_name.trim()) {
      setError("Business name is required — your agent introduces itself with it.");
      return;
    }
    void run(async () => {
      const updated = await merchantApi.updateMe({
        business_name: draft.business_name.trim(),
        owner_name: draft.owner_name.trim(),
        phone: draft.phone.trim(),
        email: draft.email.trim(),
        support_phone: draft.support_phone.trim(),
      });
      commit(profileFrom(updated));
      await refresh();
      onSaved();
    }, "Business profile saved.");
  };

  return (
    <SectionCard id="profile" icon={Building2} title="Business profile" description="Who you are. The business name is what your agent introduces itself with.">
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit} noValidate>
        <FormRow id="business_name" label="Business name *">
          <Input id="business_name" value={draft.business_name} onChange={set("business_name")} maxLength={160} required autoComplete="organization" />
        </FormRow>
        <FormRow id="owner_name" label="Owner name">
          <Input id="owner_name" value={draft.owner_name} onChange={set("owner_name")} maxLength={120} autoComplete="name" />
        </FormRow>
        <FormRow id="phone" label="Phone" hint="Your contact number for the platform team.">
          <Input id="phone" type="tel" inputMode="tel" value={draft.phone} onChange={set("phone")} maxLength={32} aria-describedby="phone-hint" autoComplete="tel" />
        </FormRow>
        <FormRow id="email" label="Email">
          <Input id="email" type="email" value={draft.email} onChange={set("email")} maxLength={160} autoComplete="email" />
        </FormRow>
        <FormRow
          id="support_phone"
          label="Live transfer number"
          className="sm:col-span-2"
          hint="Your agent puts callers through to this number when they ask for a person. Leave it empty and the agent tells them a team member will call back."
        >
          <Input
            id="support_phone"
            type="tel"
            inputMode="tel"
            value={draft.support_phone}
            onChange={set("support_phone")}
            maxLength={32}
            placeholder="+1 415 555 0100"
            aria-describedby="support_phone-hint"
          />
        </FormRow>
        <div className="sm:col-span-2">
          <SaveBar dirty={dirty} saving={saving} error={error} onReset={() => { reset(); setError(null); }} label="Save profile" />
        </div>
      </form>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- agent voice & behaviour

type AgentForm = {
  language: Language;
  voice_persona: VoicePersona;
  custom_greeting: string;
  silence_hangup_secs: number;
  max_call_seconds: number;
  verify_address: boolean;
};

function agentFrom(merchant: Merchant): AgentForm {
  return {
    language: merchant.language === "bn" ? "bn" : "en",
    voice_persona: merchant.voice_persona === "male" ? "male" : "female",
    custom_greeting: merchant.custom_greeting ?? "",
    silence_hangup_secs: merchant.silence_hangup_secs || 10,
    max_call_seconds: merchant.max_call_seconds || 0,
    verify_address: Boolean(merchant.verify_address),
  };
}

function maxCallLabel(seconds: number): string {
  if (!seconds) return "Platform default";
  return seconds % 60 === 0 ? `${seconds / 60} minutes` : `${seconds} seconds`;
}

function withCurrent(options: number[], current: number): number[] {
  return options.includes(current) ? options : [...options, current].sort((a, b) => a - b);
}

function AgentSection({ onSaved }: { onSaved: () => void }) {
  const { merchant, vertical, refresh } = useWorkspace();
  const source = useMemo(() => agentFrom(merchant), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  useReportDirty("agent", dirty);
  const isEcommerce = vertical.key === "ecommerce";
  const defaultGreeting = `Hello, thank you for calling ${merchant.business_name || "your business"}.`;

  const patch = (values: Partial<AgentForm>) => setDraft((current) => ({ ...current, ...values }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (draft.custom_greeting.length > GREETING_MAX) {
      setError(`The greeting can be at most ${GREETING_MAX} characters.`);
      return;
    }
    void run(async () => {
      const updated = await merchantApi.updateMe({
        language: draft.language,
        // The chosen language is the call language (no auto-detect between languages).
        supported_languages: [draft.language],
        voice_persona: draft.voice_persona,
        custom_greeting: draft.custom_greeting.trim(),
        silence_hangup_secs: draft.silence_hangup_secs,
        max_call_seconds: draft.max_call_seconds,
        ...(isEcommerce ? { verify_address: draft.verify_address } : {}),
      });
      commit(agentFrom(updated));
      await refresh();
      onSaved();
    }, "Agent settings saved.");
  };

  return (
    <SectionCard id="agent" icon={Bot} title="Agent voice & behaviour" description="How your agent sounds and when it ends a call.">
      <form className="grid gap-5" onSubmit={submit} noValidate>
        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Segmented<Language>
              name="language"
              label="Language"
              value={draft.language}
              options={[
                { value: "en", label: "English" },
                { value: "bn", label: "Bangla" },
              ]}
              onChange={(language) => patch({ language })}
            />
            <p className="text-xs leading-relaxed text-muted-foreground">
              English is the main language today. Bangla is available for customers in Bangladesh.
            </p>
          </div>
          <div className="space-y-1.5">
            <Segmented<VoicePersona>
              name="voice_persona"
              label="Voice"
              value={draft.voice_persona}
              options={[
                { value: "female", label: "Female" },
                { value: "male", label: "Male" },
              ]}
              onChange={(voice_persona) => patch({ voice_persona })}
            />
            <p className="text-xs leading-relaxed text-muted-foreground">The accent follows your region.</p>
          </div>
        </div>

        <FormRow
          id="custom_greeting"
          label="Greeting"
          aside={<Counter value={draft.custom_greeting.length} max={GREETING_MAX} />}
          hint="Said word for word at the start of every call and chat. Leave empty to use the default shown above."
        >
          <Textarea
            id="custom_greeting"
            rows={2}
            maxLength={GREETING_MAX}
            value={draft.custom_greeting}
            placeholder={defaultGreeting}
            aria-describedby="custom_greeting-hint"
            onChange={(e) => patch({ custom_greeting: e.target.value })}
          />
        </FormRow>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormRow
            id="silence_hangup_secs"
            label="Silence before hanging up"
            hint="After this much silence the agent asks whether the caller can hear it; after the same again, it ends the call."
          >
            <Select
              id="silence_hangup_secs"
              value={String(draft.silence_hangup_secs)}
              aria-describedby="silence_hangup_secs-hint"
              onChange={(e) => patch({ silence_hangup_secs: Number(e.target.value) })}
            >
              {withCurrent(SILENCE_OPTIONS, draft.silence_hangup_secs).map((value) => (
                <option key={value} value={value}>
                  {value} seconds
                </option>
              ))}
            </Select>
          </FormRow>
          <FormRow id="max_call_seconds" label="Maximum call length" hint="The agent politely wraps up a call that reaches this length.">
            <Select
              id="max_call_seconds"
              value={String(draft.max_call_seconds)}
              aria-describedby="max_call_seconds-hint"
              onChange={(e) => patch({ max_call_seconds: Number(e.target.value) })}
            >
              {withCurrent(MAX_CALL_OPTIONS, draft.max_call_seconds).map((value) => (
                <option key={value} value={value}>
                  {maxCallLabel(value)}
                </option>
              ))}
            </Select>
          </FormRow>
        </div>

        {isEcommerce && (
          <Toggle
            checked={draft.verify_address}
            onChange={(verify_address) => patch({ verify_address })}
            label="Verify the delivery address"
            description="On confirmation calls the agent reads the address back and asks the customer to confirm or correct it."
          />
        )}

        <SaveBar dirty={dirty} saving={saving} error={error} onReset={() => { reset(); setError(null); }} label="Save agent settings" />
      </form>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- region & locale

type RegionForm = { timezone: string; currency: string; emergency_number: string };

function regionFrom(merchant: Merchant): RegionForm {
  return { timezone: merchant.timezone ?? "", currency: merchant.currency ?? "", emergency_number: merchant.emergency_number ?? "" };
}

function RegionSection({ onSaved }: { onSaved: () => void }) {
  const { merchant, regions, refresh } = useWorkspace();
  const source = useMemo(() => regionFrom(merchant), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  useReportDirty("region", dirty);

  const region = regions.find((item) => item.code === merchant.region);
  const zoneOptions = useMemo(() => {
    const seen = new Set<string>();
    const out: { value: string; label: string }[] = [];
    for (const item of regions) {
      if (!seen.has(item.timezone)) {
        seen.add(item.timezone);
        out.push({ value: item.timezone, label: item.label });
      }
    }
    for (const zone of COMMON_TIME_ZONES) {
      if (!seen.has(zone)) {
        seen.add(zone);
        out.push({ value: zone, label: "" });
      }
    }
    return out;
  }, [regions]);

  const zoneOk = validTimeZone(draft.timezone);
  const currencyOk = /^[A-Z]{3}$/.test(draft.currency);
  const emergencyDigits = draft.emergency_number.replace(/\D/g, "");
  const emergencyOk = emergencyDigits.length >= 2 && emergencyDigits.length <= 8;
  const regionDefaults: RegionForm | null = region
    ? { timezone: region.timezone, currency: region.currency, emergency_number: region.emergency }
    : null;

  const patch = (values: Partial<RegionForm>) => setDraft((current) => ({ ...current, ...values }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!zoneOk) return setError("Choose a valid time zone, e.g. America/New_York.");
    if (!currencyOk) return setError("Currency must be a 3-letter code, e.g. USD.");
    if (!emergencyOk) return setError("The emergency number must be 2–8 digits, e.g. 911, 999 or 112.");
    void run(async () => {
      const updated = await merchantApi.updateMe({
        timezone: draft.timezone.trim(),
        currency: draft.currency,
        emergency_number: emergencyDigits,
      });
      commit(regionFrom(updated));
      await refresh();
      onSaved();
    }, "Region settings saved.");
  };

  return (
    <SectionCard id="region" icon={Globe} title="Region & locale" description="The clock, currency and emergency number your agent uses.">
      <form className="grid gap-4" onSubmit={submit} noValidate>
        <div className="flex flex-col gap-3 rounded-md border border-border bg-surface p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-[13.5px] font-semibold text-muted-foreground">Region</p>
            <p className="mt-0.5 font-medium">
              {region?.label ?? merchant.region} <span className="text-muted-foreground">({merchant.region})</span>
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">Set by your admin — it decides the phone number format and the agent&apos;s English accent.</p>
          </div>
          {regionDefaults && !same(draft, regionDefaults) && (
            <Button type="button" variant="outline" size="sm" className="shrink-0" onClick={() => patch(regionDefaults)}>
              Use {region?.label} defaults
            </Button>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <FormRow
            id="timezone"
            label="Time zone"
            className="sm:col-span-3"
            hint={zoneOk ? `Local time there now: ${formatInZone(new Date().toISOString(), draft.timezone.trim())}. Bookings and the agent's "today" / "tomorrow" use this clock.` : "Type or pick an IANA time zone, e.g. Europe/London."}
          >
            <Input
              id="timezone"
              list="timezone-options"
              value={draft.timezone}
              maxLength={64}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={!zoneOk}
              aria-describedby="timezone-hint"
              className={cn(!zoneOk && "border-destructive")}
              onChange={(e) => patch({ timezone: e.target.value })}
            />
            <datalist id="timezone-options">
              {zoneOptions.map((zone) => (
                <option key={zone.value} value={zone.value}>
                  {zone.label}
                </option>
              ))}
            </datalist>
          </FormRow>
          <FormRow id="currency" label="Currency" hint={currencyOk ? `e.g. ${money(1234.5, draft.currency)}` : "3-letter code, e.g. USD, GBP, BDT"}>
            <Input
              id="currency"
              value={draft.currency}
              maxLength={3}
              autoComplete="off"
              spellCheck={false}
              className={cn("uppercase", !currencyOk && "border-destructive")}
              aria-invalid={!currencyOk}
              aria-describedby="currency-hint"
              onChange={(e) => patch({ currency: e.target.value.toUpperCase().replace(/[^A-Z]/g, "") })}
            />
          </FormRow>
          <FormRow
            id="emergency_number"
            label="Emergency number"
            className="sm:col-span-2"
            hint="Your agent tells callers to dial this in an emergency (gas smell, chest pain, fire)."
          >
            <Input
              id="emergency_number"
              inputMode="numeric"
              value={draft.emergency_number}
              maxLength={8}
              className={cn(!emergencyOk && "border-destructive")}
              aria-invalid={!emergencyOk}
              aria-describedby="emergency_number-hint"
              onChange={(e) => patch({ emergency_number: e.target.value.replace(/\D/g, "") })}
            />
          </FormRow>
        </div>

        <SaveBar dirty={dirty} saving={saving} error={error} onReset={() => { reset(); setError(null); }} label="Save region settings" />
      </form>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- knowledge base

function KnowledgeSection({ onSaved }: { onSaved: () => void }) {
  const { merchant, vertical, refresh } = useWorkspace();
  const source = useMemo(() => ({ knowledge: merchant.knowledge ?? "" }), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  useReportDirty("knowledge", dirty);
  const length = draft.knowledge.length;
  const catalogPlural = t(vertical.catalog_label_plural).toLowerCase();

  const insertExample = () => {
    const example = KNOWLEDGE_EXAMPLES[vertical.key] ?? KNOWLEDGE_EXAMPLES.ecommerce;
    if (draft.knowledge.trim() && !window.confirm("Replace your current text with the example? You can still discard it before saving.")) return;
    setDraft(() => ({ knowledge: example }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (length > KNOWLEDGE_MAX) {
      setError(`Keep it under ${KNOWLEDGE_MAX.toLocaleString("en-US")} characters.`);
      return;
    }
    void run(async () => {
      const updated = await merchantApi.updateMe({ knowledge: draft.knowledge.trim() });
      commit({ knowledge: updated.knowledge ?? "" });
      await refresh();
      onSaved();
    }, "Knowledge base saved.");
  };

  return (
    <SectionCard
      id="knowledge"
      icon={BookOpenText}
      title="Knowledge base"
      description="Facts your agent may answer questions from. It never makes up anything that isn't here or in your catalog."
    >
      <form className="grid gap-3" onSubmit={submit} noValidate>
        <div className="rounded-md border border-border bg-surface p-3 text-xs leading-relaxed text-muted-foreground">
          <p>
            Write short, plain lines: <span className="font-medium text-foreground">address and directions, opening hours, payment and cancellation policies, and frequent questions</span>. Put
            the details customers ask about most at the top.
            {catalogPlural ? ` Your ${catalogPlural} are managed separately — no need to repeat them here.` : ""}
          </p>
        </div>
        <FormRow
          id="knowledge"
          label="Business information"
          aside={
            <div className="flex items-center gap-3">
              <Counter value={length} max={KNOWLEDGE_MAX} warnAt={KNOWLEDGE_USED} />
            </div>
          }
          hint={
            length > KNOWLEDGE_USED
              ? `Getting long — every call reads all of this, so keep it to the facts callers actually ask about (limit ${KNOWLEDGE_MAX.toLocaleString("en-US")}).`
              : undefined
          }
        >
          <Textarea
            id="knowledge"
            rows={12}
            maxLength={KNOWLEDGE_MAX}
            value={draft.knowledge}
            placeholder={"Address: …\nOpening hours: …\nPolicies: …\nFAQ — …"}
            className="font-mono text-[13px] leading-relaxed"
            aria-describedby={length > KNOWLEDGE_USED ? "knowledge-hint" : undefined}
            onChange={(e) => setDraft(() => ({ knowledge: e.target.value }))}
          />
        </FormRow>
        <div>
          <Button type="button" variant="outline" size="sm" onClick={insertExample}>
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            Insert example
          </Button>
          <span className="ml-2 text-xs text-muted-foreground">Replace the [bracketed] parts with your own details.</span>
        </div>
        <SaveBar dirty={dirty} saving={saving} error={error} onReset={() => { reset(); setError(null); }} label="Save knowledge" />
      </form>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- business settings (vertical config)

type TimeWindow = { key: string; start: string; end: string };
type ConfigForm = { values: FormValues; windows: TimeWindow[] };

function windowsFrom(raw: unknown): TimeWindow[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .map((item) => ({ key: String(item.key ?? ""), start: String(item.start ?? "").slice(0, 5), end: String(item.end ?? "").slice(0, 5) }));
}

function configFrom(specs: FieldSpec[], config: Record<string, unknown>, hasWindows: boolean): ConfigForm {
  const values: FormValues = {};
  for (const spec of specs) {
    const value = config[spec.key];
    if (value !== undefined && value !== null) values[spec.key] = value;
  }
  return { values, windows: hasWindows ? windowsFrom(config.time_windows) : [] };
}

/** What the backend's `Vertical.config()` returns: the stored settings over the defaults. */
function mergedConfig(vertical: VerticalSpec, stored: Record<string, unknown>): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...vertical.config_defaults };
  for (const [key, value] of Object.entries(stored ?? {})) {
    if (value !== null && value !== undefined) merged[key] = value;
  }
  return merged;
}

function validateConfig(specs: FieldSpec[], form: ConfigForm, hasWindows: boolean): string | null {
  for (const spec of specs) {
    const value = form.values[spec.key];
    if ((spec.type === "number" || spec.type === "money") && typeof value === "number" && value < 0) {
      return `${t(spec.label)} can't be negative.`;
    }
  }
  if (!hasWindows) return null;
  if (!form.windows.length) return "Add at least one arrival window.";
  const keys = new Set<string>();
  for (const [index, window] of form.windows.entries()) {
    const label = `Arrival window ${index + 1}`;
    if (!/^[a-z_]{1,20}$/.test(window.key)) return `${label}: give it a short name in lowercase letters, e.g. morning.`;
    if (keys.has(window.key)) return `${label}: the name "${window.key}" is used twice.`;
    keys.add(window.key);
    if (!window.start || !window.end) return `${label}: set a start and an end time.`;
    if (window.end <= window.start) return `${label}: the end time must be after the start time.`;
  }
  return null;
}

function TimeWindowsEditor({ windows, onChange, teams }: { windows: TimeWindow[]; onChange: (next: TimeWindow[]) => void; teams: unknown }) {
  const update = (index: number, values: Partial<TimeWindow>) => onChange(windows.map((item, i) => (i === index ? { ...item, ...values } : item)));
  const add = () => {
    const last = windows[windows.length - 1];
    const start = last?.end || "09:00";
    const [hours, minutes] = start.split(":").map(Number);
    const endHours = Math.min(23, (hours || 0) + 3);
    const end = `${String(endHours).padStart(2, "0")}:${String(minutes || 0).padStart(2, "0")}`;
    onChange([...windows, { key: "", start, end: end > start ? end : "23:59" }]);
  };
  return (
    <fieldset className="space-y-3 sm:col-span-2">
      <legend className="text-[13.5px] font-semibold text-muted-foreground">Arrival windows</legend>
      <p className="text-xs leading-relaxed text-muted-foreground">
        The time slots your agent offers on working days{typeof teams === "number" && teams > 0 ? `; each takes up to ${teams} booking${teams === 1 ? "" : "s"} (your teams per window)` : ""}. Use names
        callers would say — e.g. morning, afternoon, evening.
      </p>
      {windows.length === 0 && <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">No arrival windows yet.</p>}
      <ul className="space-y-2">
        {windows.map((window, index) => (
          <li key={index} className="grid grid-cols-2 items-end gap-2 rounded-md border border-border p-2.5 sm:grid-cols-[1fr_8rem_8rem_auto] sm:border-0 sm:p-0">
            <div className="col-span-2 flex flex-col gap-1 sm:col-span-1">
              <label htmlFor={`window-key-${index}`} className={cn("text-xs font-medium text-muted-foreground", index > 0 && "sm:sr-only")}>
                Name
              </label>
              <Input
                id={`window-key-${index}`}
                value={window.key}
                maxLength={20}
                placeholder="morning"
                autoComplete="off"
                spellCheck={false}
                onChange={(e) => update(index, { key: e.target.value.toLowerCase().replace(/[^a-z_]/g, "") })}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor={`window-start-${index}`} className={cn("text-xs font-medium text-muted-foreground", index > 0 && "sm:sr-only")}>
                From
              </label>
              <Input id={`window-start-${index}`} type="time" value={window.start} onChange={(e) => update(index, { start: e.target.value })} />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor={`window-end-${index}`} className={cn("text-xs font-medium text-muted-foreground", index > 0 && "sm:sr-only")}>
                Until
              </label>
              <Input id={`window-end-${index}`} type="time" value={window.end} onChange={(e) => update(index, { end: e.target.value })} />
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="col-span-2 w-full text-muted-foreground hover:text-destructive sm:col-span-1 sm:w-10"
              aria-label={`Remove arrival window ${window.key || index + 1}`}
              onClick={() => onChange(windows.filter((_, i) => i !== index))}
            >
              <Trash2 className="h-4 w-4" aria-hidden />
              <span className="sm:hidden">Remove</span>
            </Button>
          </li>
        ))}
      </ul>
      <Button type="button" variant="outline" size="sm" onClick={add} disabled={windows.length >= MAX_TIME_WINDOWS}>
        <Plus className="h-3.5 w-3.5" aria-hidden />
        Add window
      </Button>
      {windows.length >= MAX_TIME_WINDOWS && <span className="ml-2 text-xs text-muted-foreground">Up to {MAX_TIME_WINDOWS} windows.</span>}
    </fieldset>
  );
}

function BusinessSettingsSection({ onSaved }: { onSaved: () => void }) {
  const { merchant, vertical, config, refresh } = useWorkspace();
  const specs = vertical.config_fields;
  const hasWindows = "time_windows" in (vertical.config_defaults ?? {});
  const source = useMemo(() => configFrom(specs, config, hasWindows), [specs, config, hasWindows]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  useReportDirty("business", dirty);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const problem = validateConfig(specs, draft, hasWindows);
    if (problem) {
      setError(problem);
      return;
    }
    // Lists: drop the blank line the editor keeps while typing.
    const values: FormValues = {};
    for (const [key, value] of Object.entries(draft.values)) {
      values[key] = Array.isArray(value) ? value.map((item) => (typeof item === "string" ? item.trim() : item)).filter((item) => item !== "") : value;
    }
    const payload: Record<string, unknown> = compactValues(values);
    // A cleared field goes back to the default: the API drops keys sent as null.
    for (const spec of specs) {
      if (!(spec.key in payload) && source.values[spec.key] !== undefined) payload[spec.key] = null;
    }
    if (hasWindows) payload.time_windows = draft.windows.map(({ key, start, end }) => ({ key, start, end }));
    void run(async () => {
      const updated = await merchantApi.updateMe({ vertical_config: payload });
      commit(configFrom(specs, mergedConfig(vertical, updated.vertical_config ?? {}), hasWindows));
      await refresh();
      onSaved();
    }, "Business settings saved.");
  };

  if (!specs.length && !hasWindows) return null;

  return (
    <SectionCard
      id="business"
      icon={SlidersHorizontal}
      title="Business settings"
      description={`How your agent books and handles ${t(vertical.record_label_plural, "records").toLowerCase()}. Leave a field empty to use the default.`}
    >
      <form className="grid gap-4" onSubmit={submit} noValidate>
        <SchemaFields
          specs={specs}
          values={draft.values}
          timezone={merchant.timezone}
          disabled={saving}
          onChange={(values) => setDraft((current) => ({ ...current, values }))}
        />
        {hasWindows && (
          <div className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
            <TimeWindowsEditor windows={draft.windows} teams={draft.values.teams} onChange={(windows) => setDraft((current) => ({ ...current, windows }))} />
          </div>
        )}
        <SaveBar dirty={dirty} saving={saving} error={error} onReset={() => { reset(); setError(null); }} label="Save business settings" />
      </form>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- how your agent works

function StepList({ title, subtitle, steps, icon: Icon }: { title: string; subtitle: string; steps: string[]; icon: LucideIcon }) {
  return (
    <section className="min-w-0 rounded-md border border-border p-4" aria-label={title}>
      <h4 className="flex items-center gap-2 text-sm font-semibold">
        <Icon className="h-4 w-4 text-primary" aria-hidden />
        {title}
      </h4>
      <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
      {steps.length ? (
        <ol className="mt-3 space-y-2.5">
          {steps.map((step, index) => (
            <li key={`${index}-${step}`} className="flex gap-3 text-sm leading-relaxed">
              <span
                aria-hidden
                className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-accent-foreground tabular-nums"
              >
                {index + 1}
              </span>
              <span className="min-w-0">{step}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">No steps to show.</p>
      )}
    </section>
  );
}

function FlowSection({ version }: { version: number }) {
  const { vertical } = useWorkspace();
  const [preview, setPreview] = useState<FlowPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    merchantApi
      .flowPreview()
      .then((next) => {
        if (cancelled) return;
        setPreview(next);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(formatApiError(err, "Could not load how your agent works."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [version, reload]);

  const inbound = preview?.sections?.inbound;
  const outbound = preview?.sections?.outbound;
  const recordLabel = t(vertical.record_label, "record").toLowerCase();

  return (
    <SectionCard
      id="flow"
      icon={Route}
      title="How your agent works"
      description="The steps your agent follows with the settings above. It updates when you save."
    >
      {error ? (
        <div className="space-y-3">
          <ApiError message={error} />
          <Button type="button" variant="outline" size="sm" onClick={() => setReload((n) => n + 1)}>
            Try again
          </Button>
        </div>
      ) : loading && !preview ? (
        <div className="grid gap-4 md:grid-cols-2" aria-busy="true" aria-label="Loading">
          {[0, 1].map((key) => (
            <div key={key} className="h-48 animate-pulse rounded-md bg-secondary" />
          ))}
        </div>
      ) : (
        <div className={cn("grid gap-4 transition-opacity", loading && "opacity-60", inbound && outbound && "md:grid-cols-2")}>
          {inbound && <StepList icon={Bot} title="When a customer contacts you" subtitle="Inbound calls and chats" steps={inbound} />}
          {outbound && (
            <StepList
              icon={Bot}
              title={`${t(vertical.outbound_label, "Outbound call")}`}
              subtitle={`When you call a customer about a ${recordLabel}`}
              steps={outbound}
            />
          )}
          {!inbound && !outbound && <p className="text-sm text-muted-foreground">No preview available.</p>}
        </div>
      )}
      <p className="mt-4 text-xs text-muted-foreground">
        Want to hear it?{" "}
        <Link href="/test" className="font-medium text-primary underline-offset-2 hover:underline">
          Test your agent
        </Link>{" "}
        with a browser call or a chat.
      </p>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- security

function SecuritySection() {
  const { saving, error, setError, run } = useSaver();
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const mismatch = form.confirm.length > 0 && form.next !== form.confirm;
  const filled = form.current && form.next && form.confirm;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!form.current) return setError("Enter your current password.");
    if (form.next.length < 6) return setError("The new password needs at least 6 characters.");
    if (form.next !== form.confirm) return setError("The new passwords don't match.");
    if (form.next === form.current) return setError("Choose a password different from the current one.");
    void run(
      async () => {
        await merchantApi.changePassword(form.current, form.next);
        setForm({ current: "", next: "", confirm: "" });
      },
      "Password changed.",
      "Could not change the password.",
    );
  };

  const type = show ? "text" : "password";
  return (
    <SectionCard id="security" icon={KeyRound} title="Security" description="Change the password you sign in with.">
      <form className="grid gap-4 sm:grid-cols-3" onSubmit={submit} noValidate>
        <FormRow id="current_password" label="Current password">
          <Input id="current_password" type={type} autoComplete="current-password" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} />
        </FormRow>
        <FormRow id="new_password" label="New password" hint="At least 6 characters.">
          <Input
            id="new_password"
            type={type}
            autoComplete="new-password"
            value={form.next}
            aria-describedby="new_password-hint"
            onChange={(e) => setForm({ ...form, next: e.target.value })}
          />
        </FormRow>
        <FormRow id="confirm_password" label="Confirm new password" hint={mismatch ? "Doesn't match the new password." : undefined}>
          <Input
            id="confirm_password"
            type={type}
            autoComplete="new-password"
            value={form.confirm}
            aria-invalid={mismatch}
            aria-describedby={mismatch ? "confirm_password-hint" : undefined}
            className={cn(mismatch && "border-destructive")}
            onChange={(e) => setForm({ ...form, confirm: e.target.value })}
          />
        </FormRow>
        <div className="space-y-3 sm:col-span-3">
          {error && (
            <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" variant="outline" disabled={saving || !filled}>
              {saving && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
              Change password
            </Button>
            <Button type="button" variant="ghost" size="sm" aria-pressed={show} onClick={() => setShow((value) => !value)}>
              {show ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
              {show ? "Hide passwords" : "Show passwords"}
            </Button>
          </div>
        </div>
      </form>
    </SectionCard>
  );
}

// ---------------------------------------------------------------- page

const SECTIONS: { id: string; label: string }[] = [
  { id: "profile", label: "Profile" },
  { id: "agent", label: "Voice & behaviour" },
  { id: "region", label: "Region" },
  { id: "knowledge", label: "Knowledge" },
  { id: "business", label: "Business settings" },
  { id: "flow", label: "How it works" },
  { id: "security", label: "Security" },
];

export default function SettingsPage() {
  const { merchant, vertical } = useWorkspace();
  const [dirty, setDirty] = useState<Record<string, boolean>>({});
  const [previewVersion, setPreviewVersion] = useState(0);

  const report = useCallback((id: string, value: boolean) => {
    setDirty((current) => (Boolean(current[id]) === value ? current : { ...current, [id]: value }));
  }, []);
  const bumpPreview = useCallback(() => setPreviewVersion((n) => n + 1), []);
  const anyDirty = Object.values(dirty).some(Boolean);

  // Warn before leaving the page with unsaved edits.
  useEffect(() => {
    if (!anyDirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [anyDirty]);

  const hasBusinessSettings = vertical.config_fields.length > 0 || "time_windows" in (vertical.config_defaults ?? {});
  const sections = SECTIONS.filter((section) => section.id !== "business" || hasBusinessSettings);

  return (
    <DirtyContext.Provider value={report}>
      <div className="mx-auto max-w-4xl space-y-6">
        <PageHeader title="Settings" subtitle={`Signed in as ${merchant.username} · ${t(vertical.label)}`} />

        <nav aria-label="Settings sections" className="-mt-2 flex flex-wrap gap-1.5">
          {sections.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-[13px] font-medium text-muted-foreground transition hover:border-tint-strong hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {section.label}
              {dirty[section.id] && (
                <>
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />
                  <span className="sr-only">(unsaved changes)</span>
                </>
              )}
            </a>
          ))}
        </nav>

        <ProfileSection onSaved={bumpPreview} />
        <AgentSection onSaved={bumpPreview} />
        <RegionSection onSaved={bumpPreview} />
        <KnowledgeSection onSaved={bumpPreview} />
        <BusinessSettingsSection onSaved={bumpPreview} />
        <FlowSection version={previewVersion} />
        <SecuritySection />
      </div>
    </DirtyContext.Provider>
  );
}
