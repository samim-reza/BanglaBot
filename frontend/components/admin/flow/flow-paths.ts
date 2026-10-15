/**
 * The admin call-flow view's model (pure functions).
 *
 * The admin edits the owner's SPARSE settings directly — only the paths the admin touches change, so
 * the owner's other choices (and values sitting under a lock) survive — and the lock map, which the
 * API replaces as a whole. What a setting will do on calls: lock > owner > (preset/default).
 */

import { t } from "@/lib/vertical";
import type { AgentFlow, FlowBranch, FlowConfig, FlowEffective, FlowOptionSpec, FlowSkill } from "@/services/api/agentFlow";
import type { FlowLocks } from "@/services/api/admin/flow";

export type FlowIndex = {
  skills: Record<string, FlowSkill>;
  branches: Record<string, FlowBranch>;
  effective: FlowEffective;
};

/** Skills and branches by key across both directions (a skill is configured once for both). */
export function indexFlow(flow: AgentFlow): FlowIndex {
  const out: FlowIndex = { skills: {}, branches: {}, effective: { steps: {}, branches: {}, order: {} } };
  for (const view of [flow.directions.inbound, flow.directions.outbound]) {
    if (!view) continue;
    for (const [key, skill] of Object.entries(view.blueprint.skills)) {
      out.skills[key] ??= skill;
      if (view.effective.steps[key]) out.effective.steps[key] ??= view.effective.steps[key];
    }
    for (const branch of view.blueprint.branches) {
      out.branches[branch.key] ??= branch;
      if (view.effective.branches[branch.key]) out.effective.branches[branch.key] ??= view.effective.branches[branch.key];
      if (view.effective.order[branch.key]) out.effective.order[branch.key] ??= view.effective.order[branch.key];
    }
  }
  return out;
}

export function canon(value: unknown): string {
  return JSON.stringify(value ?? null, (_key, inner) =>
    inner && typeof inner === "object" && !Array.isArray(inner)
      ? Object.fromEntries(Object.entries(inner as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)))
      : inner,
  );
}

export const enabledPath = (skill: string) => `steps.${skill}.enabled`;
export const optionPath = (skill: string, option: string) => `steps.${skill}.options.${option}`;
export const branchPath = (branch: string) => `branches.${branch}.enabled`;
export const orderPath = (branch: string) => `order.${branch}`;

/** The owner's own value at `path` (undefined = not set → default). */
export function ownerValue(config: FlowConfig, path: string): unknown {
  const [root, key, part, name] = path.split(".");
  if (root === "steps") {
    const step = config.steps?.[key];
    if (part === "enabled") return step?.enabled;
    if (part === "options") return step?.options?.[name];
    return undefined;
  }
  if (root === "branches") return config.branches?.[key]?.enabled;
  if (root === "order") return config.order?.[key];
  return undefined;
}

/** `config` with the owner's value at `path` replaced. */
export function withOwnerValue(config: FlowConfig, path: string, value: unknown): FlowConfig {
  const [root, key, part, name] = path.split(".");
  if (root === "steps") {
    const step = { ...(config.steps?.[key] ?? {}) };
    if (part === "enabled") step.enabled = Boolean(value);
    else if (part === "options") step.options = { ...(step.options ?? {}), [name]: value };
    return { ...config, steps: { ...(config.steps ?? {}), [key]: step } };
  }
  if (root === "branches") return { ...config, branches: { ...(config.branches ?? {}), [key]: { enabled: Boolean(value) } } };
  return config;
}

/** The blueprint default (what applies with no preset, owner value or lock). */
function defaultValue(index: FlowIndex, path: string): unknown {
  const [root, key, part, name] = path.split(".");
  if (root === "steps") {
    const skill = index.skills[key];
    if (part === "enabled") return skill ? (skill.toggleable ? skill.default_enabled : true) : true;
    if (part === "options") return skill?.defaults?.[name] ?? skill?.options.find((spec) => spec.key === name)?.default;
  }
  if (root === "branches") return true;
  if (root === "order") return index.branches[key]?.skills;
  return undefined;
}

function effectiveValue(index: FlowIndex, path: string): unknown {
  const [root, key, part, name] = path.split(".");
  if (root === "steps") {
    const step = index.effective.steps[key];
    if (part === "enabled") return step?.enabled;
    if (part === "options") return step?.options?.[name];
  }
  if (root === "branches") return index.effective.branches[key]?.enabled;
  if (root === "order") return index.effective.order[key];
  return undefined;
}

export type FlowState = { index: FlowIndex; config: FlowConfig; locks: FlowLocks; savedLocks: FlowLocks };

/** What calls will use for `path` with the draft applied. */
export function appliedValue(state: FlowState, path: string): unknown {
  if (path in state.locks) return state.locks[path];
  const owner = ownerValue(state.config, path);
  if (owner !== undefined && owner !== null) return owner;
  // A path the server view still shows locked would report the lock; fall back to the default.
  return path in state.savedLocks ? defaultValue(state.index, path) : effectiveValue(state.index, path) ?? defaultValue(state.index, path);
}

/** A value as short text, using a select's option labels. */
export function describeValue(value: unknown, spec?: FlowOptionSpec): string {
  if (value === undefined || value === null || value === "") return "—";
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (spec?.options?.length) {
    const labelOf = (item: unknown) => {
      const match = spec.options.find((option) => option.value === item);
      return match ? t(match.label, String(item)) : String(item);
    };
    if (Array.isArray(value)) return value.map(labelOf).join(", ") || "—";
    return labelOf(value);
  }
  if (Array.isArray(value)) return value.length ? `${value.length} item${value.length === 1 ? "" : "s"}` : "None";
  if (typeof value === "object") return "Custom";
  return String(value);
}

/** Lock paths changed between two lock maps (for the save summary). */
export function changedPaths(a: Record<string, unknown>, b: Record<string, unknown>): string[] {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  return [...keys].filter((key) => canon(a[key]) !== canon(b[key]) || key in a !== key in b);
}
