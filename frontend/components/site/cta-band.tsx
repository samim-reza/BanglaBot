import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Container } from "@/components/site/section";
import { SALES_HREF, TRIAL, TRIAL_HREF } from "@/lib/site-content";

/** Closing call-to-action band used at the bottom of most pages. */
export function CtaBand({
  title = "Stop sending callers to voicemail.",
  subtitle = `Start a ${TRIAL.days}-day free trial with ${TRIAL.minutes} call minutes, or book a 20-minute demo with our team.`,
  trialHref = TRIAL_HREF,
  salesHref = SALES_HREF,
}: {
  title?: string;
  subtitle?: string;
  trialHref?: string;
  salesHref?: string;
}) {
  return (
    <section className="py-16 sm:py-20">
      <Container>
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[#0f766e] to-[#0d9488] px-6 py-12 text-center text-white sm:px-12">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full border-[28px] border-white/10"
          />
          <div
            aria-hidden
            className="pointer-events-none absolute -bottom-20 -left-10 h-48 w-48 rounded-full border-[20px] border-white/5"
          />
          <h2 className="relative text-balance text-2xl font-bold tracking-tight sm:text-3xl">{title}</h2>
          <p className="relative mx-auto mt-3 max-w-xl text-pretty text-white/85">{subtitle}</p>
          <div className="relative mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link
              href={trialHref}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-white px-5 text-sm font-semibold text-[#0f766e] transition-colors hover:bg-[#e6f4f2] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-[#0f766e]"
            >
              Start free trial
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
            <Link
              href={salesHref}
              className="inline-flex h-11 items-center justify-center rounded-md border border-white/40 px-5 text-sm font-semibold text-white transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              Talk to sales
            </Link>
          </div>
        </div>
      </Container>
    </section>
  );
}
