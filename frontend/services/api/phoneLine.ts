/** The account's phone line: owners ask for a number, the admin assigns it. */

import { request } from "./client";

export type PhoneLineView = {
  /** The assigned number ("" until the admin assigns one). */
  number: string;
  request: { id: string; status: "pending" | "approved" | "declined" | "cancelled"; note: string; admin_note: string; created_at: string } | null;
};

export const phoneLineApi = {
  get: () => request<PhoneLineView>("/api/phone-line", { auth: "merchant" }),
  request: (note = "") => request<PhoneLineView>("/api/phone-line/request", { method: "POST", auth: "merchant", body: JSON.stringify({ note }) }),
};
