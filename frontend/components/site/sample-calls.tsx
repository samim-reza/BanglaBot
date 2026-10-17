import { SampleCallCard } from "@/components/site/sample-call-card";
import { Section, SectionHeading } from "@/components/site/section";
import { SAMPLE_CALLS } from "@/lib/site/sample-calls";
import type { AgentKey } from "@/lib/site/types";
import { cn } from "@/lib/utils";

/** The sample call for a business type, if one was recorded. */
export function sampleCallFor(vertical: AgentKey) {
  return SAMPLE_CALLS.find((call) => call.vertical === vertical);
}

/** Homepage "Hear it": every sample call side by side. */
export function SampleCallsSection({ className }: { className?: string }) {
  return (
    <Section id="hear-it" tone="muted" labelledBy="hear-title" className={className}>
      <SectionHeading
        id="hear-title"
        eyebrow="Hear it"
        title="Listen to the agent take a call"
        subtitle="Three short sample calls, scripted and voiced in the agent's default voice."
      />
      <ul className="mt-12 grid items-start gap-5 lg:grid-cols-3">
        {SAMPLE_CALLS.map((call) => (
          <li key={call.key}>
            <SampleCallCard call={call} />
          </li>
        ))}
      </ul>
    </Section>
  );
}

/** Solution pages: the matching sample call next to a short heading (renders nothing without one). */
export function SampleCallBand({ vertical, className }: { vertical: AgentKey; className?: string }) {
  const call = sampleCallFor(vertical);
  if (!call) return null;
  return (
    <Section id="hear-it" tone="muted" labelledBy="hear-title" className={cn("border-t-0", className)}>
      <div className="grid items-center gap-10 lg:grid-cols-[1fr_1.1fr] lg:gap-14">
        <SectionHeading
          id="hear-title"
          align="left"
          eyebrow="Hear it"
          title="Listen to a sample call"
          subtitle={`A scripted ${Math.round(call.duration)}-second call to ${call.business}, voiced in the agent's default voice.`}
        />
        <SampleCallCard call={call} />
      </div>
    </Section>
  );
}
