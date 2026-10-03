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
  description: `Voice agent plans from $49 a month, or a website chat agent for $29. Add WhatsApp, Messenger, extra minutes and more. ${TRIAL.days}-day free trial, annual billing with 2 months free.`,
};

export default function PricingPage() {
  return (
    <>
      <PageHero
        eyebrow="Pricing"
        title="Pick a plan, add what you need"
        subtitle="A voice agent for your phone line, or a chat agent for your website. Add channels and capacity whenever you need them."
      />

      <Section labelledBy="plans-title" className="pt-12 sm:pt-14">
        <h2 id="plans-title" className="sr-only">
          Plans
        </h2>
        <PricingPlans addonsHref="#addons" />
      </Section>

      <Section id="addons" tone="muted" labelledBy="addons-title">
        <SectionHeading id="addons-title" eyebrow="Add-ons" title="Add what you need" subtitle="On top of any plan. Monthly unless marked once." />
        <div className="mt-10">
          <AddonList />
        </div>
      </Section>

      <Section labelledBy="compare-title">
        <SectionHeading
          id="compare-title"
          eyebrow="Compare"
          title="What answering the phone costs today"
          subtitle="Growth covers 600 minutes for $149: about $0.25 a minute, answering 24/7, with booking and call-backs built in."
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
          subtitle="Plug in your own numbers. Every step of the math is shown."
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
        subtitle={`${TRIAL.days} days, ${TRIAL.minutes} call minutes, every channel switched on. Or talk to sales about volume pricing.`}
      />
    </>
  );
}
