/**
 * The call-flow editor's data model, all pure functions.
 *
 * The server sends, per direction, the blueprint (skills, branches, defaults) and
 * the effective view (every layer applied). The editor keeps one *draft* across
 * directions (skills are shared by key: the goodbye is the same in and out) and
 * saves a SPARSE config: only what differs from the defaults, so settings the
 * owner never touched keep following platform improvements.
 *
 * The *baseline* a value is compared against (see config.ts for the diff) is what the account would get
 * without the owner's own setting: the effective value for paths the owner never
 * set (that already includes the business-type preset and platform locks), the
 * blueprint default for paths the owner did set.
 */

import type { AgentFlow, Direction, FlowBlueprint, FlowBranch, FlowConfig, FlowLanguage, FlowLineSpec, FlowSkill, FlowStepState } from "@/services/api";

export type StepDraft = {
  enabled: boolean;
  options: Record<string, unknown>;
  /** Full text of every line (not just overrides): language → line key → text. */
  lines: Record<string, Record<string, string>>;
};

export type FlowDraft = {
  steps: Record<string, StepDraft>;
  branches: Record<string, boolean>;
  order: Record<string, string[]>;
};

export type FlowModel = {
  /** Per call direction: branches, greeting / goodbye, always-on skills. */
  blueprints: Partial<Record<Direction, FlowBlueprint>>;
  skills: Record<string, FlowSkill>;
  branches: Record<string, FlowBranch>;
  languages: FlowLanguage[];
  hash: string;
  editing: "lines" | "full";
  locked: string[];
  baseline: FlowDraft;
  initial: FlowDraft;
};

// ---------------------------------------------------------------- small helpers

/** JSON with sorted keys, for comparing values. */
export function canon(value: unknown): string {
  return JSON.stringify(value, (_key, inner) =>
    inner && typeof inner === "object" && !Array.isArray(inner)
      ? Object.fromEntries(Object.entries(inner as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)))
      : inner,
  );
}

/** Whitespace collapsed, as the server stores lines. */
export function squash(text: unknown): string {
  return typeof text === "string" ? text.split(/\s+/).filter(Boolean).join(" ") : "";
}

export function defaultLine(spec: FlowLineSpec, lang: string): string {
  const texts = spec.default as Record<string, string | undefined>;
  return texts[lang] || texts.en || Object.values(texts)[0] || "";
}

/** `path` itself or anything under it. */
export function under(path: string, prefix: string): boolean {
  return path === prefix || path.startsWith(`${prefix}.`);
}

function ownerSet(config: FlowConfig, path: string[]): boolean {
  let node: unknown = config;
  for (const part of path) {
    if (!node || typeof node !== "object" || !(part in (node as Record<string, unknown>))) return false;
    node = (node as Record<string, unknown>)[part];
  }
  return node !== undefined && node !== null;
}

// ---------------------------------------------------------------- model

export function buildModel(flow: AgentFlow): FlowModel {
  const skills: Record<string, FlowSkill> = {};
  const branches: Record<string, FlowBranch> = {};
  const effSteps: Record<string, FlowStepState> = {};
  const effBranches: Record<string, boolean> = {};
  const effOrder: Record<string, string[]> = {};
  const blueprints: FlowModel["blueprints"] = {};
  for (const direction of ["inbound", "outbound"] as Direction[]) {
    const view = flow.directions[direction];
    if (!view) continue;
    blueprints[direction] = view.blueprint;
    for (const [key, skill] of Object.entries(view.blueprint.skills)) {
      skills[key] ??= skill;
      effSteps[key] ??= view.effective.steps[key];
    }
    for (const branch of view.blueprint.branches) {
      branches[branch.key] ??= branch;
      effBranches[branch.key] ??= view.effective.branches[branch.key]?.enabled ?? true;
      const order = view.effective.order[branch.key];
      effOrder[branch.key] ??= Array.isArray(order) && order.length === branch.skills.length ? order : branch.skills;
    }
  }

  const owner = flow.config ?? {};
  const languages = flow.languages?.length ? flow.languages : (["en"] as FlowLanguage[]);
  const initial: FlowDraft = { steps: {}, branches: {}, order: {} };
  const baseline: FlowDraft = { steps: {}, branches: {}, order: {} };

  for (const [key, skill] of Object.entries(skills)) {
    const eff = effSteps[key] ?? { enabled: skill.default_enabled, options: {}, lines: {} };
    const enabled = skill.toggleable ? Boolean(eff.enabled) : true;
    const options = { ...skill.defaults, ...(eff.options ?? {}) };
    const baseOptions: Record<string, unknown> = {};
    for (const name of new Set([...Object.keys(skill.defaults ?? {}), ...skill.options.map((spec) => spec.key)])) {
      baseOptions[name] = ownerSet(owner, ["steps", key, "options", name]) ? skill.defaults?.[name] : options[name];
    }
    const lines: StepDraft["lines"] = {};
    const baseLines: StepDraft["lines"] = {};
    for (const lang of languages) {
      lines[lang] = {};
      baseLines[lang] = {};
      for (const spec of skill.lines) {
        const fallback = defaultLine(spec, lang);
        const effective = eff.lines?.[lang]?.[spec.key] || fallback;
        lines[lang][spec.key] = effective;
        baseLines[lang][spec.key] = ownerSet(owner, ["steps", key, "lines", lang, spec.key]) ? fallback : effective;
      }
    }
    initial.steps[key] = { enabled, options, lines };
    baseline.steps[key] = {
      enabled: skill.toggleable && !ownerSet(owner, ["steps", key, "enabled"]) ? enabled : skill.toggleable ? skill.default_enabled : true,
      options: baseOptions,
      lines: baseLines,
    };
  }
  for (const [key, branch] of Object.entries(branches)) {
    initial.branches[key] = branch.toggleable ? effBranches[key] : true;
    baseline.branches[key] = ownerSet(owner, ["branches", key, "enabled"]) ? true : initial.branches[key];
    initial.order[key] = [...effOrder[key]];
    baseline.order[key] = ownerSet(owner, ["order", key]) ? [...branch.skills] : [...effOrder[key]];
  }
  return { blueprints, skills, branches, languages, hash: flow.hash, editing: flow.editing === "lines" ? "lines" : "full", locked: flow.locked ?? [], baseline, initial };
}

// ---------------------------------------------------------------- draft updates

export function withStep(draft: FlowDraft, key: string, update: (step: StepDraft) => StepDraft): FlowDraft {
  const step = draft.steps[key];
  return step ? { ...draft, steps: { ...draft.steps, [key]: update(step) } } : draft;
}

export function withLine(draft: FlowDraft, key: string, lang: string, line: string, text: string): FlowDraft {
  return withStep(draft, key, (step) => ({ ...step, lines: { ...step.lines, [lang]: { ...step.lines[lang], [line]: text } } }));
}

export function withOption(draft: FlowDraft, key: string, name: string, value: unknown): FlowDraft {
  return withStep(draft, key, (step) => ({ ...step, options: { ...step.options, [name]: value } }));
}

/** Put the values at `paths` back to `source` (e.g. settings the platform turned out to have locked). */
export function revertPaths(draft: FlowDraft, source: FlowDraft, paths: string[]): FlowDraft {
  let next = draft;
  for (const path of paths) {
    const [root, key, part, a, b] = path.split(".");
    if (root === "steps" && source.steps[key]) {
      if (part === "enabled") next = withStep(next, key, (step) => ({ ...step, enabled: source.steps[key].enabled }));
      else if (part === "options" && a) next = withOption(next, key, a, source.steps[key].options[a]);
      else if (part === "lines" && a && b) next = withLine(next, key, a, b, source.steps[key].lines[a]?.[b] ?? "");
    } else if (root === "branches" && key in source.branches) {
      next = { ...next, branches: { ...next.branches, [key]: source.branches[key] } };
    } else if (root === "order" && source.order[key]) {
      next = { ...next, order: { ...next.order, [key]: [...source.order[key]] } };
    }
  }
  return next;
}
