/** The draft as the sparse settings document the server stores (see model.ts for the baseline). */

import type { FlowConfig, FlowOptionSpec } from "@/services/api";

import { canon, squash, type FlowDraft, type FlowModel } from "./model";

// ---------------------------------------------------------------- option values

/** An option value in the form the server stores (undefined = empty → default). */
export function normalizeOption(spec: FlowOptionSpec, value: unknown): unknown {
  if (value === undefined || value === null || value === "") return undefined;
  switch (spec.type) {
    case "list":
    case "days":
    case "multiselect":
      return Array.isArray(value) ? value.map((item) => (typeof item === "string" ? item.trim() : item)).filter((item) => item !== "") : value;
    case "number":
    case "money": {
      const number = Number(value);
      return Number.isFinite(number) ? number : undefined;
    }
    case "fields":
      return Array.isArray(value) ? value.map(normalizeFieldRow) : value;
    case "custom_fields":
      return Array.isArray(value) && value.length ? value.map(normalizeCustomRow) : undefined;
    default:
      return typeof value === "string" ? value.trim() || undefined : value;
  }
}

function normalizeFieldRow(raw: unknown): Record<string, unknown> {
  const row = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const out: Record<string, unknown> = { key: String(row.key ?? ""), on: Boolean(row.on), required: Boolean(row.required), ask: row.ask !== false };
  const question = squash(row.question);
  if (question) out.question = question;
  return out;
}

function normalizeCustomRow(raw: unknown): Record<string, unknown> {
  const row = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const type = String(row.type || "text");
  const out: Record<string, unknown> = {
    key: String(row.key ?? "").trim().toLowerCase(),
    label: squash(row.label),
    type,
    question: squash(row.question),
    required: Boolean(row.required),
    on: row.on !== false,
  };
  if (type === "choice") {
    out.choices = (Array.isArray(row.choices) ? row.choices : []).map((choice) => squash(choice)).filter(Boolean);
  }
  return out;
}

// ---------------------------------------------------------------- the sparse config

/** The draft as the sparse settings document (only what differs from the baseline). */
export function buildConfig(model: FlowModel, draft: FlowDraft, locked: string[]): FlowConfig {
  const isLocked = (path: string) => locked.includes(path);
  const steps: NonNullable<FlowConfig["steps"]> = {};
  for (const [key, skill] of Object.entries(model.skills)) {
    const now = draft.steps[key];
    const base = model.baseline.steps[key];
    if (!now || !base) continue;
    const entry: NonNullable<FlowConfig["steps"]>[string] = {};
    if (skill.toggleable && !isLocked(`steps.${key}.enabled`) && now.enabled !== base.enabled) entry.enabled = now.enabled;
    const options: Record<string, unknown> = {};
    for (const spec of skill.options) {
      if (isLocked(`steps.${key}.options.${spec.key}`)) continue;
      const value = normalizeOption(spec, now.options[spec.key]);
      if (value !== undefined && canon(value) !== canon(normalizeOption(spec, base.options[spec.key]))) options[spec.key] = value;
    }
    if (Object.keys(options).length) entry.options = options;
    const lines: Record<string, Record<string, string>> = {};
    for (const lang of model.languages) {
      for (const spec of skill.lines) {
        if (isLocked(`steps.${key}.lines.${lang}.${spec.key}`)) continue;
        const text = squash(now.lines[lang]?.[spec.key]);
        if (text && text !== squash(base.lines[lang]?.[spec.key])) (lines[lang] ??= {})[spec.key] = text;
      }
    }
    if (Object.keys(lines).length) entry.lines = lines;
    if (Object.keys(entry).length) steps[key] = entry;
  }
  const branches: NonNullable<FlowConfig["branches"]> = {};
  const order: NonNullable<FlowConfig["order"]> = {};
  for (const [key, branch] of Object.entries(model.branches)) {
    if (branch.toggleable && !isLocked(`branches.${key}.enabled`) && draft.branches[key] !== model.baseline.branches[key]) {
      branches[key] = { enabled: draft.branches[key] };
    }
    if (!isLocked(`order.${key}`) && canon(draft.order[key]) !== canon(model.baseline.order[key])) order[key] = [...draft.order[key]];
  }
  const config: FlowConfig = { _v: 1 };
  if (Object.keys(steps).length) config.steps = steps;
  if (Object.keys(branches).length) config.branches = branches;
  if (Object.keys(order).length) config.order = order;
  return config;
}
