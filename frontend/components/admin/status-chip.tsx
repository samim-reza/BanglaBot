import { CircleCheck, CircleMinus, CircleX, TriangleAlert } from "lucide-react";

import { Pill, type Tone } from "@/components/admin/badges";

/** ok · warn (degraded / cooling down) · down · off (not configured). */
export type HealthState = "ok" | "warn" | "down" | "off";

const LOOK: Record<HealthState, { tone: Tone; icon: typeof CircleCheck }> = {
  ok: { tone: "green", icon: CircleCheck },
  warn: { tone: "amber", icon: TriangleAlert },
  down: { tone: "red", icon: CircleX },
  off: { tone: "neutral", icon: CircleMinus },
};

/** A status chip: icon + label, never colour alone. `title` carries the how/why on hover. */
export function StatusChip({ state, children, title }: { state: HealthState; children: React.ReactNode; title?: string }) {
  const { tone, icon: Icon } = LOOK[state];
  return (
    <span title={title}>
      <Pill tone={tone}>
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        {children}
      </Pill>
    </span>
  );
}

export const STATE_WORD: Record<HealthState, string> = { ok: "OK", warn: "Degraded", down: "Down", off: "Off" };
