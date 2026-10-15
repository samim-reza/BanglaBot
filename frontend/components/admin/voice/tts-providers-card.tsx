import { fmtCompact, fmtInt } from "@/components/admin/numbers";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { TtsProviderStats, VoiceEngine } from "@/services/api/admin/system";

/** Per-provider TTS counters since the process started (merged across the chains built so far). */
export function TtsProvidersCard({ engine }: { engine: VoiceEngine }) {
  const rows = new Map<string, TtsProviderStats>();
  for (const providers of Object.values(engine.tts.stats?.chains ?? {})) {
    for (const [name, stats] of Object.entries(providers)) rows.set(name, stats);
  }
  if (rows.size === 0) return null;
  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle>TTS providers</CardTitle>
      </CardHeader>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Provider</TableHead>
            <TableHead className="text-right">Lines served</TableHead>
            <TableHead className="text-right">Requests</TableHead>
            <TableHead className="text-right">Characters</TableHead>
            <TableHead className="text-right" title="Characters served from cache">
              Cached chars
            </TableHead>
            <TableHead className="text-right">Errors</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[...rows.entries()].map(([name, stats]) => (
            <TableRow key={name}>
              <TableCell className="font-mono text-xs font-semibold">{name}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtInt(stats.served_lines ?? 0)}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtInt(stats.requests ?? 0)}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtCompact(stats.chars ?? 0)}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtCompact(stats.cached_chars ?? 0)}</TableCell>
              <TableCell className="text-right tabular-nums">
                <span className={(stats.errors ?? 0) + (stats.fallback_errors ?? 0) ? "font-semibold text-destructive" : undefined} title={stats.last_error || undefined}>
                  {fmtInt((stats.errors ?? 0) + (stats.fallback_errors ?? 0))}
                </span>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
