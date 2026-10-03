"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Lock } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { formatDate } from "@/lib/format";
import { t } from "@/lib/vertical";
import {
  adminApi,
  formatApiError,
  isApiRequestError,
  type AdminMeta,
  type Language,
  type Merchant,
  type MerchantAdminUpdate,
  type VoicePersona,
} from "@/services/api";

import {
  FormField,
  FormSection,
  Switch,
  currencyError,
  emailError,
  emergencyError,
  fieldProps,
  focusFirstInvalid,
  phoneError,
  timezoneError,
} from "./form-bits";
import { LanguageField, PersonaField, PlanField, RegionFields } from "./merchant-fields";
import { DialogError, Overlay } from "./overlay";
import { verticalOf } from "./use-admin-meta";

type EditForm = {
  active: boolean;
  business_name: string;
  owner_name: string;
  email: string;
  phone: string;
  support_phone: string;
  plan: string;
  inbound_number: string;
  region: string;
  timezone: string;
  currency: string;
  emergency_number: string;
  language: Language;
  voice_persona: VoicePersona;
  custom_greeting: string;
  password: string;
};

type Errors = Partial<Record<keyof EditForm, string | null>>;

const GREETING_MAX = 300;

function formFrom(merchant: Merchant): EditForm {
  return {
    active: merchant.active !== false,
    business_name: merchant.business_name ?? "",
    owner_name: merchant.owner_name ?? "",
    email: merchant.email ?? "",
    phone: merchant.phone ?? "",
    support_phone: merchant.support_phone ?? "",
    plan: merchant.plan || "trial",
    inbound_number: merchant.inbound_number ?? "",
    region: merchant.region || "INTL",
    timezone: merchant.timezone ?? "",
    currency: merchant.currency ?? "",
    emergency_number: merchant.emergency_number ?? "",
    language: merchant.language === "bn" ? "bn" : "en",
    voice_persona: merchant.voice_persona === "male" ? "male" : "female",
    custom_greeting: merchant.custom_greeting ?? "",
    password: "",
  };
}

function validate(form: EditForm, initial: EditForm): Errors {
  const changed = (key: keyof EditForm) => form[key] !== initial[key];
  const errors: Errors = {};
  if (!form.business_name.trim()) errors.business_name = "Business name is required.";
  if (form.password && form.password.length < 6) errors.password = "At least 6 characters.";
  if (form.custom_greeting.length > GREETING_MAX) errors.custom_greeting = `At most ${GREETING_MAX} characters.`;
  errors.email = emailError(form.email);
  errors.phone = phoneError(form.phone);
  errors.support_phone = phoneError(form.support_phone);
  errors.inbound_number = phoneError(form.inbound_number);
  // Only check locale fields the admin touched, so a legacy value never blocks an unrelated save.
  if (changed("timezone")) errors.timezone = timezoneError(form.timezone);
  if (changed("currency")) errors.currency = currencyError(form.currency);
  if (changed("emergency_number")) errors.emergency_number = emergencyError(form.emergency_number);
  return errors;
}

/** Only the fields the admin changed (the business type is never sent — it is fixed). */
function diff(form: EditForm, initial: EditForm): MerchantAdminUpdate {
  const payload: MerchantAdminUpdate = {};
  const strings = [
    "business_name",
    "owner_name",
    "email",
    "phone",
    "support_phone",
    "plan",
    "inbound_number",
    "region",
    "timezone",
    "currency",
    "emergency_number",
    "custom_greeting",
  ] as const;
  for (const key of strings) {
    const next = key === "currency" ? form[key].trim().toUpperCase() : form[key].trim();
    if (next !== initial[key].trim()) payload[key] = next;
  }
  if (form.active !== initial.active) payload.active = form.active;
  if (form.language !== initial.language) payload.language = form.language;
  if (form.voice_persona !== initial.voice_persona) payload.voice_persona = form.voice_persona;
  if (form.password) payload.password = form.password;
  return payload;
}

/**
 * Side drawer to edit an account: status, profile, plan, inbound number, region
 * and locale, agent voice and greeting, and a password reset. The business
 * type is shown read-only — the API never changes it.
 */
export function MerchantEditDrawer({
  merchant,
  meta,
  onClose,
  onSaved,
}: {
  merchant: Merchant | null;
  meta: AdminMeta | null;
  onClose: () => void;
  onSaved: (merchant: Merchant) => void;
}) {
  const toast = useAppToast();
  const initial = useMemo(() => (merchant ? formFrom(merchant) : null), [merchant]);
  const [form, setForm] = useState<EditForm | null>(initial);
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    setForm(initial);
    setErrors({});
    setFormError(null);
    setTouched(false);
  }, [initial]);

  useEffect(() => {
    if (!touched || !form || !initial) return;
    const found = validate(form, initial);
    setErrors(found);
    if (!Object.values(found).some(Boolean)) setFormError(null);
  }, [form, initial, touched]);

  const open = Boolean(merchant && form && initial);
  const spec = verticalOf(meta, merchant?.vertical);
  const update = (patch: Partial<EditForm>) => setForm((current) => (current ? { ...current, ...patch } : current));
  const text = (key: keyof EditForm) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    update({ [key]: event.target.value } as Partial<EditForm>);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!merchant || !form || !initial) return;
    setTouched(true);
    const found = validate(form, initial);
    setErrors(found);
    if (Object.values(found).some(Boolean)) {
      setFormError("Please fix the highlighted fields.");
      focusFirstInvalid("admin-edit-account");
      return;
    }
    const payload = diff(form, initial);
    if (!Object.keys(payload).length) {
      toast.success("No changes to save.");
      onClose();
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      const saved = await adminApi.updateMerchant(merchant.id, payload);
      toast.success(`"${saved.business_name}" updated.`);
      onSaved(saved);
    } catch (err) {
      const message = formatApiError(err, "Could not update the account.");
      if (isApiRequestError(err) && err.status === 409 && message.toLowerCase().includes("inbound")) {
        setErrors((current) => ({ ...current, inbound_number: message }));
      }
      setFormError(message);
    } finally {
      setBusy(false);
    }
  };

  if (!merchant || !form || !initial) return null;

  return (
    <Overlay
      open={open}
      onClose={onClose}
      variant="drawer"
      busy={busy}
      title={`Edit ${merchant.business_name}`}
      description={
        <span className="font-mono text-xs">
          @{merchant.username}
          <span className="font-sans"> · created {formatDate(merchant.created_at)}</span>
        </span>
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form="admin-edit-account" disabled={busy}>
            {busy ? "Saving…" : "Save changes"}
          </Button>
        </>
      }
    >
      <form id="admin-edit-account" noValidate className="space-y-6" onSubmit={submit}>
        <Switch
          checked={form.active}
          onChange={(active) => update({ active })}
          label="Active"
          description="Inactive accounts can't sign in, and their agent stops answering calls and chats."
        />

        <div className="rounded-md border border-border bg-surface p-3 text-sm">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Lock className="h-3 w-3" aria-hidden="true" />
            Business type
          </div>
          <p className="mt-1 font-semibold">{spec ? t(spec.label, spec.key) : merchant.vertical}</p>
          {spec && <p className="mt-0.5 text-xs text-muted-foreground">{t(spec.description)}</p>}
          <p className="mt-1.5 text-xs text-muted-foreground">Fixed at creation. To change it, create a new account.</p>
        </div>

        <FormSection title="Profile">
          <FormField id="edit-business" label="Business name" required error={errors.business_name}>
            <Input {...fieldProps("edit-business", errors.business_name)} value={form.business_name} onChange={text("business_name")} maxLength={160} />
          </FormField>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="edit-owner" label="Owner name">
              <Input id="edit-owner" value={form.owner_name} onChange={text("owner_name")} maxLength={120} autoComplete="off" />
            </FormField>
            <FormField id="edit-email" label="Email" error={errors.email}>
              <Input {...fieldProps("edit-email", errors.email)} type="email" value={form.email} onChange={text("email")} maxLength={160} autoComplete="off" />
            </FormField>
            <FormField id="edit-phone" label="Phone" error={errors.phone}>
              <Input {...fieldProps("edit-phone", errors.phone)} value={form.phone} onChange={text("phone")} inputMode="tel" maxLength={32} autoComplete="off" />
            </FormField>
            <FormField id="edit-support" label="Support phone" error={errors.support_phone}>
              <Input {...fieldProps("edit-support", errors.support_phone)} value={form.support_phone} onChange={text("support_phone")} inputMode="tel" maxLength={32} autoComplete="off" />
            </FormField>
          </div>
        </FormSection>

        <FormSection title="Plan & phone number">
          <PlanField id="edit-plan" meta={meta} value={form.plan} onChange={(plan) => update({ plan })} />
          <FormField
            id="edit-inbound"
            label="Inbound number"
            hint="Calls to this Twilio number are answered by this account. Leave blank to detach it."
            error={errors.inbound_number}
          >
            <Input
              {...fieldProps("edit-inbound", errors.inbound_number, "hint")}
              value={form.inbound_number}
              onChange={text("inbound_number")}
              inputMode="tel"
              maxLength={32}
              autoComplete="off"
              placeholder="+14155550123"
            />
          </FormField>
        </FormSection>

        <FormSection title="Region & locale">
          <RegionFields
            idPrefix="edit"
            meta={meta}
            value={form}
            errors={errors}
            onChange={(patch) => update(patch)}
            regionHint="Sets the phone-number format and voice accent. Changing it refills the fields below."
          />
        </FormSection>

        <FormSection title="Agent">
          <div className="grid gap-3 sm:grid-cols-2">
            <LanguageField id="edit-language" meta={meta} value={form.language} onChange={(language) => update({ language })} />
            <PersonaField id="edit-persona" value={form.voice_persona} onChange={(voice_persona) => update({ voice_persona })} />
          </div>
          <FormField
            id="edit-greeting"
            label="Custom greeting"
            hint={`${form.custom_greeting.length}/${GREETING_MAX} · Leave blank to use the agent's standard opening line.`}
            error={errors.custom_greeting}
          >
            <Textarea
              {...fieldProps("edit-greeting", errors.custom_greeting, "hint")}
              value={form.custom_greeting}
              onChange={text("custom_greeting")}
              rows={3}
              maxLength={GREETING_MAX}
            />
          </FormField>
        </FormSection>

        <FormSection title="Security">
          <FormField id="edit-password" label="Reset password" hint="Leave blank to keep the current password." error={errors.password}>
            <Input
              {...fieldProps("edit-password", errors.password, "hint")}
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={text("password")}
              maxLength={200}
            />
          </FormField>
        </FormSection>

        <DialogError message={formError} />
      </form>
    </Overlay>
  );
}
