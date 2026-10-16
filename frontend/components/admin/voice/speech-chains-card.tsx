import { ChevronRight } from "lucide-react";

import { chainState } from "@/components/admin/health-model";
import { StatusChip, STATE_WORD, type HealthState } from "@/components/admin/status-chip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SpeechChain, TtsProviderStats, VoiceEngine } from "@/services/api/admin/system";

type ProviderLook = { state: HealthState; word: string };

function providerLook(name: string, chain: SpeechChain, stats: TtsProviderStats | undefined, speechUp: boolean | undefined): ProviderLook {
  if (!chain.ready.includes(name)) return { state: "off", word: "No key" };
  if (name === "local" && speechUp === false) return { state: "down", word: "Server down" };
  if (stats?.benched) return { state: "warn", word: `Benched ${Math.ceil(stats.benched_for ?? 0)}s` };
  return { state: "ok", word: "Ready" };
}

function ChainRow({
  label,
  chain,
  stats,
  speechUp,
  benched,
}: {
  label: string;
  chain: SpeechChain;
  stats?: Record<string, TtsProviderStats>;
  speechUp?: boolean;
  benched?: string[];
}) {
  const overall = chainState(chain, { speechUp, benched });
  return (
    <div className="flex flex-col gap-2 border-b border-border py-3 last:border-0 sm:flex-row sm:items-center">
      <div className="flex w-28 shrink-0 items-center justify-between gap-2 sm:block">
        <span className="text-sm font-semibold">{label}</span>
        <span className="sm:mt-1 sm:block">
          <StatusChip state={overall}>{STATE_WORD[overall]}</StatusChip>
        </span>
      </div>
      <ol className="flex flex-wrap items-center gap-1.5" aria-label={`${label} order`}>
        {chain.chain.length === 0 && <li className="text-sm text-muted-foreground">No chain set</li>}
        {chain.chain.map((name, index) => {
          const look = providerLook(name, chain, stats?.[name], speechUp);
          return (
            <li key={name} className="flex items-center gap-1.5">
              {index > 0 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />}
              <span className="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1" title={stats?.[name]?.last_error || undefined}>
                <span className="font-mono text-xs font-semibold">{name}</span>
                <StatusChip state={look.state}>{look.word}</StatusChip>
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** Speech-to-text and text-to-speech fallback chains, first choice on the left. */
export function SpeechChainsCard({ engine }: { engine: VoiceEngine }) {
  const speechUp = engine.speech_server.configured ? Boolean(engine.speech_server.up) : undefined;
  const ttsStats: Record<string, TtsProviderStats> = {};
  for (const providers of Object.values(engine.tts.stats?.chains ?? {})) Object.assign(ttsStats, providers);
  const benched = Object.entries(ttsStats)
    .filter(([, stats]) => stats?.benched)
    .map(([name]) => name);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Speech chains</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <ChainRow label="STT" chain={engine.stt.en} speechUp={speechUp} />
        <ChainRow label="TTS" chain={engine.tts.en} stats={ttsStats} speechUp={speechUp} benched={benched} />
      </CardContent>
    </Card>
  );
}
