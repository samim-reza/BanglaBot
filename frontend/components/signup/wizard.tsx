"use client";

/** Self-serve signup: business type → plan → add-ons (live total) → account → checkout. */

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, LoaderCircle } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { AddonPicker, IntervalToggle, TierCards, addonsFor } from "@/components/plan/pickers";
import { QuoteSummary, useQuote } from "@/components/plan/quote-summary";
import { SIGNUP_REFERENCE_KEY } from "@/components/public/pay-view";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatApiError, isApiRequestError, signupApi, type PlanSelection, type SignupCatalog } from "@/services/api";

import { StepAccount, accountProblem, type AccountForm } from "./step-account";
import { StepBusiness } from "./step-business";

const STEPS = ["Business", "Plan", "Add-ons", "Account"] as const;

const EMPTY_ACCOUNT: AccountForm = { business_name: "", owner_name: "", email: "", phone: "", password: "", region: "", username: "", website: "" };

function submitError(err: unknown): string {
  if (isApiRequestError(err) && err.status === 409) return err.detail || "An account with this email already exists — sign in instead.";
  if (isApiRequestError(err) && err.status === 429) return "Too many tries — wait a few minutes.";
  if (isApiRequestError(err) && err.status === 503) return "Online payment isn't available right now — try again soon or contact us.";
  return formatApiError(err, "Could not create your account.");
}

export function SignupWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [base, setBase] = useState<SignupCatalog | null>(null);
  const [offer, setOffer] = useState<SignupCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [vertical, setVertical] = useState("");
  const [selection, setSelection] = useState<PlanSelection>({ tier: "", interval: "month", addons: {} });
  const [account, setAccount] = useState<AccountForm>(EMPTY_ACCOUNT);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Prefill from links like /get-started?vertical=clinic&plan=growth&interval=year.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setVertical(params.get("vertical") ?? "");
    setSelection((s) => ({ ...s, tier: params.get("plan") ?? "", interval: params.get("interval") === "year" ? "year" : "month" }));
    signupApi
      .catalog()
      .then((next) => {
        setBase(next);
        setAccount((a) => ({ ...a, region: next.regions.find((r) => r.code === "INTL")?.code ?? next.regions[0]?.code ?? "" }));
      })
      .catch((err) => setError(formatApiError(err, "Could not load plans.")));
  }, []);

  // Tiers and add-ons sold for the chosen business type.
  useEffect(() => {
    if (!vertical) return;
    let live = true;
    signupApi
      .catalog(vertical)
      .then((next) => {
        if (!live) return;
        setOffer(next);
        const buyable = next.plans.filter((tier) => tier.visible !== false && tier.checkout);
        setSelection((s) => (buyable.some((tier) => tier.key === s.tier) ? s : { ...s, tier: (buyable.find((tier) => tier.highlight) ?? buyable[0])?.key ?? "" }));
      })
      .catch((err) => live && setError(formatApiError(err, "Could not load plans.")));
    return () => {
      live = false;
    };
  }, [vertical]);

  const tiers = useMemo(() => (offer?.plans ?? []).filter((tier) => tier.visible !== false).sort((a, b) => a.sort - b.sort), [offer]);
  const tier = tiers.find((item) => item.key === selection.tier);
  const addons = useMemo(() => addonsFor(offer?.addons ?? [], tier), [offer, tier]);
  const sent: PlanSelection = { ...selection, addons: Object.fromEntries(Object.entries(selection.addons).filter(([key, qty]) => qty > 0 && addons.some((a) => a.key === key))) };
  const quoteKey = vertical && tier ? JSON.stringify({ ...sent, vertical }) : "";
  const quote = useQuote(quoteKey, (body) => signupApi.quote(JSON.parse(body)), step > 0);

  const canNext = step === 0 ? Boolean(vertical && offer) : step === 1 ? Boolean(tier?.checkout) : true;

  const submit = async () => {
    const problem = accountProblem(account);
    if (problem) return setFormError(problem);
    setBusy(true);
    setFormError(null);
    try {
      const { username, ...rest } = account;
      const result = await signupApi.signup({ ...rest, ...(username.trim() ? { username: username.trim() } : {}), ...sent, vertical, email: account.email.trim() });
      try {
        window.sessionStorage.setItem(SIGNUP_REFERENCE_KEY, result.reference);
      } catch {
        // storage blocked: the pay page just won't offer "Continue"
      }
      if (result.checkout_url) window.location.assign(result.checkout_url);
      else router.push(`/signup/complete?reference=${encodeURIComponent(result.reference)}`);
    } catch (err) {
      setFormError(submitError(err));
      setBusy(false);
    }
  };

  if (error && !base) return <ApiError message={error} />;
  if (!base) return <div className="h-72 animate-pulse rounded-lg bg-secondary" aria-busy="true" aria-label="Loading" />;

  return (
    <div className="space-y-6">
      <ol className="flex flex-wrap gap-2 text-xs font-semibold" aria-label="Steps">
        {STEPS.map((label, index) => (
          <li key={label} aria-current={index === step ? "step" : undefined} className={cn("rounded-full px-3 py-1", index === step ? "bg-primary text-primary-foreground" : index < step ? "bg-accent text-accent-foreground" : "bg-secondary text-muted-foreground")}>
            {index + 1}. {label}
          </li>
        ))}
      </ol>

      <div className={cn("grid gap-6", step > 0 && "lg:grid-cols-[minmax(0,1fr)_18rem]")}>
        <div className="min-w-0 space-y-4">
          {step === 0 && (
            <StepBusiness
              verticals={base.verticals}
              value={vertical}
              onChange={(key) => {
                if (key !== vertical) setOffer(null);
                setVertical(key);
              }}
            />
          )}
          {step === 1 && (
            <>
              <IntervalToggle value={selection.interval} onChange={(interval) => setSelection((s) => ({ ...s, interval }))} />
              <TierCards tiers={tiers} value={selection.tier} interval={selection.interval} onChange={(key) => setSelection((s) => ({ ...s, tier: key }))} />
            </>
          )}
          {step === 2 && <AddonPicker addons={addons} value={selection.addons} onChange={(next) => setSelection((s) => ({ ...s, addons: next }))} />}
          {step === 3 && <StepAccount form={account} regions={base.regions} onChange={(patch) => setAccount((a) => ({ ...a, ...patch }))} />}
          {formError && step === 3 && <ApiError message={formError} />}
        </div>
        {step > 0 && <QuoteSummary quote={quote.data} loading={quote.loading} error={quote.error} />}
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-border pt-4">
        <Button type="button" variant="ghost" disabled={step === 0 || busy} onClick={() => setStep((s) => s - 1)}>
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back
        </Button>
        {step < STEPS.length - 1 ? (
          <Button type="button" disabled={!canNext} onClick={() => setStep((s) => s + 1)}>
            Next
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        ) : (
          <Button type="button" disabled={busy || !quote.data} onClick={() => void submit()}>
            {busy && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
            Continue to payment
          </Button>
        )}
      </div>
    </div>
  );
}
