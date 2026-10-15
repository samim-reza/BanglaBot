/** Turns the voice-engine and system-health payloads into one status per component. */

import type { HealthState } from "@/components/admin/status-chip";
import type { LlmLink, SpeechChain, SpeechServer, SystemHealth, VoiceEngine } from "@/services/api/admin/system";

export type HealthItem = { key: string; label: string; state: HealthState; detail: string; href: string };

export function llmLinkState(link: LlmLink): { state: HealthState; word: string } {
  if (!link.usable) return { state: "off", word: "Paid off" };
  if (!link.available) return { state: "warn", word: link.blocked_for_s ? `Cooling ${Math.ceil(link.blocked_for_s)}s` : "Unavailable" };
  return { state: "ok", word: "Ready" };
}

export function llmState(engine: VoiceEngine): HealthItem {
  const usable = engine.llm.chain.filter((link) => link.usable);
  const ready = usable.filter((link) => link.available);
  const state: HealthState = ready.length === 0 ? "down" : ready[0] !== usable[0] ? "warn" : "ok";
  const detail = ready[0] ? ready[0].key : usable.length ? "Every model cooling down" : "No usable model";
  return { key: "llm", label: "LLM", state, detail, href: "/admin/voice" };
}

/** A speech chain is down with no configured provider, degraded when its first choice is missing or benched. */
export function chainState(chain: SpeechChain, opts: { speechUp?: boolean; benched?: string[] } = {}): HealthState {
  const ready = chain.ready.filter((name) => !(name === "local" && opts.speechUp === false) && !opts.benched?.includes(name));
  if (ready.length === 0) return chain.chain.length ? "down" : "off";
  return ready[0] === chain.chain[0] ? "ok" : "warn";
}

/** Providers of a TTS chain that the fallback engine has benched after errors. */
export function benchedTts(engine: VoiceEngine): string[] {
  const out = new Set<string>();
  for (const providers of Object.values(engine.tts.stats?.chains ?? {})) {
    for (const [name, stats] of Object.entries(providers)) if (stats?.benched) out.add(name);
  }
  return [...out];
}

export function speechServerState(server: SpeechServer | undefined): HealthState {
  if (!server?.configured) return "off";
  return server.up ? "ok" : "down";
}

export function engineItems(engine: VoiceEngine): HealthItem[] {
  const speechUp = engine.speech_server.configured ? Boolean(engine.speech_server.up) : undefined;
  const benched = benchedTts(engine);
  const speech = (kind: "stt" | "tts", lang: "en" | "bn"): HealthItem => {
    const chain = engine[kind][lang];
    const state = chainState(chain, { speechUp, benched: kind === "tts" ? benched : undefined });
    return {
      key: `${kind}-${lang}`,
      label: `${kind.toUpperCase()} ${lang === "en" ? "EN" : "BN"}`,
      state,
      detail: chain.ready[0] ?? "No provider",
      href: "/admin/voice",
    };
  };
  return [llmState(engine), speech("stt", "en"), speech("stt", "bn"), speech("tts", "en"), speech("tts", "bn")];
}

export function systemItems(health: SystemHealth): HealthItem[] {
  const redis = health.redis?.status;
  const telnyx = health.telnyx;
  return [
    {
      key: "db",
      label: "Database",
      state: health.database?.up ? "ok" : "down",
      detail: health.database?.up ? `${health.database.ms ?? "?"} ms` : "Unreachable",
      href: "/admin/system",
    },
    { key: "redis", label: "Redis", state: redis === "ok" ? "ok" : redis === "disabled" ? "off" : "down", detail: redis ?? "—", href: "/admin/system" },
    {
      key: "speech",
      label: "Speech server",
      state: speechServerState(health.speech_server),
      detail: !health.speech_server?.configured ? "Not set" : health.speech_server.up ? `${health.speech_server.ms ?? "?"} ms` : "Unreachable",
      href: "/admin/system",
    },
    {
      key: "telnyx",
      label: "Telnyx",
      state: !telnyx?.configured ? "off" : !telnyx.voice ? "down" : telnyx.signatures_enforced ? "ok" : "warn",
      detail: !telnyx?.configured ? "Not set" : !telnyx.voice ? "Voice off" : telnyx.signatures_enforced ? "Voice on" : "Signatures off",
      href: "/admin/system",
    },
  ];
}
