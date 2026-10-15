import { fmtInt, fmtMs } from "@/components/admin/numbers";
import { speechServerState } from "@/components/admin/health-model";
import { StatusChip, STATE_WORD } from "@/components/admin/status-chip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SpeechServer } from "@/services/api/admin/system";

import { Facts } from "./ratio-bar";

const KNOWN = new Set(["configured", "up", "ms", "device", "stt", "tts", "vram_mb", "status", "ok"]);

/** A model name, a list of loaded models, or `{model: …}` — whatever the server reports. */
function modelText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(modelText).join(", ");
  const record = value as Record<string, unknown>;
  return String(record.model ?? record.name ?? JSON.stringify(value));
}

/** The self-hosted speech server (local STT / TTS on the GPU box). */
export function SpeechServerCard({ server }: { server: SpeechServer | undefined }) {
  const state = speechServerState(server);
  const extra = Object.entries(server ?? {}).filter(([key, value]) => !KNOWN.has(key) && (typeof value !== "object" || value === null));
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle>Speech server</CardTitle>
        <StatusChip state={state}>{server?.configured ? STATE_WORD[state] : "Not set"}</StatusChip>
      </CardHeader>
      <CardContent>
        {!server?.configured ? (
          <p className="text-sm text-muted-foreground">No speech server URL — local STT/TTS are skipped.</p>
        ) : (
          <Facts
            items={[
              ["Ping", fmtMs(server.ms)],
              ["Device", server.device ? String(server.device) : "—"],
              ["VRAM", server.vram_mb !== undefined ? `${fmtInt(server.vram_mb)} MB` : "—"],
              ["STT", modelText(server.stt)],
              ["TTS", modelText(server.tts)],
              ...extra.map(([key, value]): [string, React.ReactNode] => [key.replace(/_/g, " "), String(value)]),
            ]}
          />
        )}
      </CardContent>
    </Card>
  );
}
