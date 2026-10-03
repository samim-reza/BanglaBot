import Link from "next/link";
import { ArrowRight, CalendarCheck, Clock, PhoneForwarded, PhoneOutgoing } from "lucide-react";

import { AgentCards } from "@/components/site/agent-cards";
import { CtaBand } from "@/components/site/cta-band";
import { DemoSection } from "@/components/site/demo-section";
import { FaqList } from "@/components/site/faq";
import { FeatureGrid } from "@/components/site/feature-grid";
import { HeroVisual } from "@/components/site/hero-visual";
import { PricingPlans } from "@/components/site/pricing-plans";
import { Container, Section, SectionHeading } from "@/components/site/section";
import { SiteShell } from "@/components/site/site-shell";
import { Steps } from "@/components/site/steps";
import { Button } from "@/components/ui/button";
import { BRAND } from "@/lib/brand";
import { ENTERPRISE, HOME_FAQS, SALES_HREF, TRIAL, TRIAL_HREF, usd } from "@/lib/site-content";

const PROMISES = [
  { icon: Clock, title: "Answers 24/7", body: "Calls and chats, nights and weekends included." },
  { icon: CalendarCheck, title: "Books into your records", body: "Appointments, viewings and visits — read back first." },
  { icon: PhoneOutgoing, title: "Calls customers back", body: "Reminders, confirmations and lead follow-ups." },
  { icon: PhoneForwarded, title: "Hands off to your team", body: "Live transfer the moment a person is needed." },
];

export default function HomePage() {
  return (
    <SiteShell>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-border">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(55%_65%_at_15%_0%,hsl(var(--tint))_0%,transparent_70%)]"
        />
        <Container className="relative grid items-center gap-14 py-14 sm:py-20 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:py-24">
          <div>
            <p className="inline-flex flex-wrap items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs font-semibold text-primary-dark">
              <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
              For clinics, real estate, home services &amp; e-commerce
            </p>
            <h1 className="mt-5 text-balance text-4xl font-bold leading-[1.1] tracking-tight text-foreground sm:text-5xl">
              The AI receptionist that answers, books and calls back.
            </h1>
            <p className="mt-5 max-w-xl text-pretty text-lg leading-relaxed text-muted-foreground">
              {BRAND.name} is a ready-made voice and chat agent for your business. It answers every call, books straight into
              your schedule and calls customers to confirm, using only your own data.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button asChild className="h-11 px-6 text-[15px]">
                <Link href={TRIAL_HREF}>
                  Start free trial
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
              </Button>
              <Button asChild variant="outline" className="h-11 px-6 text-[15px]">
                <Link href={SALES_HREF}>Talk to sales</Link>
              </Button>
            </div>
            <p className="mt-5 text-sm text-muted-foreground">
              <Link href="#demo" className="font-semibold text-primary-dark hover:underline">
                Try the live demo
              </Link>{" "}
              · {TRIAL.days}-day free trial with {TRIAL.minutes} call minutes
            </p>
          </div>
          <div className="pb-8 sm:px-6 lg:px-0">
            <HeroVisual />
          </div>
        </Container>
      </section>

      {/* Promises */}
      <section aria-label="What the agent does" className="border-b border-border bg-card">
        <Container>
          <ul className="grid gap-px bg-border sm:grid-cols-2 lg:grid-cols-4">
            {PROMISES.map((item) => {
              const Icon = item.icon;
              return (
                <li key={item.title} className="flex gap-3 bg-card px-2 py-6 sm:px-5">
                  <Icon className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
                  <div>
                    <p className="font-semibold text-foreground">{item.title}</p>
                    <p className="mt-0.5 text-sm text-muted-foreground">{item.body}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </Container>
      </section>

      {/* Agents */}
      <Section id="agents" labelledBy="agents-title">
        <SectionHeading
          id="agents-title"
          eyebrow="One platform, four agents"
          title="An agent that already knows your kind of business"
          subtitle="Pick your business type. The agent already knows what to ask, how your bookings work and what it must never say."
        />
        <div className="mt-12">
          <AgentCards />
        </div>
      </Section>

      {/* How it works */}
      <Section id="how-it-works" tone="muted" labelledBy="how-title">
        <SectionHeading
          id="how-title"
          eyebrow="How it works"
          title="Live on your phone line without writing a script"
          subtitle="No developers, no call-flow diagrams. You fill in what you offer; the agent handles the talking."
        />
        <div className="mt-12">
          <Steps />
        </div>
        <p className="mt-8 text-center">
          <Link href="/how-it-works" className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary-dark hover:underline">
            See what happens on a call
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </p>
      </Section>

      {/* Features */}
      <Section labelledBy="features-title">
        <SectionHeading
          id="features-title"
          eyebrow="Platform"
          title="Everything a great front desk does on the phone"
          subtitle="One agent for your phone line and chat channels, with your rules, in your region."
        />
        <div className="mt-14">
          <FeatureGrid />
        </div>
      </Section>

      <DemoSection />

      {/* Pricing teaser */}
      <Section id="pricing" labelledBy="pricing-title">
        <SectionHeading
          id="pricing-title"
          eyebrow="Pricing"
          title="A month of 24/7 answering for less than a week of receptionist wages"
          subtitle="Pick a plan, add what you need. For comparison, the U.S. median receptionist earns about $716 a week (BLS)."
        />
        <div className="mt-10">
          <PricingPlans showEnterprise={false} />
        </div>
        <div className="mt-8 flex flex-col items-center gap-2 text-center text-sm text-muted-foreground">
          <p>
            Larger volume or several locations? Enterprise starts at {usd(ENTERPRISE.priceFrom)} / month.{" "}
            <Link href="/contact?plan=enterprise" className="font-semibold text-primary-dark hover:underline">
              Talk to sales
            </Link>
          </p>
          <Link href="/pricing" className="inline-flex items-center gap-1.5 font-semibold text-primary-dark hover:underline">
            Compare plans, add-ons and the ROI calculator
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </Section>

      {/* FAQ */}
      <Section tone="muted" labelledBy="faq-title">
        <SectionHeading id="faq-title" eyebrow="FAQ" title="Questions we hear a lot" />
        <div className="mt-10">
          <FaqList items={HOME_FAQS} />
        </div>
      </Section>

      <CtaBand />
    </SiteShell>
  );
}
