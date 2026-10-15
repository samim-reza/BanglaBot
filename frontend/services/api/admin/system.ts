/** Live calls, the voice engine and system health. Backend: backend/app/api/routes/admin_system.py */

import { request } from "../client";

// ------------------------------------------------------------------ live calls
export type LiveCall = {
  call_log_id: string;
  merchant_id: string;
  business: string;
  vertical: string;
  direction: string;
  /** Masked by the backend. */
  caller: string;
  seconds: number;
  stage: string;
  language: string;
  llm: string;
  stt: string;
  closing: boolean;
};

export type LiveCalls = { items: LiveCall[]; total: number };

// ------------------------------------------------------------------ voice engine
export type LlmLink = {
  key: string;
  provider: string;
  model: string;
  paid: boolean;
  /** Paid links are skipped unless paid models are allowed. */
  usable: boolean;
  available: boolean;
  blocked_for_s?: number;
  remaining_tokens?: number | null;
  remaining_requests?: number | null;
  /** Not reported yet (backend gap): the window's limits, for quota bars. */
  limit_tokens?: number | null;
  limit_requests?: number | null;
  requests?: number;
  failures?: number;
  last_error?: string;
};

/** `ready`: the chain's providers that have their key / URL. */
export type SpeechChain = { chain: string[]; ready: string[] };

export type TtsProviderStats = {
  provider?: string;
  requests?: number;
  chars?: number;
  cached_chars?: number;
  errors?: number;
  served_lines?: number;
  fallback_errors?: number;
  benched?: boolean;
  benched_for?: number;
  trips?: number;
  last_error?: string;
  [key: string]: unknown;
};

export type TtsCacheStats = {
  hits: Record<string, number>;
  misses: number;
  hit_rate: number;
  synthesized?: number;
  synth_bytes?: number;
  served_bytes?: number;
  entries?: number;
  bytes?: number;
  pinned?: number;
  [key: string]: unknown;
};

export type SpeechServer = {
  configured: boolean;
  up?: boolean;
  ms?: number;
  device?: string;
  stt?: unknown;
  tts?: unknown;
  vram_mb?: number;
  [key: string]: unknown;
};

export type VoiceEngine = {
  llm: { allow_paid: boolean; prompt_profile: string; chain: LlmLink[]; unconfigured: string[] };
  stt: { en: SpeechChain; bn: SpeechChain };
  tts: {
    en: SpeechChain;
    bn: SpeechChain;
    stats: { chains: Record<string, Record<string, TtsProviderStats>>; cache: TtsCacheStats | null };
  };
  speech_server: SpeechServer;
  pipelines: { entries: number; pinned: number; hits: number; misses: number };
  keys: Record<string, boolean>;
};

export type TtsTestResult = { ms: number; bytes: number; seconds: number; stats: Record<string, unknown> };
export type LlmTestResult = { ms: number; model: string; provider: string; text: string };

// ------------------------------------------------------------------ health
export type SystemHealth = {
  database: { up: boolean; ms?: number; error?: string };
  redis: { status: "ok" | "disabled" | "error" | string; message?: string };
  speech_server: SpeechServer;
  telnyx: { voice: boolean; configured: boolean; signatures_enforced: boolean };
  live_calls: number;
  environment: string;
};

export const systemApi = {
  liveCalls: () => request<LiveCalls>("/api/admin/live-calls", { auth: "admin" }),
  hangUp: (callLogId: string) =>
    request<{ ok: true }>(`/api/admin/live-calls/${encodeURIComponent(callLogId)}/hangup`, { method: "POST", auth: "admin" }),
  voiceEngine: () => request<VoiceEngine>("/api/admin/voice-engine", { auth: "admin" }),
  testTts: (text: string, language: "en" | "bn") =>
    request<TtsTestResult>("/api/admin/voice-engine/test-tts", { method: "POST", auth: "admin", body: JSON.stringify({ text, language }) }),
  testLlm: () => request<LlmTestResult>("/api/admin/voice-engine/test-llm", { method: "POST", auth: "admin" }),
  health: () => request<SystemHealth>("/api/admin/system/health", { auth: "admin" }),
};
