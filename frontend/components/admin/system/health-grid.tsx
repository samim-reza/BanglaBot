import Link from "next/link";
import { Database, Phone, Radio, Server } from "lucide-react";

import { systemItems } from "@/components/admin/health-model";
import { StatusChip, STATE_WORD } from "@/components/admin/status-chip";
import { SpeechServerCard } from "@/components/admin/voice/speech-server-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SystemHealth } from "@/services/api/admin/system";

function Tile({ icon: Icon, title, children, chip }: { icon: React.ComponentType<{ className?: string }>; title: string; children: React.ReactNode; chip?: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          {title}
        </CardTitle>
        {chip}
      </CardHeader>
      <CardContent className="text-sm">{children}</CardContent>
    </Card>
  );
}

const yesNo = (value: boolean) => (value ? "Yes" : "No");

/** Database, Redis, telephony, speech server and live calls. */
export function HealthGrid({ health }: { health: SystemHealth }) {
  const items = Object.fromEntries(systemItems(health).map((item) => [item.key, item]));
  const chip = (key: string) => <StatusChip state={items[key].state}>{STATE_WORD[items[key].state]}</StatusChip>;
  return (
    <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
      <Tile icon={Database} title="Database" chip={chip("db")}>
        {health.database.up ? (
          <p>
            Query in <span className="font-semibold">{health.database.ms ?? "?"} ms</span>
          </p>
        ) : (
          <p className="break-words text-destructive">{health.database.error || "Unreachable"}</p>
        )}
      </Tile>
      <Tile icon={Server} title="Redis" chip={chip("redis")}>
        <p>{health.redis.status === "disabled" ? "Not configured — rate limits and caches stay in-process." : health.redis.status === "ok" ? "Connected." : health.redis.message || "Error"}</p>
      </Tile>
      <Tile icon={Phone} title="Telnyx" chip={chip("telnyx")}>
        <dl className="grid grid-cols-2 gap-y-1">
          <dt className="text-muted-foreground">Configured</dt>
          <dd>{yesNo(health.telnyx.configured)}</dd>
          <dt className="text-muted-foreground">Voice ready</dt>
          <dd>{yesNo(health.telnyx.voice)}</dd>
          <dt className="text-muted-foreground" title="Webhook signatures are checked">
            Signatures
          </dt>
          <dd>{health.telnyx.signatures_enforced ? "Enforced" : "Not enforced"}</dd>
        </dl>
      </Tile>
      <Tile icon={Radio} title="Live calls">
        <p className="text-2xl font-semibold">{health.live_calls}</p>
        <Link href="/admin/live" className="text-sm text-primary hover:underline">
          View live calls
        </Link>
      </Tile>
      <SpeechServerCard server={health.speech_server} />
    </div>
  );
}
