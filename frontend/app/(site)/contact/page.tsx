import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { CalendarDays, Mail, MessageCircle } from "lucide-react";

import { ContactForm } from "@/components/site/contact-form";
import { Container, Eyebrow } from "@/components/site/section";
import { BRAND } from "@/lib/brand";
import { TRIAL } from "@/lib/site-content";

export const metadata: Metadata = {
  title: "Contact sales",
  description: `Start a ${TRIAL.days}-day free trial, book a 20-minute demo, or ask about Enterprise pricing for ${BRAND.name}'s AI voice and chat agents.`,
};

const NEXT_STEPS = [
  "We confirm your business type, region and the number you want to use.",
  "We set up your agent and show you the browser test console.",
  "You test it on your own questions, then go live when you're happy.",
];

function FormFallback() {
  return <div className="h-[640px] animate-pulse rounded-2xl border border-border bg-card" aria-hidden />;
}

export default function ContactPage() {
  return (
    <section className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-80 bg-[radial-gradient(60%_100%_at_50%_0%,hsl(var(--tint))_0%,transparent_75%)]"
      />
      <Container className="relative grid gap-10 py-14 sm:py-20 lg:grid-cols-[1fr_1.35fr] lg:gap-14">
        <div>
          <Eyebrow>Contact sales</Eyebrow>
          <h1 className="mt-3 text-balance text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            Let&apos;s get your agent answering.
          </h1>
          <p className="mt-4 text-pretty leading-relaxed text-muted-foreground">
            Start a free trial, see a live demo, or get help choosing a plan. Tell us a little about your business and
            we&apos;ll take it from there.
          </p>

          <div className="mt-8 space-y-4">
            <div className="flex gap-4 rounded-xl border border-border bg-card p-5">
              <CalendarDays className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
              <div>
                <h2 className="font-semibold text-foreground">Book a 20-minute demo</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  We&apos;ll call an agent set up for your kind of business, live, and walk through bookings, recordings
                  and outcomes in the portal.
                </p>
              </div>
            </div>
            <div className="flex gap-4 rounded-xl border border-border bg-card p-5">
              <Mail className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
              <div>
                <h2 className="font-semibold text-foreground">Email sales</h2>
                <a href={`mailto:${BRAND.salesEmail}`} className="mt-1 inline-block text-sm font-medium text-primary-dark hover:underline">
                  {BRAND.salesEmail}
                </a>
              </div>
            </div>
            <div className="flex gap-4 rounded-xl border border-border bg-card p-5">
              <MessageCircle className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
              <div>
                <h2 className="font-semibold text-foreground">Can&apos;t wait?</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  <Link href="/#demo" className="font-medium text-primary-dark hover:underline">
                    Chat with our demo clinic agent
                  </Link>{" "}
                  right now.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-8">
            <h2 className="text-sm font-semibold text-foreground">What happens next</h2>
            <ol className="mt-3 space-y-2.5 text-sm text-muted-foreground">
              {NEXT_STEPS.map((step, index) => (
                <li key={step} className="flex gap-3">
                  <span
                    className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-accent-foreground"
                    aria-hidden
                  >
                    {index + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
          </div>
        </div>

        <Suspense fallback={<FormFallback />}>
          <ContactForm />
        </Suspense>
      </Container>
    </section>
  );
}
