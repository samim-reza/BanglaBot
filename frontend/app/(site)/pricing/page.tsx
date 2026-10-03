import type { Metadata } from "next";

import { AddonList } from "@/components/site/addons";
import { Comparison } from "@/components/site/comparison";
import { CtaBand } from "@/components/site/cta-band";
import { FaqList } from "@/components/site/faq";
import { PricingPlans } from "@/components/site/pricing-plans";
import { RoiCalculator } from "@/components/site/roi-calculator";
import { PageHero, Section, SectionHeading } from "@/components/site/section";
import { PRICING_FAQS, TRIAL } from "@/lib/site-content";

export const metadata: Metadata = {
  title: "Pricing",
  description: `Plans from $49 a month with call minutes and website chats included. ${TRIAL.days}-day free trial with ${TRIAL.minutes} minutes, annual billing with 2 months free, and an ROI calculator.`,
};

export default function PricingPage() {
  return (
    <>
      <PageHero
        eyebrow="Pricing"
        title="Pay for minutes, not headcount"
        subtitle="Every plan includes your agent on the phone and in website chat, recordings and transcripts, and the browser test console. Inbound and outbound minutes share one pool."
      />

      <Section labelledBy="plans-title" className="pt-12 sm:pt-14">
        <h2 id="plans-title" className="sr-only">
          Plans
        </h2>
        <PricingPlans />
      </Section>

      <Section tone="muted" labelledBy="addons-title">
        <SectionHeading
          id="addons-title"
          eyebrow="Add-ons"
          title="Add only what you need"
          subtitle="Available on any plan, billed monthly unless stated."
        />
        <div className="mx-auto mt-10 max-w-4xl">
          <AddonList />
        </div>
      </Section>

      <Section labelledBy="compare-title">
        <SectionHeading
          id="compare-title"
          eyebrow="Compare"
          title="What answering the phone costs today"
          subtitle="Growth covers 600 minutes for $149 — about $0.25 a minute, answering 24/7, with booking and call-backs built in."
        />
        <div className="mt-12">
          <Comparison />
        </div>
      </Section>

      <Section id="roi" tone="muted" labelledBy="roi-title">
        <SectionHeading
          id="roi-title"
          eyebrow="ROI calculator"
          title="What are missed calls costing you?"
          subtitle="Plug in your own numbers. Every step of the math is shown — no hidden multipliers."
        />
        <div className="mx-auto mt-12 max-w-5xl">
          <RoiCalculator />
        </div>
      </Section>

      <Section labelledBy="pricing-faq-title">
        <SectionHeading id="pricing-faq-title" eyebrow="FAQ" title="Pricing questions" />
        <div className="mt-10">
          <FaqList items={PRICING_FAQS} />
        </div>
      </Section>

      <CtaBand
        title="Try it on your own calls first"
        subtitle={`${TRIAL.days} days, ${TRIAL.minutes} call minutes, every agent unlocked. Or talk to sales about volume pricing.`}
      />
    </>
  );
}
