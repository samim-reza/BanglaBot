/** An account's call flow as the admin sees it (owner settings + admin locks) and its provider overrides.
 * Backend: backend/app/api/routes/admin_flow.py. The flow shapes are the owner editor's (`../agentFlow`). */

import { request } from "../client";
import type { AgentFlow, FlowConfig } from "../agentFlow";

/** path → locked value. Paths: steps.<skill>.enabled · steps.<skill>.options.<opt> ·
 * steps.<skill>.lines.<lang>.<key> · branches.<branch>.enabled · order.<branch> */
export type FlowLocks = Record<string, unknown>;

/** GET /api/admin/merchants/{id}/agent-flow: the owner's view plus the lock values. */
export type AdminAgentFlow = AgentFlow & { locks: FlowLocks };

/** Comma-separated chains; empty = platform default. LLM entries are `provider:model`. */
export type ProviderChains = { llm_chain: string; stt_chain: string; tts_chain: string };

const base = (id: string) => `/api/admin/merchants/${encodeURIComponent(id)}`;

export const adminFlowApi = {
  /** 404 = this business type has a fixed call flow. */
  get: (merchantId: string) => request<AdminAgentFlow>(`${base(merchantId)}/agent-flow`, { auth: "admin" }),
  /** Admin edits ignore locks. A stale `base_hash` answers 409; field errors 422 (`flowErrors`). */
  save: (merchantId: string, config: FlowConfig, base_hash: string) =>
    request<AgentFlow>(`${base(merchantId)}/agent-flow`, { method: "PUT", auth: "admin", body: JSON.stringify({ config, base_hash }) }),
  /** Replaces the whole lock set; a `null` value freezes the setting's current value. */
  saveLocks: (merchantId: string, locks: Record<string, unknown | null>) =>
    request<AgentFlow>(`${base(merchantId)}/agent-flow-locks`, { method: "PUT", auth: "admin", body: JSON.stringify({ locks }) }),
  /** 422 `{detail: {errors: [{path: "llm_chain" | "stt_chain" | "tts_chain", message}]}}`. */
  saveProviders: (merchantId: string, chains: ProviderChains) =>
    request<{ ok: true; provider_settings: Partial<ProviderChains> }>(`${base(merchantId)}/providers`, {
      method: "PUT",
      auth: "admin",
      body: JSON.stringify(chains),
    }),
};

/** STT / TTS provider names the backend accepts (app/api/routes/admin_flow.py). */
export const STT_PROVIDERS = ["local", "deepgram", "groq", "openai"] as const;
export const TTS_PROVIDERS = ["local", "deepgram", "azure", "gemini", "edge"] as const;
