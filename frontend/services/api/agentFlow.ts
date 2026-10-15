/** The owner's call-flow editor: the blueprint, the saved (sparse) settings, preview and reset. */

import { isApiRequestError, request } from "./client";
import type { Direction, FieldSpec, FieldType, Label } from "./types";

export type FlowLanguage = "en" | "bn";

/** ask | gate (yes/no) | router | effect (after the booking) | line (spoken only) | global (any time) | readback */
export type SkillKind = "ask" | "gate" | "router" | "effect" | "line" | "global" | "readback";

/** A spoken line the owner may reword, per language. */
export type FlowLineSpec = {
  key: string;
  label: string;
  default: Partial<Record<FlowLanguage, string>>;
  variables: string[];
  /** Placeholders that must stay in the text. */
  required_vars: string[];
  max_chars: number;
};

/** A skill option: a regular field spec, or the intake editors (`fields`, `custom_fields`). */
export type FlowOptionSpec = Omit<FieldSpec, "type"> & { type: FieldType | "fields" | "custom_fields" };

export type FlowSkill = {
  key: string;
  kind: SkillKind;
  label: Partial<Label>;
  description: Partial<Label>;
  toggleable: boolean;
  default_enabled: boolean;
  options: FlowOptionSpec[];
  defaults: Record<string, unknown>;
  lines: FlowLineSpec[];
};

export type FlowBranch = {
  key: string;
  label: Partial<Label>;
  /** Skill keys in their default order. */
  skills: string[];
  /** Groups of skills the owner may reorder among themselves. */
  movable: string[][];
  /** skill → skills that must come earlier. */
  before: Record<string, string[]>;
  tail: string;
  toggleable: boolean;
};

export type FlowBlueprint = {
  key: string;
  vertical?: string;
  direction?: string;
  version?: number;
  /** Asked before any branch (e.g. "what do you need?"). */
  prelude: string[];
  router_slot?: string;
  branches: FlowBranch[];
  default_branch?: string;
  /** Active at any point of the call (emergency). */
  globals: string[];
  /** Run after the booking (texts, payment link). */
  effects: string[];
  /** Lines only (greeting, goodbye, read-back). */
  line_skills: string[];
  skills: Record<string, FlowSkill>;
};

export type FlowStepState = {
  enabled: boolean;
  options: Record<string, unknown>;
  /** Overrides only: language → line key → text. */
  lines: Partial<Record<string, Record<string, string>>>;
};

/** Every layer applied (defaults < business-type preset < owner < platform lock). */
export type FlowEffective = {
  steps: Record<string, FlowStepState>;
  branches: Record<string, { enabled: boolean }>;
  order: Record<string, string[]>;
};

export type FlowDirectionView = { blueprint: FlowBlueprint; effective: FlowEffective };

/** What is stored: only what differs from the defaults. */
export type FlowConfig = {
  _v?: number;
  steps?: Record<string, { enabled?: boolean; options?: Record<string, unknown>; lines?: Record<string, Record<string, string>> }>;
  branches?: Record<string, { enabled: boolean }>;
  order?: Record<string, string[]>;
};

export type AgentFlow = {
  vertical: string;
  config: FlowConfig;
  /** Platform-locked paths, e.g. "steps.payment.options.mode". */
  locked: string[];
  /** Version of what is stored; sent back on save so two editors can't overwrite each other. */
  hash: string;
  languages: FlowLanguage[];
  editing: "lines" | "full";
  directions: Partial<Record<Direction, FlowDirectionView>>;
};

export type FlowPreviewStep = { skill: string; label: Partial<Label>; kind: SkillKind | string; says: string };
export type FlowPreviewBranch = { key: string; label: Partial<Label>; steps: FlowPreviewStep[] };
export type AgentFlowPreview = {
  language: string;
  directions: Partial<Record<Direction, { opening: string; branches: FlowPreviewBranch[] }>>;
};

export type FlowFieldError = { path: string; message: string };

const json = (method: string, body: unknown) => ({ method, auth: "merchant" as const, body: JSON.stringify(body) });

export const agentFlowApi = {
  /** 404 = this business type has a fixed call flow. */
  get: () => request<AgentFlow>("/api/agent/flow", { auth: "merchant" }),
  /** 409 = changed somewhere else (reload); 422 = field errors (see `flowErrors`). */
  save: (config: FlowConfig, base_hash: string | null) => request<AgentFlow>("/api/agent/flow", json("PUT", { config, base_hash })),
  preview: (config: FlowConfig | null) => request<AgentFlowPreview>("/api/agent/flow/preview", json("POST", { config })),
  /** Back to the platform defaults (platform locks still apply). */
  reset: () => request<AgentFlow>("/api/agent/flow/reset", { method: "POST", auth: "merchant" }),
};

/** The `{errors, locked}` of a 422 from save / preview, or null for any other error. */
export function flowErrors(error: unknown): { errors: FlowFieldError[]; locked: string[] } | null {
  if (!isApiRequestError(error) || error.status !== 422) return null;
  const detail = (error.body as { detail?: unknown } | undefined)?.detail;
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return null;
  const raw = detail as { errors?: unknown; locked?: unknown };
  const errors = Array.isArray(raw.errors)
    ? raw.errors
        .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
        .map((item) => ({ path: String(item.path ?? ""), message: String(item.message ?? "") }))
    : [];
  const locked = Array.isArray(raw.locked) ? raw.locked.map(String) : [];
  return { errors, locked };
}
