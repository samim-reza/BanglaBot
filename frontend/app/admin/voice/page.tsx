"use client";

import { RefreshCw } from "lucide-react";

import { useAdminMe } from "@/components/admin/shell/admin-me";
import { LoadingRows } from "@/components/admin/states";
import { CacheCard } from "@/components/admin/voice/cache-card";
import { KeysCard } from "@/components/admin/voice/keys-card";
import { LlmChainCard } from "@/components/admin/voice/llm-chain-card";
import { SpeechChainsCard } from "@/components/admin/voice/speech-chains-card";
import { SpeechServerCard } from "@/components/admin/voice/speech-server-card";
import { TestPanel } from "@/components/admin/voice/test-panel";
import { TtsProvidersCard } from "@/components/admin/voice/tts-providers-card";
import { useVoiceEngine } from "@/components/admin/voice/use-voice-engine";
import { ApiError } from "@/components/api-error";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";

export default function AdminVoiceEnginePage() {
  const { engine, error, refreshing, reload } = useVoiceEngine();
  const { can } = useAdminMe();
  return (
    <>
      <PageHeader
        title="Voice engine"
        subtitle="This server process · updates every 10 s"
        actions={
          <Button variant="outline" onClick={() => void reload()} disabled={refreshing} aria-label="Refresh">
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin motion-reduce:animate-none" : ""}`} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        }
      />
      <ApiError message={error} />
      {!engine ? (
        error ? null : <LoadingRows label="Loading the voice engine…" rows={6} />
      ) : (
        <div className="grid gap-6 xl:grid-cols-3">
          <div className="space-y-6 xl:col-span-2">
            <LlmChainCard engine={engine} />
            <SpeechChainsCard engine={engine} />
            <TtsProvidersCard engine={engine} />
          </div>
          <div className="space-y-6">
            {can("voiceTests") && <TestPanel />}
            <CacheCard engine={engine} />
            <SpeechServerCard server={engine.speech_server} />
            <KeysCard keys={engine.keys} />
          </div>
        </div>
      )}
    </>
  );
}
