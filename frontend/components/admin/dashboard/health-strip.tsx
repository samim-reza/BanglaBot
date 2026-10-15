import Link from "next/link";

import { engineItems, systemItems, type HealthItem } from "@/components/admin/health-model";
import { StatusChip, STATE_WORD } from "@/components/admin/status-chip";
import type { SystemHealth, VoiceEngine } from "@/services/api/admin/system";

/** One row of provider + infrastructure status; each chip links to its detail page. */
export function HealthStrip({ engine, health }: { engine: VoiceEngine | null; health: SystemHealth | null }) {
  const items: HealthItem[] = [...(engine ? engineItems(engine) : []), ...(health ? systemItems(health) : [])];
  return (
    <section aria-label="Health" className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Health</h2>
        {health && <span className="text-xs text-muted-foreground">{health.environment}</span>}
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading…
        </p>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {items.map((item) => (
            <li key={item.key}>
              <Link
                href={item.href}
                className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 transition-colors hover:border-tint-strong hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">{item.label}</span>
                  <span className="block truncate font-mono text-[11.5px] text-muted-foreground">{item.detail}</span>
                </span>
                <StatusChip state={item.state}>{STATE_WORD[item.state]}</StatusChip>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
