"use client";

/** Settings → Payments: platform links or the owner's own link template, and the accepted methods. */

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CreditCard } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { SectionCard, useDraft } from "@/components/portal/kit";
import { FormRow, SaveBar, Segmented, useReportDirty, useSaver } from "@/components/settings/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";
import { formatApiError, paymentsApi, type PaymentMethod, type PaymentSettings } from "@/services/api";

type Form = Pick<PaymentSettings, "provider" | "link_template" | "methods">;

const PLACEHOLDERS = ["amount", "currency", "ref"];
const METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "online", label: "Online (link by text)" },
  { value: "at_venue", label: "On arrival" },
];

function formFrom(settings: PaymentSettings): Form {
  return { provider: settings.provider === "link" ? "link" : "platform", link_template: settings.link_template ?? "", methods: settings.methods ?? [] };
}

/** The template filled with sample values, or null when it isn't a usable https link. */
function sampleLink(template: string): string | null {
  const filled = template.trim().replace(/\{amount\}/g, "49.00").replace(/\{currency\}/g, "USD").replace(/\{ref\}/g, "A1B2C3");
  return /^https:\/\/[^\s{}]+$/.test(filled) ? filled : null;
}

function PaymentsForm({ settings, onSaved }: { settings: PaymentSettings; onSaved: (next: PaymentSettings) => void }) {
  const { entitlements } = useWorkspace();
  const source = useMemo(() => formFrom(settings), [settings]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const { saving, error, setError, run } = useSaver();
  useReportDirty("payments", dirty);
  const blocked = entitlements.capabilities?.payments === false;
  const patch = (values: Partial<Form>) => setDraft((current) => ({ ...current, ...values }));
  const sample = sampleLink(draft.link_template);
  const testLinks = settings.platform_provider === "dummy";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (draft.provider === "link" && !sample) return setError("Use a full https:// link; {amount}, {currency} and {ref} are filled in.");
    if (!draft.methods.length) return setError("Keep at least one way to pay.");
    void run(async () => {
      const next = await paymentsApi.updateSettings({ provider: draft.provider, link_template: draft.link_template.trim(), methods: draft.methods });
      commit(formFrom(next));
      onSaved(next);
    }, "Payment settings saved.");
  };

  return (
    <form className="grid gap-5" onSubmit={submit} noValidate>
      {blocked && (
        <p className="rounded-md border border-border bg-surface px-3 py-2 text-xs text-muted-foreground">
          Payments on calls aren&apos;t in your plan.{" "}
          <Link href="/plan" className="font-medium text-primary-dark hover:underline dark:text-primary">
            Upgrade
          </Link>
        </p>
      )}
      <Segmented<Form["provider"]>
        name="payment_provider"
        label="Payment links"
        value={draft.provider}
        options={[
          { value: "platform", label: testLinks ? "Platform (test)" : "Platform" },
          { value: "link", label: "My own link" },
        ]}
        onChange={(provider) => patch({ provider })}
      />
      {draft.provider === "link" && (
        <FormRow
          id="link_template"
          label="Link"
          info="Your Stripe Payment Link, PayPal.me or similar. Callers get it by text; mark bookings paid yourself."
          hint={sample ? `e.g. ${sample}` : "https://… with {amount}, {currency}, {ref}"}
        >
          <Input
            id="link_template"
            value={draft.link_template}
            maxLength={500}
            spellCheck={false}
            placeholder="https://pay.example.com/your-shop?amount={amount}&ref={ref}"
            className={cn(draft.link_template && !sample && "border-destructive")}
            onChange={(e) => patch({ link_template: e.target.value })}
          />
          <div className="flex flex-wrap gap-1">
            {PLACEHOLDERS.map((name) => (
              <button
                key={name}
                type="button"
                className="rounded-full border border-border px-2 py-0.5 font-mono text-[11.5px] text-muted-foreground hover:bg-accent"
                onClick={() => patch({ link_template: `${draft.link_template}{${name}}` })}
              >
                {`{${name}}`}
              </button>
            ))}
          </div>
        </FormRow>
      )}
      <fieldset className="space-y-2 text-sm">
        <legend className="mb-1.5 text-[13.5px] font-semibold text-muted-foreground">Callers can pay</legend>
        {METHODS.map((method) => (
          <label key={method.value} className="flex items-center gap-2">
            <input
              type="checkbox"
              className="h-4 w-4 accent-primary"
              checked={draft.methods.includes(method.value)}
              onChange={(e) =>
                patch({ methods: e.target.checked ? [...draft.methods, method.value] : draft.methods.filter((value) => value !== method.value) })
              }
            />
            {method.label}
          </label>
        ))}
      </fieldset>
      <SaveBar dirty={dirty} saving={saving} error={error} onReset={() => { reset(); setError(null); }} />
    </form>
  );
}

export function PaymentsSection() {
  const [settings, setSettings] = useState<PaymentSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setSettings(await paymentsApi.settings());
      setError(null);
    } catch (err) {
      setError(formatApiError(err, "Could not load payment settings."));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  return (
    <SectionCard id="payments" icon={CreditCard} title="Payments" description="How callers pay when a step asks for it.">
      {settings ? (
        <PaymentsForm settings={settings} onSaved={setSettings} />
      ) : error ? (
        <div className="space-y-3">
          <ApiError message={error} />
          <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      ) : (
        <div className="h-32 animate-pulse rounded-md bg-secondary" aria-busy="true" aria-label="Loading" />
      )}
    </SectionCard>
  );
}
