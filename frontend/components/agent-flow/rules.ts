/** What the owner may change: step order constraints, platform locks, plan gates, field errors. */

import type { Capabilities, FlowBranch, FlowFieldError } from "@/services/api";

import { under } from "./model";

/** Mirrors the server: a step may sit at a position only if it shares a movable group with
 * the default step there, and every `before` rule holds. */
export function validOrder(branch: FlowBranch, order: string[]): boolean {
  const defaults = branch.skills;
  if (order.length !== defaults.length) return false;
  for (let index = 0; index < order.length; index += 1) {
    const key = order[index];
    const expected = defaults[index];
    if (key !== expected && !branch.movable.some((group) => group.includes(key) && group.includes(expected))) return false;
  }
  for (const [key, earlier] of Object.entries(branch.before ?? {})) {
    const at = order.indexOf(key);
    if (at >= 0 && earlier.some((dep) => order.indexOf(dep) > at)) return false;
  }
  return true;
}

/** The order with the step at `index` swapped one place up (-1) or down (+1), or null if that breaks a rule. */
export function moveStep(branch: FlowBranch, order: string[], index: number, delta: -1 | 1): string[] | null {
  const target = index + delta;
  if (target < 0 || target >= order.length) return null;
  const next = [...order];
  [next[index], next[target]] = [next[target], next[index]];
  return validOrder(branch, next) ? next : null;
}

export function isLocked(locked: string[], path: string): boolean {
  return locked.includes(path);
}

/** Any locked setting at or under `prefix` (for the step's lock badge). */
export function lockedUnder(locked: string[], prefix: string): boolean {
  return locked.some((path) => under(path, prefix));
}

/** Errors at, under or above `prefix` (an error on `steps.intake.options.custom` belongs to the custom-fields editor). */
export function errorsFor(errors: FlowFieldError[], prefix: string): FlowFieldError[] {
  return errors.filter((error) => under(error.path, prefix));
}

/** Steps whose switching on is a paid capability. */
const CAPABILITY_STEPS: Record<string, keyof Capabilities> = { payment: "payments" };

/** The plan doesn't include what turning this step on needs (only an explicit `false` blocks). */
export function stepNeedsUpgrade(key: string, capabilities: Capabilities | undefined): boolean {
  const capability = CAPABILITY_STEPS[key];
  return Boolean(capability && capabilities && capabilities[capability] === false);
}

export const UPGRADE_LINES_ONLY = "Your plan lets you reword lines. Upgrade to switch, reorder or change steps.";
export const LOCKED_HINT = "Set by the platform — ask support to change it.";
