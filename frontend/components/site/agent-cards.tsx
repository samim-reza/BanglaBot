import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { AGENTS } from "@/lib/site-content";

/** The four ready-made agents, each linking to its solution page. */
export function AgentCards() {
  return (
    <ul className="grid gap-4 sm:grid-cols-2">
      {AGENTS.map((agent) => {
        const Icon = agent.icon;
        return (
          <li key={agent.key}>
            <Link
              href={`/solutions/${agent.slug}`}
              className="group flex h-full flex-col rounded-xl border border-border bg-card p-6 transition-colors hover:border-tint-strong hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex items-start gap-4">
                <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                <div className="min-w-0">
                  <h3 className="text-lg font-semibold text-foreground">{agent.name}</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">{agent.forWho}</p>
                </div>
              </div>
              <p className="mt-4 font-medium text-foreground">{agent.tagline}</p>
              <ul className="mt-3 space-y-1.5 text-sm text-muted-foreground">
                {agent.capabilities.slice(0, 3).map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
              <span className="mt-auto inline-flex items-center gap-1.5 pt-5 text-sm font-semibold text-primary-dark">
                Explore the {agent.agentName.toLowerCase()}
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
