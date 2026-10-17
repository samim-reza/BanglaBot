/** Holiday / closure dates the agent never books (Settings → Closures). */

import { request } from "./client";

export type Closure = {
  /** YYYY-MM-DD, business-local; both ends included. */
  start: string;
  end: string;
  label: string;
  /** A doctor / stylist / resource ("" = the whole business). */
  item_id: string;
};

export type ClosureInput = { start: string; end?: string; label?: string; item_id?: string };

export type ClosuresView = {
  closures: Closure[];
  /** Who a closure can be limited to (empty for businesses without per-person hours). */
  items: { id: string; name: string }[];
  /** The business's today (YYYY-MM-DD). */
  today: string;
};

export const closuresApi = {
  list: () => request<ClosuresView>("/api/closures", { auth: "merchant" }),
  /** Replaces the whole list (ended closures are dropped by the server). */
  save: (closures: ClosureInput[]) =>
    request<ClosuresView>("/api/closures", { method: "PUT", auth: "merchant", body: JSON.stringify({ closures }) }),
};
