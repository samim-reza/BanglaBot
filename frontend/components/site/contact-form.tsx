"use client";

import { useId, useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { BUSINESS_TYPES, INTERESTS, MONTHLY_CALLS, TRIAL } from "@/lib/site-content";
import { formatApiError, publicApi, type SalesInquiryInput } from "@/services/api";

type Values = {
  name: string;
  email: string;
  phone: string;
  company: string;
  business_type: string;
  country: string;
  monthly_calls: string;
  interest: string;
  message: string;
  website: string;
};

function pick<T extends readonly { value: string }[]>(options: T, value: string | null): string {
  return value && options.some((option) => option.value === value) ? value : "";
}

function headingFor(interest: string): { title: string; subtitle: string } {
  if (interest === "trial") {
    return {
      title: `Start your ${TRIAL.days}-day free trial`,
      subtitle: `Tell us about your business and we'll set up your agent with ${TRIAL.minutes} call minutes to try it on real calls.`,
    };
  }
  const plan = INTERESTS.find((option) => option.value === interest);
  if (interest === "starter" || interest === "growth" || interest === "pro") {
    return {
      title: `Get started on ${plan?.label ?? "your plan"}`,
      subtitle: `We'll set up your account and agent. You can begin with the ${TRIAL.days}-day free trial.`,
    };
  }
  if (interest === "demo") {
    return {
      title: "Book a 20-minute demo",
      subtitle: "We'll call your agent together, live, and walk through bookings, recordings and outcomes.",
    };
  }
  if (interest === "enterprise") {
    return { title: "Talk to sales about Enterprise", subtitle: "Volume pricing, multiple locations, custom integrations and SSO." };
  }
  return { title: "Talk to sales", subtitle: "Questions, a live demo, or help choosing a plan — we'll get back to you." };
}

function FormField({
  id,
  label,
  required,
  hint,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-semibold text-foreground">
        {label}
        {required && (
          <span className="ml-0.5 text-destructive" aria-hidden>
            *
          </span>
        )}
      </label>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}

/** Talk-to-sales / trial request form. Pre-fills from ?plan= and ?type=
 * (re-mounts when they change, e.g. clicking "Start free trial" on this page). */
export function ContactForm() {
  const params = useSearchParams();
  const plan = params.get("plan");
  const type = params.get("type");
  return <ContactFormInner key={`${plan ?? ""}|${type ?? ""}`} plan={plan} type={type} />;
}

function ContactFormInner({ plan, type }: { plan: string | null; type: string | null }) {
  const id = useId();
  const [values, setValues] = useState<Values>(() => ({
    name: "",
    email: "",
    phone: "",
    company: "",
    business_type: pick(BUSINESS_TYPES, type),
    country: "",
    monthly_calls: "",
    interest: pick(INTERESTS, plan),
    message: "",
    website: "",
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const set = (key: keyof Values) => (event: { target: { value: string } }) =>
    setValues((current) => ({ ...current, [key]: event.target.value }));

  const heading = headingFor(values.interest);
  const missingContact = !values.email.trim() && !values.phone.trim();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!values.name.trim()) {
      setInvalid("Please tell us your name.");
      return;
    }
    if (missingContact) {
      setInvalid("Please leave an email or a phone number so we can reach you.");
      return;
    }
    if (values.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) {
      setInvalid("Please check your email address.");
      return;
    }
    setInvalid(null);
    const interest = INTERESTS.find((option) => option.value === values.interest);
    const message = [interest ? `Interested in: ${interest.label}` : "", values.message.trim()].filter(Boolean).join("\n\n");
    const payload: SalesInquiryInput = {
      name: values.name.trim(),
      email: values.email.trim(),
      phone: values.phone.trim(),
      company: values.company.trim(),
      business_type: values.business_type,
      country: values.country.trim(),
      monthly_calls: values.monthly_calls,
      message,
      website: values.website,
    };
    setBusy(true);
    setError(null);
    try {
      await publicApi.contact(payload);
      setDone(true);
    } catch (err) {
      setError(formatApiError(err, "We couldn't send your message. Please try again or email us."));
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div className="rounded-2xl border border-border bg-card p-8 text-center" role="status">
        <CircleCheck className="mx-auto h-10 w-10 text-primary" aria-hidden />
        <h2 className="mt-4 text-xl font-semibold text-foreground">Thanks, {values.name.trim().split(" ")[0]} — we&apos;ve got it.</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          Someone from our team will reach out{values.email.trim() ? ` at ${values.email.trim()}` : " by phone"} shortly.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Button asChild>
            <Link href="/how-it-works">How it works</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/solutions">Explore solutions</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="relative rounded-2xl border border-border bg-card p-6 sm:p-8" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="text-xl font-semibold text-foreground">
        {heading.title}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{heading.subtitle}</p>

      <div className="mt-6 grid gap-5 sm:grid-cols-2">
        <FormField id={`${id}-name`} label="Your name" required>
          <Input
            id={`${id}-name`}
            name="name"
            autoComplete="name"
            required
            aria-required="true"
            aria-invalid={invalid !== null && !values.name.trim() ? true : undefined}
            maxLength={120}
            value={values.name}
            onChange={set("name")}
          />
        </FormField>
        <FormField id={`${id}-company`} label="Business name">
          <Input
            id={`${id}-company`}
            name="company"
            autoComplete="organization"
            maxLength={160}
            value={values.company}
            onChange={set("company")}
          />
        </FormField>
        <FormField id={`${id}-email`} label="Work email" hint="Email or phone — at least one.">
          <Input
            id={`${id}-email`}
            name="email"
            type="email"
            autoComplete="email"
            maxLength={160}
            aria-describedby={`${id}-email-hint`}
            aria-invalid={invalid !== null && missingContact ? true : undefined}
            value={values.email}
            onChange={set("email")}
          />
        </FormField>
        <FormField id={`${id}-phone`} label="Phone">
          <Input
            id={`${id}-phone`}
            name="phone"
            type="tel"
            autoComplete="tel"
            maxLength={40}
            aria-invalid={invalid !== null && missingContact ? true : undefined}
            value={values.phone}
            onChange={set("phone")}
          />
        </FormField>
        <FormField id={`${id}-type`} label="Business type">
          <Select id={`${id}-type`} name="business_type" value={values.business_type} onChange={set("business_type")}>
            <option value="">Choose one…</option>
            {BUSINESS_TYPES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id={`${id}-country`} label="Country">
          <Input
            id={`${id}-country`}
            name="country"
            autoComplete="country-name"
            maxLength={60}
            value={values.country}
            onChange={set("country")}
          />
        </FormField>
        <FormField id={`${id}-calls`} label="Calls per month">
          <Select id={`${id}-calls`} name="monthly_calls" value={values.monthly_calls} onChange={set("monthly_calls")}>
            <option value="">Choose a range…</option>
            {MONTHLY_CALLS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id={`${id}-interest`} label="Interested in">
          <Select id={`${id}-interest`} name="interest" value={values.interest} onChange={set("interest")}>
            <option value="">Not sure yet</option>
            {INTERESTS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </FormField>
        <div className="sm:col-span-2">
          <FormField id={`${id}-message`} label="Anything we should know?">
            <Textarea
              id={`${id}-message`}
              name="message"
              rows={4}
              maxLength={3800}
              placeholder="Opening hours, how many doctors or crews, the software you use today…"
              value={values.message}
              onChange={set("message")}
            />
          </FormField>
        </div>
      </div>

      {/* Honeypot: hidden from people and assistive tech; bots tend to fill it. */}
      <div aria-hidden="true" className="absolute -left-[10000px] h-px w-px overflow-hidden">
        <label htmlFor={`${id}-website`}>Website</label>
        <input
          id={`${id}-website`}
          name="website"
          type="text"
          tabIndex={-1}
          autoComplete="off"
          value={values.website}
          onChange={set("website")}
        />
      </div>

      <div className="mt-6 space-y-4">
        <div aria-live="assertive">
          {invalid ? (
            <p className="flex items-start gap-2 text-sm font-medium text-destructive">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              {invalid}
            </p>
          ) : (
            <ApiError message={error} />
          )}
        </div>
        <Button type="submit" disabled={busy} className="h-11 w-full sm:w-auto sm:px-8">
          {busy && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
          {busy ? "Sending…" : values.interest === "trial" ? "Request my free trial" : "Send"}
        </Button>
        <p className="text-xs text-muted-foreground">
          We use your details only to reply to this request.
        </p>
      </div>
    </form>
  );
}
