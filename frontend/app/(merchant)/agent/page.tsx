"use client";

/** Agent: language, voice and greeting, plus the call-flow editor (or the fixed flow's steps). */

import { useState } from "react";
import { RefreshCw } from "lucide-react";

import { AgentVoiceCard } from "@/components/agent-flow/agent-voice-card";
import { FlowEditor } from "@/components/agent-flow/flow-editor";
import { LegacyFlow } from "@/components/agent-flow/legacy-flow";
import type { ReadyFlow } from "@/components/agent-flow/step-list";
import { useAgentFlow } from "@/components/agent-flow/use-agent-flow";
import { ApiError } from "@/components/api-error";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/lib/workspace";

export default function AgentPage() {
  const { vertical } = useWorkspace();
  // Older backends don't send the flag: try the editor and fall back on a 404.
  const flow = useAgentFlow(vertical.configurable_flow !== false);
  const [version, setVersion] = useState(0);
  const ready = flow.status === "ready" && flow.model && flow.draft;

  return (
    <div className="space-y-6">
      <PageHeader title="Agent" subtitle="What your agent says and asks, step by step." />
      <AgentVoiceCard editableFlow={flow.status !== "fixed"} onSaved={() => setVersion((n) => n + 1)} />
      {ready ? (
        <FlowEditor state={flow as ReadyFlow} />
      ) : flow.status === "fixed" ? (
        <LegacyFlow version={version} />
      ) : flow.status === "error" ? (
        <div className="space-y-3">
          <ApiError message={flow.loadError} />
          <Button type="button" variant="outline" size="sm" onClick={() => void flow.reload()}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            Try again
          </Button>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]" aria-busy="true" aria-label="Loading call flow">
          <div className="space-y-2">
            {[0, 1, 2, 3].map((key) => (
              <div key={key} className="h-16 animate-pulse rounded-lg bg-secondary" />
            ))}
          </div>
          <div className="h-64 animate-pulse rounded-lg bg-secondary" />
        </div>
      )}
    </div>
  );
}
