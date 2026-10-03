import { Check } from "lucide-react";

import { STEPS } from "@/lib/site-content";
import { cn } from "@/lib/utils";

/** The four set-up steps; `detailed` adds the bullet points under each. */
export function Steps({ detailed = false }: { detailed?: boolean }) {
  return (
    <ol className={cn("grid gap-4", detailed ? "md:grid-cols-2" : "sm:grid-cols-2 lg:grid-cols-4")}>
      {STEPS.map((step, index) => (
        <li key={step.title} className="relative rounded-xl border border-border bg-card p-6">
          <span
            className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground"
            aria-hidden
          >
            {index + 1}
          </span>
          <h3 className="mt-4 font-semibold text-foreground">
            <span className="sr-only">Step {index + 1}: </span>
            {step.title}
          </h3>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{step.body}</p>
          {detailed && (
            <ul className="mt-4 space-y-2 text-sm">
              {step.points.map((point) => (
                <li key={point} className="flex gap-2 text-foreground">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
                  {point}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}
