import type { Metadata } from "next";
import Link from "next/link";
import {
  BookOpen,
  CalendarCheck,
  KeyRound,
  ListChecks,
  Lock,
  Mic,
  PhoneForwarded,
  ShieldAlert,
  Siren,
  Webhook,
} from "lucide-react";

import { CtaBand } from "@/components/site/cta-band";
import { PageHero, Section, SectionHeading } from "@/components/site/section";
import { BRAND } from "@/lib/brand";

export const metadata: Metadata = {
  title: "Safety & privacy",
  description: `The guardrails every ${BRAND.name} agent follows on the phone and in chat, and how your call recordings, transcripts and records are handled.`,
};

const GUARDRAILS = [
  {
    icon: BookOpen,
    title: "Answers only from your data",
    body: "Replies come from your catalog and knowledge base. If something isn't covered, the agent says so and offers a message or a transfer.",
  },
  {
    icon: ListChecks,
    title: "Read-back before booking",
    body: "Names, times, prices and addresses are read back and confirmed before anything is saved.",
  },
  {
    icon: CalendarCheck,
    title: "Availability checked in code",
    body: "Open slots, capacity and double-booking checks run against your schedule at the moment of booking.",
  },
  {
    icon: Siren,
    title: "Emergencies routed out",
    body: "Clinic callers describing an emergency, or a gas leak, sparks or fire on a service line, are told to call your region's emergency number.",
  },
  {
    icon: ShieldAlert,
    title: "Things it won't say",
    body: "No medical advice. No promises on property prices or legal status. No fixed repair quotes beyond your price range.",
  },
  {
    icon: PhoneForwarded,
    title: "A person when it matters",
    body: "Callers who ask for a human, and conversations the agent shouldn't handle, are transferred or flagged for follow-up.",
  },
];

const DATA = [
  {
    icon: Lock,
    title: "Your account, your records",
    body: "Each business has its own account. Your catalog, knowledge base, bookings, recordings and transcripts are shown only to people signed in to it.",
  },
  {
    icon: Mic,
    title: "Recordings and transcripts",
    body: "Every call and chat is kept with its transcript and outcome, so your team can check what was said. Pro, or an add-on, keeps recordings for 12 months.",
  },
  {
    icon: KeyRound,
    title: "Telling callers about recording",
    body: "Recording rules differ by country and state. Set a custom greeting so callers hear that the call is answered by an AI assistant and recorded.",
  },
  {
    icon: Webhook,
    title: "You choose where data goes",
    body: "Webhooks send bookings and outcomes only to the endpoints you configure, and you can change or remove them at any time.",
  },
];

function Grid({ items }: { items: { icon: typeof Lock; title: string; body: string }[] }) {
  return (
    <ul className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <li key={item.title} className="rounded-xl border border-border bg-card p-6">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
              <Icon className="h-5 w-5" aria-hidden />
            </span>
            <h3 className="mt-4 font-semibold text-foreground">{item.title}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{item.body}</p>
          </li>
        );
      })}
    </ul>
  );
}

export default function SecurityPage() {
  return (
    <>
      <PageHero
        eyebrow="Safety & privacy"
        title="Safe to put on the phone with your customers"
        subtitle="An AI agent speaks for your business. These are the rules it follows on every call and chat, and how the records it creates are handled."
      />

      <Section labelledBy="guardrails-title">
        <SectionHeading
          id="guardrails-title"
          eyebrow="Guardrails"
          title="Rules the agent follows on every call"
          subtitle="Built into each business type's conversation flow — not left to a prompt you have to write."
        />
        <Grid items={GUARDRAILS} />
      </Section>

      <Section tone="muted" labelledBy="data-title">
        <SectionHeading id="data-title" eyebrow="Your data" title="Records that stay yours" />
        <Grid items={DATA} />
        <p className="mx-auto mt-10 max-w-2xl text-center text-sm text-muted-foreground">
          Have a security questionnaire, data-processing or compliance question for your industry?{" "}
          <Link href="/contact" className="font-semibold text-primary-dark hover:underline">
            Talk to us
          </Link>{" "}
          or email{" "}
          <a href={`mailto:${BRAND.salesEmail}`} className="font-semibold text-primary-dark hover:underline">
            {BRAND.salesEmail}
          </a>
          .
        </p>
      </Section>

      <CtaBand />
    </>
  );
}
