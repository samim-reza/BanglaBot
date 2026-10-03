"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Eye, EyeOff, Plus } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  adminApi,
  formatApiError,
  isApiRequestError,
  type AdminMeta,
  type Language,
  type Merchant,
  type MerchantCreateInput,
  type VerticalKey,
  type VoicePersona,
} from "@/services/api";

import {
  FormField,
  FormSection,
  USERNAME_RE,
  currencyError,
  emailError,
  emergencyError,
  fieldProps,
  focusFirstInvalid,
  phoneError,
  timezoneError,
} from "./form-bits";
import { LanguageField, PersonaField, PlanField, RegionFields, VerticalPicker, regionPreset, type LocaleValues } from "./merchant-fields";
import { DialogError, Overlay } from "./overlay";

type CreateForm = LocaleValues & {
  business_name: string;
  username: string;
  password: string;
  vertical: VerticalKey | "";
  language: Language;
  plan: string;
  voice_persona: VoicePersona;
  owner_name: string;
  email: string;
  phone: string;
  support_phone: string;
  inbound_number: string;
};

type Errors = Partial<Record<keyof CreateForm, string | null>>;

function blankForm(meta: AdminMeta | null): CreateForm {
  const region = meta?.regions.some((item) => item.code === "INTL") ? "INTL" : meta?.regions[0]?.code ?? "INTL";
  const preset = regionPreset(meta, region) ?? { timezone: "UTC", currency: "USD", emergency_number: "112" };
  return {
    business_name: "",
    username: "",
    password: "",
    vertical: "",
    language: "en",
    region,
    ...preset,
    plan: meta?.plans.some((plan) => plan.key === "trial") ? "trial" : meta?.plans[0]?.key ?? "trial",
    voice_persona: "female",
    owner_name: "",
    email: "",
    phone: "",
    support_phone: "",
    inbound_number: "",
  };
}

function validate(form: CreateForm): Errors {
  const errors: Errors = {};
  const username = form.username.trim();
  if (!form.business_name.trim()) errors.business_name = "Business name is required.";
  if (!username) errors.username = "Username is required.";
  else if (username.length < 3) errors.username = "At least 3 characters.";
  else if (!USERNAME_RE.test(username)) errors.username = "Letters, numbers, dot, dash and underscore only.";
  if (form.password.length < 6) errors.password = "At least 6 characters.";
  if (!form.vertical) errors.vertical = "Choose the business type.";
  errors.email = emailError(form.email);
  errors.phone = phoneError(form.phone);
  errors.support_phone = phoneError(form.support_phone);
  errors.inbound_number = phoneError(form.inbound_number);
  errors.timezone = timezoneError(form.timezone);
  errors.currency = currencyError(form.currency);
  errors.emergency_number = emergencyError(form.emergency_number);
  return errors;
}

const hasErrors = (errors: Errors) => Object.values(errors).some(Boolean);

/** "Create account" dialog: credentials, the fixed business engine, region preset, plan and contact details. */
export function MerchantCreateDialog({
  open,
  meta,
  onClose,
  onCreated,
}: {
  open: boolean;
  meta: AdminMeta | null;
  onClose: () => void;
  onCreated: (merchant: Merchant) => void;
}) {
  const toast = useAppToast();
  const [form, setForm] = useState<CreateForm>(() => blankForm(meta));
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState(false);

  const metaRef = useRef(meta);
  useEffect(() => {
    metaRef.current = meta;
  }, [meta]);

  // A fresh form each time the dialog opens. (Without meta yet, the blank form
  // already carries the International preset, so nothing is lost meanwhile.)
  useEffect(() => {
    if (open) {
      setForm(blankForm(metaRef.current));
      setErrors({});
      setFormError(null);
      setShowPassword(false);
      setTouched(false);
    }
  }, [open]);

  // Once the admin has tried to submit, keep the messages in step with edits.
  useEffect(() => {
    if (!touched) return;
    const found = validate(form);
    setErrors(found);
    if (!hasErrors(found)) setFormError(null);
  }, [form, touched]);

  const update = (patch: Partial<CreateForm>) => setForm((current) => ({ ...current, ...patch }));

  const text = (key: keyof CreateForm) => (event: React.ChangeEvent<HTMLInputElement>) => update({ [key]: event.target.value } as Partial<CreateForm>);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    const found = validate(form);
    setErrors(found);
    if (hasErrors(found) || !form.vertical) {
      setFormError("Please fix the highlighted fields.");
      focusFirstInvalid("admin-create-account");
      return;
    }
    setBusy(true);
    setFormError(null);
    const payload: MerchantCreateInput = {
      business_name: form.business_name.trim(),
      username: form.username.trim(),
      password: form.password,
      vertical: form.vertical,
      region: form.region,
      language: form.language,
      plan: form.plan,
      voice_persona: form.voice_persona,
      owner_name: form.owner_name.trim(),
      email: form.email.trim(),
      phone: form.phone.trim(),
      support_phone: form.support_phone.trim(),
      inbound_number: form.inbound_number.trim(),
      timezone: form.timezone.trim(),
      currency: form.currency.trim().toUpperCase(),
      emergency_number: form.emergency_number.trim(),
    };
    try {
      const merchant = await adminApi.createMerchant(payload);
      toast.success(`Account "${merchant.business_name}" created.`);
      onCreated(merchant);
    } catch (err) {
      const message = formatApiError(err, "Could not create the account.");
      if (isApiRequestError(err) && err.status === 409) {
        const lower = message.toLowerCase();
        if (lower.includes("inbound")) setErrors((current) => ({ ...current, inbound_number: message }));
        else if (lower.includes("username")) setErrors((current) => ({ ...current, username: message }));
      }
      setFormError(message);
    } finally {
      setBusy(false);
    }
  };

  const busyLabel = busy ? "Creating…" : "Create account";

  return (
    <Overlay
      open={open}
      onClose={onClose}
      busy={busy}
      size="lg"
      title="Create account"
      description="The owner signs in to their portal with this username and password."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form="admin-create-account" disabled={busy || !meta}>
            <Plus className="h-4 w-4" />
            {busyLabel}
          </Button>
        </>
      }
    >
      <form id="admin-create-account" noValidate className="space-y-6" onSubmit={submit}>
        <FormSection title="Account">
          <FormField id="create-business" label="Business name" required error={errors.business_name}>
            <Input {...fieldProps("create-business", errors.business_name)} value={form.business_name} onChange={text("business_name")} maxLength={160} autoComplete="organization" />
          </FormField>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField
              id="create-username"
              label="Username"
              required
              hint="3+ characters: letters, numbers, . _ -"
              error={errors.username}
            >
              <Input
                {...fieldProps("create-username", errors.username, "hint")}
                value={form.username}
                onChange={text("username")}
                maxLength={80}
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
              />
            </FormField>
            <FormField id="create-password" label="Password" required hint="At least 6 characters." error={errors.password}>
              <div className="relative">
                <Input
                  {...fieldProps("create-password", errors.password, "hint")}
                  type={showPassword ? "text" : "password"}
                  value={form.password}
                  onChange={text("password")}
                  maxLength={200}
                  autoComplete="new-password"
                  className="pr-10"
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-md text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </FormField>
          </div>
        </FormSection>

        <VerticalPicker
          name="create-vertical"
          verticals={meta?.verticals ?? []}
          value={form.vertical}
          onChange={(vertical) => update({ vertical })}
          error={errors.vertical}
        />

        <FormSection title="Agent & plan">
          <div className="grid gap-3 sm:grid-cols-3">
            <LanguageField id="create-language" meta={meta} value={form.language} onChange={(language) => update({ language })} />
            <PersonaField id="create-persona" value={form.voice_persona} onChange={(voice_persona) => update({ voice_persona })} />
            <PlanField id="create-plan" meta={meta} value={form.plan} onChange={(plan) => update({ plan })} />
          </div>
          <FormField
            id="create-inbound"
            label="Inbound number"
            hint="The Telnyx number whose calls this account answers, e.g. +14155550123. Each number can belong to one account only."
            error={errors.inbound_number}
          >
            <Input
              {...fieldProps("create-inbound", errors.inbound_number, "hint")}
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
            idPrefix="create"
            meta={meta}
            value={form}
            errors={errors}
            onChange={(patch) => update(patch)}
          />
        </FormSection>

        <FormSection title="Owner & contact">
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="create-owner" label="Owner name">
              <Input id="create-owner" value={form.owner_name} onChange={text("owner_name")} maxLength={120} autoComplete="off" />
            </FormField>
            <FormField id="create-email" label="Email" error={errors.email}>
              <Input {...fieldProps("create-email", errors.email)} type="email" value={form.email} onChange={text("email")} maxLength={160} autoComplete="off" />
            </FormField>
            <FormField id="create-phone" label="Phone" error={errors.phone}>
              <Input {...fieldProps("create-phone", errors.phone)} value={form.phone} onChange={text("phone")} inputMode="tel" maxLength={32} autoComplete="off" />
            </FormField>
            <FormField
              id="create-support"
              label="Support phone"
              hint="Where the agent sends callers who need a person."
              error={errors.support_phone}
            >
              <Input
                {...fieldProps("create-support", errors.support_phone, "hint")}
                value={form.support_phone}
                onChange={text("support_phone")}
                inputMode="tel"
                maxLength={32}
                autoComplete="off"
              />
            </FormField>
          </div>
        </FormSection>

        <DialogError message={formError} />
      </form>
    </Overlay>
  );
}
