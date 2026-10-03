import Link from "next/link";
import { MessageSquare } from "lucide-react";

import { LiveDemo } from "@/components/site/live-demo";
import { Eyebrow, Section } from "@/components/site/section";

const PROMPTS = [
  "Can my daughter see the pediatrician on Friday?",
  "How much is a visit with the dermatologist?",
  "Do you accept Blue Cross Blue Shield?",
  "Where do I park, and what should I bring?",
];

/** "Try it now" band: copy + suggested prompts + the live chat bubble. */
export function DemoSection({ id = "demo" }: { id?: string }) {
  return (
    <Section id={id} tone="muted" labelledBy={`${id}-title`}>
      <div className="grid gap-10 lg:grid-cols-2 lg:items-center">
        <div>
          <Eyebrow>Live demo</Eyebrow>
          <h2 id={`${id}-title`} className="mt-3 text-balance text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Talk to a real agent, right now.
          </h2>
          <p className="mt-4 text-pretty leading-relaxed text-muted-foreground">
            This page runs our demo clinic, CityCare Family Clinic — a doctor list with days, hours and fees, plus a
            knowledge base. It&apos;s the same agent that answers the clinic&apos;s phone, typed instead of spoken. Ask it
            anything a patient would.
          </p>
          <div className="mt-6">
            <LiveDemo />
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            Prefer a walkthrough of the phone side?{" "}
            <Link href="/contact?plan=demo" className="font-semibold text-primary-dark hover:underline">
              Book a 20-minute demo
            </Link>
            .
          </p>
        </div>

        <div className="rounded-2xl border border-border bg-card p-6">
          <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <MessageSquare className="h-4 w-4 text-primary" aria-hidden />
            Things to try
          </p>
          <ul className="mt-4 space-y-2.5">
            {PROMPTS.map((prompt) => (
              <li
                key={prompt}
                className="rounded-xl rounded-br-md border border-border bg-secondary px-4 py-2.5 text-sm text-secondary-foreground"
              >
                “{prompt}”
              </li>
            ))}
          </ul>
          <p className="mt-5 text-xs leading-relaxed text-muted-foreground">
            The demo answers only from the demo clinic&apos;s data, reads bookings back before saving them, and never gives
            medical advice. Bookings you make here land in the demo account, not a real clinic.
          </p>
        </div>
      </div>
    </Section>
  );
}
