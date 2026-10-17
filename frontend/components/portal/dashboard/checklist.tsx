"use client";

/** The dashboard's "Finish setup" card (the phone step requests a number: see ``phone-request``). */

import Link from "next/link";
import { CircleCheck, CircleDashed, ListChecks } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type Step = {
  key: string;
  done: boolean;
  title: string;
  /** A one-line hint under the title. */
  note?: string;
  href?: string;
  cta?: string;
  /** Replaces the link: e.g. the phone step's request button. */
  action?: React.ReactNode;
};

export function Checklist({ steps }: { steps: Step[] }) {
  const done = steps.filter((step) => step.done).length;
  return (
    <Card className="border-tint-strong">
      <CardHeader className="gap-3 pb-3 sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground" aria-hidden="true">
            <ListChecks className="h-4 w-4" />
          </span>
          <div className="space-y-0.5">
            <CardTitle>Finish setup</CardTitle>
            <CardDescription>
              {done} of {steps.length} done
            </CardDescription>
          </div>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-secondary sm:w-40"
          role="progressbar"
          aria-label="Setup progress"
          aria-valuemin={0}
          aria-valuemax={steps.length}
          aria-valuenow={done}
        >
          <div className="h-full rounded-full bg-primary" style={{ width: `${(done / steps.length) * 100}%` }} />
        </div>
      </CardHeader>
      <CardContent>
        <ol className="grid gap-2 md:grid-cols-2">
          {steps.map((step) => (
            <li key={step.key} className={cn("flex items-center gap-3 rounded-md border border-border p-3", step.done ? "bg-surface" : "bg-card")}>
              {step.done ? (
                <CircleCheck className="h-5 w-5 shrink-0 text-primary" aria-label="Done" />
              ) : (
                <CircleDashed className="h-5 w-5 shrink-0 text-muted-foreground" aria-label="To do" />
              )}
              <div className="min-w-0 flex-1">
                <p className={cn("text-sm font-medium", step.done && "text-muted-foreground line-through decoration-muted-foreground/50")}>{step.title}</p>
                {step.note && !step.done && <p className="truncate text-xs text-muted-foreground">{step.note}</p>}
              </div>
              {!step.done &&
                (step.action ??
                  (step.href && (
                    <Button asChild size="sm" variant="outline" className="shrink-0">
                      <Link href={step.href}>{step.cta}</Link>
                    </Button>
                  )))}
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
