import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

import { CallTranscript } from "@/components/site/call-transcript";
import { CtaBand } from "@/components/site/cta-band";
import { FeatureGrid } from "@/components/site/feature-grid";
import { PageHero, Section, SectionHeading } from "@/components/site/section";
import { Button } from "@/components/ui/button";
import { AGENTS, SALES_HREF, TRIAL_HREF } from "@/lib/site-content";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Solutions — AI agents for clinics, real estate, home services and e-commerce",
  description:
    "Four ready-made AI voice and chat agents: a clinic receptionist, a real estate leasing and sales assistant, a home services dispatch line and an e-commerce order confirmation caller.",
};

export default function SolutionsPage() {
  return (
    <>
      <PageHero
        eyebrow="Solutions"
        title="Four agents, each built for one kind of business"
        subtitle="Every agent answers calls and chats, books into your records and calls customers back. What it asks and books depends on your business."
      >
        <Button asChild className="h-11 px-6">
          <Link href={TRIAL_HREF}>Start free trial</Link>
        </Button>
        <Button asChild variant="outline" className="h-11 px-6">
          <Link href={SALES_HREF}>Talk to sales</Link>
        </Button>
      </PageHero>

      <nav aria-label="Jump to a solution" className="border-b border-border bg-card">
        <ul className="mx-auto flex max-w-6xl gap-2 overflow-x-auto px-4 py-3 sm:justify-center sm:px-6">
          {AGENTS.map((agent) => {
            const Icon = agent.icon;
            return (
              <li key={agent.key} className="shrink-0">
                <a
                  href={`#${agent.key}`}
                  className="inline-flex items-center gap-2 rounded-full border border-border px-3.5 py-1.5 text-sm font-medium text-foreground hover:border-tint-strong hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Icon className="h-4 w-4 text-primary" aria-hidden />
                  {agent.name}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>

      {AGENTS.map((agent, index) => {
        const Icon = agent.icon;
        return (
          <Section key={agent.key} id={agent.key} tone={index % 2 === 1 ? "muted" : "default"} labelledBy={`${agent.key}-title`}>
            <div className="grid items-center gap-12 lg:grid-cols-2">
              <div className={cn(index % 2 === 1 && "lg:order-2")}>
                <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                <p className="mt-4 text-sm font-semibold text-primary-dark">{agent.name}</p>
                <h2 id={`${agent.key}-title`} className="mt-1 text-balance text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
                  {agent.tagline}
                </h2>
                <p className="mt-4 text-pretty leading-relaxed text-muted-foreground">{agent.summary}</p>
                <ul className="mt-6 space-y-2.5 text-sm">
                  {agent.capabilities.map((item) => (
                    <li key={item} className="flex gap-2.5 text-foreground">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
                      {item}
                    </li>
                  ))}
                </ul>
                <div className="mt-8 flex flex-wrap gap-3">
                  <Button asChild>
                    <Link href={`/solutions/${agent.slug}`}>
                      Setup, outcomes &amp; safety
                      <ArrowRight className="h-4 w-4" aria-hidden />
                    </Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link href={`/contact?type=${agent.key}`}>Talk to sales</Link>
                  </Button>
                </div>
              </div>
              <CallTranscript conversation={agent.example} className={cn(index % 2 === 1 && "lg:order-1")} />
            </div>
          </Section>
        );
      })}

      <Section tone="card" labelledBy="platform-title">
        <SectionHeading
          id="platform-title"
          eyebrow="Under every agent"
          title="The same platform, whichever agent you run"
          subtitle="Phone and chat channels, recordings, campaigns, webhooks and regional settings, whichever agent you run."
        />
        <div className="mt-14">
          <FeatureGrid />
        </div>
      </Section>

      <CtaBand />
    </>
  );
}
