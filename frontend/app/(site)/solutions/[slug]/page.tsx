import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight, Check, ShieldCheck } from "lucide-react";

import { CallTranscript } from "@/components/site/call-transcript";
import { CtaBand } from "@/components/site/cta-band";
import { Container, Eyebrow, Section, SectionHeading } from "@/components/site/section";
import { Button } from "@/components/ui/button";
import { AGENTS, agentBySlug } from "@/lib/site-content";

type Props = { params: Promise<{ slug: string }> };

export const dynamicParams = false;

export function generateStaticParams() {
  return AGENTS.map((agent) => ({ slug: agent.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const agent = agentBySlug(slug);
  if (!agent) return {};
  return {
    title: `AI agent for ${agent.name.toLowerCase()}`,
    description: `${agent.tagline} ${agent.summary}`,
  };
}

export default async function SolutionPage({ params }: Props) {
  const { slug } = await params;
  const agent = agentBySlug(slug);
  if (!agent) notFound();
  const Icon = agent.icon;
  const others = AGENTS.filter((item) => item.key !== agent.key);

  return (
    <>
      <section className="relative overflow-hidden border-b border-border">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(55%_70%_at_10%_0%,hsl(var(--tint))_0%,transparent_70%)]"
        />
        <Container className="relative grid items-center gap-12 py-14 sm:py-20 lg:grid-cols-2">
          <div>
            <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
              <Link href="/solutions" className="hover:text-foreground hover:underline">
                Solutions
              </Link>
              <span aria-hidden> / </span>
              <span aria-current="page">{agent.name}</span>
            </nav>
            <div className="mt-6 flex items-center gap-3">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                <Icon className="h-5 w-5" aria-hidden />
              </span>
              <Eyebrow>{agent.agentName}</Eyebrow>
            </div>
            <h1 className="mt-4 text-balance text-3xl font-bold leading-tight tracking-tight text-foreground sm:text-4xl lg:text-5xl">
              {agent.tagline}
            </h1>
            <p className="mt-5 text-pretty text-lg leading-relaxed text-muted-foreground">{agent.summary}</p>
            <p className="mt-4 text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">Built for:</span> {agent.forWho}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild className="h-11 px-6">
                <Link href={`/contact?plan=trial&type=${agent.key}`}>
                  Start free trial
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
              </Button>
              <Button asChild variant="outline" className="h-11 px-6">
                <Link href={`/contact?type=${agent.key}`}>Talk to sales</Link>
              </Button>
            </div>
          </div>
          <CallTranscript conversation={agent.example} live />
        </Container>
      </section>

      <Section labelledBy="does-title">
        <div className="grid gap-12 lg:grid-cols-2">
          <div>
            <SectionHeading id="does-title" align="left" eyebrow="Capabilities" title="What it handles, start to finish" />
            <p className="mt-3 text-sm text-muted-foreground">{agent.directions}.</p>
            <ul className="mt-6 space-y-3">
              {agent.capabilities.map((item) => (
                <li key={item} className="flex gap-3 text-foreground">
                  <Check className="mt-1 h-4 w-4 shrink-0 text-primary" aria-hidden />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <SectionHeading align="left" eyebrow="What you set up" title="You fill in the facts; it handles the talking" />
            <ol className="mt-6 space-y-3">
              {agent.setup.map((item, index) => (
                <li key={item} className="flex gap-3 text-foreground">
                  <span
                    className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-accent-foreground"
                    aria-hidden
                  >
                    {index + 1}
                  </span>
                  {item}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </Section>

      <Section tone="muted" labelledBy="outcomes-title">
        <SectionHeading
          id="outcomes-title"
          eyebrow="Outcomes"
          title="Every call ends with a clear outcome"
          subtitle="Each call is recorded and transcribed, and the result is written to the record — so your team works from a list, not a voicemail box."
        />
        <ul className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {agent.outcomes.map((outcome) => (
            <li key={outcome.label} className="rounded-xl border border-border bg-card p-5">
              <span className="inline-flex rounded-full bg-accent px-2.5 py-0.5 text-[12.5px] font-semibold text-accent-foreground">
                {outcome.label}
              </span>
              <p className="mt-3 text-sm text-muted-foreground">{outcome.detail}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section labelledBy="safety-title">
        <div className="mx-auto max-w-3xl rounded-2xl border border-border bg-card p-6 sm:p-10">
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-6 w-6 text-primary" aria-hidden />
            <h2 id="safety-title" className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
              Safety rules it always follows
            </h2>
          </div>
          <ul className="mt-6 space-y-3">
            {agent.safety.map((rule) => (
              <li key={rule} className="flex gap-3 text-foreground">
                <Check className="mt-1 h-4 w-4 shrink-0 text-primary" aria-hidden />
                {rule}
              </li>
            ))}
          </ul>
          <p className="mt-6 text-sm text-muted-foreground">
            It answers only from your catalog and knowledge base.{" "}
            <Link href="/security" className="font-semibold text-primary-dark hover:underline">
              More on safety &amp; privacy
            </Link>
          </p>
        </div>
      </Section>

      <Section tone="muted" labelledBy="others-title">
        <SectionHeading id="others-title" title="Other agents on the same platform" />
        <ul className="mt-10 grid gap-4 md:grid-cols-3">
          {others.map((item) => {
            const OtherIcon = item.icon;
            return (
              <li key={item.key}>
                <Link
                  href={`/solutions/${item.slug}`}
                  className="flex h-full items-start gap-3 rounded-xl border border-border bg-card p-5 hover:border-tint-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <OtherIcon className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
                  <span>
                    <span className="block font-semibold text-foreground">{item.name}</span>
                    <span className="mt-1 block text-sm text-muted-foreground">{item.tagline}</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </Section>

      <CtaBand
        title={`Start with the ${agent.agentName.toLowerCase()} today`}
        trialHref={`/contact?plan=trial&type=${agent.key}`}
        salesHref={`/contact?type=${agent.key}`}
      />
    </>
  );
}
