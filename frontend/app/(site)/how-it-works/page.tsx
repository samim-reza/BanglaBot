import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowDown,
  ArrowRight,
  AudioLines,
  BookOpen,
  CalendarClock,
  Check,
  FileText,
  Mic,
  PhoneCall,
  PhoneForwarded,
  Volume2,
  Webhook,
  Zap,
} from "lucide-react";

import { CtaBand } from "@/components/site/cta-band";
import { PageHero, Section, SectionHeading } from "@/components/site/section";
import { Steps } from "@/components/site/steps";
import { Button } from "@/components/ui/button";
import { SALES_HREF, TRIAL_HREF } from "@/lib/site-content";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "Pick your business type, add your doctors, listings or services, test the agent in your browser, then go live. Here's what happens on every call.",
};

const PIPELINE = [
  { icon: Mic, title: "Caller speaks", body: "On your number, or typed in a chat." },
  { icon: AudioLines, title: "Speech becomes text", body: "The caller's words are transcribed in the account's language." },
  { icon: BookOpen, title: "One AI turn, your data", body: "The next step is decided against your catalog, knowledge and schedule." },
  { icon: Volume2, title: "Reply is spoken", body: "Scripted lines play from a voice cache; the rest is synthesised." },
  { icon: FileText, title: "Outcome is written", body: "Booking, lead or follow-up saved, with recording and transcript." },
];

const AFTER_CALL = [
  { icon: AudioLines, title: "Recording and transcript", body: "Listen back or skim the text for every call and chat." },
  { icon: FileText, title: "A clear outcome", body: "Booked, rescheduled, cancelled, lead, emergency or follow-up." },
  { icon: Webhook, title: "Webhooks", body: "Push each booking and outcome into your own systems." },
  { icon: PhoneForwarded, title: "Live transfer", body: "When a person is needed, the call goes to your team." },
];

const OUTBOUND = [
  "One call from a record, when you click Call",
  "Every eligible record at once with Call all",
  "Automatically every day at a time you choose",
  "Unanswered calls retried, each result written back",
];

export default function HowItWorksPage() {
  return (
    <>
      <PageHero
        eyebrow="How it works"
        title="From sign-up to answering calls"
        subtitle="You describe your business; the agent already knows how the conversation should go. Four steps, no call-flow diagrams."
      >
        <Button asChild className="h-11 px-6">
          <Link href={TRIAL_HREF}>Start free trial</Link>
        </Button>
        <Button asChild variant="outline" className="h-11 px-6">
          <Link href={SALES_HREF}>Talk to sales</Link>
        </Button>
      </PageHero>

      <Section labelledBy="setup-title">
        <SectionHeading id="setup-title" eyebrow="Setup" title="Four steps to a live agent" />
        <div className="mx-auto mt-12 max-w-4xl">
          <Steps detailed />
        </div>
      </Section>

      <Section tone="muted" labelledBy="call-title">
        <SectionHeading
          id="call-title"
          eyebrow="On every call"
          title="What happens between “hello” and “you're booked”"
          subtitle="Each turn takes a single AI round-trip. Availability, prices and lead scores come from your data and fixed rules — not from the model's memory."
        />
        <ol className="mt-12 grid gap-3 lg:grid-cols-5">
          {PIPELINE.map((stage, index) => {
            const Icon = stage.icon;
            return (
              <li key={stage.title} className="relative">
                <div className="h-full rounded-xl border border-border bg-card p-5">
                  <div className="flex items-center gap-3">
                    <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                      <Icon className="h-4 w-4" aria-hidden />
                    </span>
                    <span className="text-xs font-semibold text-muted-foreground">Step {index + 1}</span>
                  </div>
                  <h3 className="mt-3 font-semibold text-foreground">{stage.title}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{stage.body}</p>
                </div>
                {index < PIPELINE.length - 1 && (
                  <>
                    <ArrowDown className="mx-auto my-1 h-4 w-4 text-tint-strong lg:hidden" aria-hidden />
                    <ArrowRight
                      className="absolute -right-3 top-1/2 z-10 hidden h-4 w-4 -translate-y-1/2 text-primary lg:block"
                      aria-hidden
                    />
                  </>
                )}
              </li>
            );
          })}
        </ol>
        <div className="mx-auto mt-10 flex max-w-3xl gap-4 rounded-xl border border-border bg-card p-5">
          <Zap className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
          <p className="text-sm leading-relaxed text-muted-foreground">
            <span className="font-semibold text-foreground">Why it feels quick: </span>
            greetings, read-backs and confirmations are spoken from a voice cache instead of being generated every time,
            and each turn makes one AI round-trip — so callers hear an answer, not silence.
          </p>
        </div>
      </Section>

      <Section labelledBy="test-title">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <SectionHeading
              id="test-title"
              align="left"
              eyebrow="Before you go live"
              title="Try it like a customer would"
              subtitle="Call your agent's number from your own phone and preview the website chat. Ask the awkward questions, then read the transcript."
            />
            <ul className="mt-6 space-y-2.5 text-sm">
              {[
                "Call your number from any phone",
                "Preview the website chat before you embed it",
                "Every conversation transcribed with its outcome",
              ].map((item) => (
                <li key={item} className="flex gap-2.5 text-foreground">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-2xl border border-border bg-card p-6">
            <div className="flex items-center gap-3">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <PhoneCall className="h-5 w-5" aria-hidden />
              </span>
              <div>
                <p className="font-semibold text-foreground">Before going live</p>
                <p className="text-xs text-muted-foreground">Try your agent before customers do</p>
              </div>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg border border-border bg-surface p-4">
                <p className="font-semibold text-foreground">Call your number</p>
                <p className="mt-1 text-xs text-muted-foreground">From any phone</p>
              </div>
              <div className="rounded-lg border border-border bg-surface p-4">
                <p className="font-semibold text-foreground">Chat preview</p>
                <p className="mt-1 text-xs text-muted-foreground">On the Channels page</p>
              </div>
            </div>
            <p className="mt-4 rounded-lg bg-accent px-4 py-3 text-xs text-accent-foreground">
              Every call and chat lands in Calls &amp; chats with its transcript and outcome.
            </p>
          </div>
        </div>
      </Section>

      <Section tone="muted" labelledBy="after-title">
        <SectionHeading id="after-title" eyebrow="After every call" title="Nothing lost in a voicemail box" />
        <ul className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {AFTER_CALL.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.title} className="rounded-xl border border-border bg-card p-5">
                <Icon className="h-5 w-5 text-primary" aria-hidden />
                <h3 className="mt-3 font-semibold text-foreground">{item.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{item.body}</p>
              </li>
            );
          })}
        </ul>
      </Section>

      <Section labelledBy="outbound-title">
        <div className="mx-auto grid max-w-5xl items-center gap-10 lg:grid-cols-2">
          <SectionHeading
            id="outbound-title"
            align="left"
            eyebrow="Outbound"
            title="Calls customers back, on your schedule"
            subtitle="Appointment reminders, visit confirmations, lead follow-ups and cash-on-delivery order checks — the agent places the calls and writes the results back."
          />
          <ul className="space-y-3 rounded-2xl border border-border bg-card p-6">
            {OUTBOUND.map((item) => (
              <li key={item} className="flex gap-3 text-sm text-foreground">
                <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </Section>

      <CtaBand />
    </>
  );
}
