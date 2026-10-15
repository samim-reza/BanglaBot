import { fmtBytes, fmtInt, fmtPct } from "@/components/admin/numbers";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { VoiceEngine } from "@/services/api/admin/system";

import { Facts, RatioBar } from "./ratio-bar";

const TIER_LABELS: Record<string, string> = { hot: "Memory", disk: "Disk", local: "Local", shared: "Shared", inflight: "Joined in-flight" };

/** Audio (TTS) cache and compiled-pipeline cache: hit rates and size. */
export function CacheCard({ engine }: { engine: VoiceEngine }) {
  const cache = engine.tts.stats?.cache;
  const pipes = engine.pipelines;
  const pipeLookups = pipes.hits + pipes.misses;
  const pipeRate = pipeLookups ? pipes.hits / pipeLookups : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Caches</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <section aria-label="Audio cache" className="space-y-3">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold">Audio cache</h3>
            <span className="text-2xl font-semibold">{cache ? fmtPct(cache.hit_rate) : "—"}</span>
          </div>
          {cache ? (
            <>
              <RatioBar ratio={cache.hit_rate} label="Audio cache hit rate" />
              <Facts
                items={[
                  ...Object.entries(cache.hits ?? {}).map(([tier, hits]): [string, React.ReactNode] => [`${TIER_LABELS[tier] ?? tier} hits`, fmtInt(hits)]),
                  ["Misses", fmtInt(cache.misses)],
                  ["Clips", fmtInt(cache.entries)],
                  ["Size", fmtBytes(cache.bytes)],
                  ["Pinned", fmtInt(cache.pinned)],
                  ["Synthesized", fmtInt(cache.synthesized)],
                ]}
              />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Not started yet.</p>
          )}
        </section>
        <section aria-label="Pipeline cache" className="space-y-3">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold" title="Compiled call flows reused across calls">
              Pipeline cache
            </h3>
            <span className="text-2xl font-semibold">{pipeLookups ? fmtPct(pipeRate) : "—"}</span>
          </div>
          <RatioBar ratio={pipeRate} label="Pipeline cache hit rate" />
          <Facts
            items={[
              ["Hits", fmtInt(pipes.hits)],
              ["Misses", fmtInt(pipes.misses)],
              ["Compiled", fmtInt(pipes.entries)],
              ["Pinned", fmtInt(pipes.pinned)],
            ]}
          />
        </section>
      </CardContent>
    </Card>
  );
}
