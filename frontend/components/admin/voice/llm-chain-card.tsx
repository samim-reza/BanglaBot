import { Pill } from "@/components/admin/badges";
import { llmLinkState } from "@/components/admin/health-model";
import { fmtCompact, fmtInt } from "@/components/admin/numbers";
import { Meter } from "@/components/admin/stats";
import { StatusChip } from "@/components/admin/status-chip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { LlmLink, VoiceEngine } from "@/services/api/admin/system";

/** Remaining quota in the provider's current window: a bar when the limit is known, else the count. */
function Quota({ remaining, limit, unit }: { remaining?: number | null; limit?: number | null; unit: string }) {
  if (remaining === null || remaining === undefined) return <span className="text-muted-foreground">—</span>;
  if (limit) {
    return (
      <div className="w-28" title={`${fmtInt(remaining)} of ${fmtInt(limit)} ${unit} left`}>
        <Meter value={limit - remaining} max={limit} label={`${unit} used`} />
        <span className="mt-0.5 block text-[11px] text-muted-foreground">{fmtCompact(remaining)} left</span>
      </div>
    );
  }
  return <span title={`${unit} left in this window`}>{fmtCompact(remaining)}</span>;
}

function LinkRow({ link, index }: { link: LlmLink; index: number }) {
  const status = llmLinkState(link);
  return (
    <TableRow>
      <TableCell className="w-8 text-muted-foreground tabular-nums">{index + 1}</TableCell>
      <TableCell className="min-w-[12rem]">
        <div className="font-medium">{link.model}</div>
        <div className="text-xs text-muted-foreground">
          {link.provider}
          {link.paid && (
            <Pill tone="violet" className="ml-2 px-1.5 py-0 text-[11px]">
              Paid
            </Pill>
          )}
        </div>
      </TableCell>
      <TableCell>
        <StatusChip state={status.state} title={link.last_error || undefined}>
          {status.word}
        </StatusChip>
      </TableCell>
      <TableCell>
        <Quota remaining={link.remaining_requests} limit={link.limit_requests} unit="requests" />
      </TableCell>
      <TableCell>
        <Quota remaining={link.remaining_tokens} limit={link.limit_tokens} unit="tokens" />
      </TableCell>
      <TableCell className="text-right tabular-nums">{fmtInt(link.requests ?? 0)}</TableCell>
      <TableCell className="text-right tabular-nums">
        <span className={link.failures ? "font-semibold text-destructive" : undefined} title={link.last_error || undefined}>
          {fmtInt(link.failures ?? 0)}
        </span>
      </TableCell>
    </TableRow>
  );
}

/** The LLM fallback chain in the order calls try it. */
export function LlmChainCard({ engine }: { engine: VoiceEngine }) {
  const { llm } = engine;
  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <CardTitle>LLM chain</CardTitle>
        <div className="flex flex-wrap gap-2">
          <Pill tone={llm.allow_paid ? "violet" : "neutral"}>{llm.allow_paid ? "Paid allowed" : "Free only"}</Pill>
          <Pill tone="teal">Prompt: {llm.prompt_profile || "default"}</Pill>
        </div>
      </CardHeader>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>#</TableHead>
            <TableHead>Model</TableHead>
            <TableHead>Status</TableHead>
            <TableHead title="Requests left in the provider's current window">Requests left</TableHead>
            <TableHead title="Tokens left in the provider's current window">Tokens left</TableHead>
            <TableHead className="text-right">Calls</TableHead>
            <TableHead className="text-right" title="Failures in a row (hover for the last error)">
              Failures
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {llm.chain.map((link, index) => (
            <LinkRow key={link.key} link={link} index={index} />
          ))}
        </TableBody>
      </Table>
      {llm.unconfigured.length > 0 && (
        <CardContent className="border-t border-border pt-4 text-sm">
          <span className="text-muted-foreground">No key: </span>
          <span className="font-mono text-xs">{llm.unconfigured.join(", ")}</span>
        </CardContent>
      )}
    </Card>
  );
}
